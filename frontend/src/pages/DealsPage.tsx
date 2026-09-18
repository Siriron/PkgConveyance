import { useEffect, useState } from 'react';
import { readView } from '../lib/genlayer/contract';
import { PackageResolver } from '../components/PackageResolver';

interface DealSummary {
  deal_id: string;
  state: string;
  package_name: string;
  escrow: string;
  buyer_npm_username: string;
  last_check_outcome: string;
  last_check_at: string;
}

export function DealsPage({ onNavigate }: { onNavigate: (r: string) => void }) {
  const [deals, setDeals] = useState<DealSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    readView<DealSummary[]>('list_deals')
      .then(setDeals)
      .catch((err) => setError(err?.message || 'Could not load deals.'));
  }, []);

  return (
    <div>
      <div className="hero">
        <h1>Escrow that only releases when npm's own registry says the transfer happened.</h1>
        <p className="lede">
          A buyer escrows the price for a named npm package. A seller who currently maintains
          it adds the buyer as a maintainer. The contract reads two independently operated
          registry mirrors inside consensus and pays the seller only when both agree the
          maintainer list actually changed.
        </p>
        <div className="boundary-note">
          Verifies public npm maintainer-list membership. Does not prove legal ownership of a
          package name, the identity behind an npm account, or anything about the package's
          source or license.
        </div>
        <PackageResolver />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <h2 style={{ fontSize: 16, margin: 0, color: 'var(--ink-soft)' }}>Open and recent deals</h2>
        <button className="action-btn" onClick={() => onNavigate('/new')}>
          Open a deal
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!error && deals === null && <div className="empty-state">Loading the ledger…</div>}

      {deals && deals.length === 0 && (
        <div className="empty-state">
          No deals yet.
          <br />
          <a
            href="/new"
            onClick={(e) => {
              e.preventDefault();
              onNavigate('/new');
            }}
          >
            Open the first one →
          </a>
        </div>
      )}

      {deals && deals.length > 0 && (
        <div className="manifest">
          {deals.map((d) => (
            <a
              key={d.deal_id}
              className="manifest-entry"
              href={`/deals/${d.deal_id}`}
              onClick={(e) => {
                e.preventDefault();
                onNavigate(`/deals/${d.deal_id}`);
              }}
            >
              <div>
                <div className="pkg">{d.package_name}</div>
                <div className="meta">
                  {d.deal_id} · buyer @{d.buyer_npm_username}
                  {d.last_check_outcome ? ` · last check: ${d.last_check_outcome}` : ''}
                </div>
              </div>
              <span className={`state-chip ${d.state}`}>{d.state}</span>
              <span className="escrow-amount">{d.escrow} wei</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
