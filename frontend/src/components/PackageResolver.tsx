import { useState } from 'react';
import { useWallet } from '../lib/useWallet';
import { writeMethod } from '../lib/genlayer/contract';

interface ProbeResult {
  package_name: string;
  found: string;
  maintainers: string;
  latest_version: string;
  modified_at: string;
}

export function PackageResolver() {
  const { account, connect } = useWallet();
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ProbeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function resolve() {
    if (!name.trim()) return;
    if (!account) {
      await connect();
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      // probe_package is a write method (it runs a real consensus round against two
      // registries) but touches no storage, so it costs gas without creating a deal.
      const res = await writeMethod(account, 'probe_package', [name.trim()]);
      setResult(res.returnValue as ProbeResult);
    } catch (err: any) {
      setError(err?.message || 'Could not resolve that package right now.');
    } finally {
      setLoading(false);
    }
  }

  const maintainers = result?.maintainers ? result.maintainers.split(',').filter(Boolean) : [];

  return (
    <div className="resolver">
      <div className="resolver-input-row">
        <input
          className="mono"
          placeholder="left-pad"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && resolve()}
        />
        <button onClick={resolve} disabled={loading || !name.trim()}>
          {loading ? 'Resolving…' : 'Resolve'}
        </button>
      </div>

      {error && <div className="error-banner" style={{ marginTop: 14 }}>{error}</div>}

      {result && (
        <div className="resolver-result">
          <div className="row">
            <span className="k">registered</span>
            <span className="v">
              <span className={`status-dot ${result.found === 'True' ? 'ok' : 'bad'}`} />
              {result.found === 'True' ? 'yes, on both mirrors' : 'no'}
            </span>
          </div>
          {result.found === 'True' && (
            <>
              <div className="row">
                <span className="k">latest version</span>
                <span className="v">{result.latest_version || '—'}</span>
              </div>
              <div className="row">
                <span className="k">maintainers</span>
                <span className="v">{maintainers.length}</span>
              </div>
              {maintainers.map((m) => (
                <div className="row" key={m}>
                  <span className="k" />
                  <span className="v">{m}</span>
                </div>
              ))}
              <div className="row">
                <span className="k">last modified</span>
                <span className="v">{result.modified_at || '—'}</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
