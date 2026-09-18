import { useEffect, useState } from 'react';
import { readView } from '../lib/genlayer/contract';

interface Parameters {
  npmjs_registry_base: string;
  npmmirror_registry_base: string;
  accept_window_seconds: string;
  transfer_window_seconds: string;
  check_cooldown_seconds: string;
  max_deal_value_wei: string;
  uses_a_model: string;
  boundary: string;
}

export function DocsPage() {
  const [params, setParams] = useState<Parameters | null>(null);

  useEffect(() => {
    readView<Parameters>('parameters').then(setParams).catch(() => {});
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 30, marginBottom: 8 }}>How it works</h1>
      <p style={{ color: 'var(--ink-soft)', maxWidth: 620 }}>
        PkgConveyance escrows GEN for an npm package's ownership transfer and releases it only
        when the npm registry's own maintainer list shows the transfer actually happened.
      </p>

      <h2 style={{ fontSize: 18, marginTop: 40 }}>Why GenLayer is necessary</h2>
      <p style={{ color: 'var(--ink-soft)', maxWidth: 620 }}>
        A package's maintainer list lives at registry.npmjs.org and nowhere on any chain. An
        oracle would need a trusted relayer to copy it across; a keeper would need a bot
        running at the right moment. GenLayer removes the copy: every validator fetches the
        registry document itself inside the consensus block, and{' '}
        <code className="mono">gl.eq_principle.strict_eq</code> requires them to arrive at the
        exact same bytes before anything is written. There is no model anywhere in this
        contract — every fetched field is compared for exact agreement, never judged.
      </p>

      <h2 style={{ fontSize: 18, marginTop: 32 }}>What it checks, in order</h2>
      <ol style={{ color: 'var(--ink-soft)', maxWidth: 620, paddingLeft: 20 }}>
        <li>At <code className="mono">open_deal</code>: is the named seller a maintainer of the package today, and is the buyer not already one?</li>
        <li>At <code className="mono">arm</code>: is the seller still a maintainer, re-checked live rather than trusted from the baseline?</li>
        <li>At <code className="mono">check_transfer</code>: does the buyer's npm username now appear in the maintainer list, and does the seller's still appear (so a wipe isn't mistaken for a transfer)?</li>
      </ol>
      <p style={{ color: 'var(--ink-soft)', maxWidth: 620 }}>
        Every one of these reads two independently operated registry mirrors —
        registry.npmjs.org and registry.npmmirror.com — and refuses to proceed if they
        currently disagree, rather than trusting either one alone.
      </p>

      <h2 style={{ fontSize: 18, marginTop: 32 }}>What it refuses to decide</h2>
      <div className="boundary-note" style={{ maxWidth: 620 }}>
        {params?.boundary ||
          "Verifies public npm maintainer-list membership. Does not prove legal ownership of a package name, the identity behind an npm account, or anything about the package's source or license."}
      </div>

      <h2 style={{ fontSize: 18, marginTop: 32 }}>Contract surface</h2>
      <table className="mono" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, maxWidth: 620 }}>
        <tbody>
          {[
            ['open_deal', 'write, payable', 'anyone — value sent becomes the escrow'],
            ['arm', 'write', 'seller only'],
            ['check_transfer', 'write', 'anyone, rate-limited per deal'],
            ['settle', 'write', 'anyone, once VERIFIED'],
            ['refund', 'write', 'anyone, once the relevant window closes'],
            ['abandon', 'write', 'either party while OFFERED, seller only once LOCKED'],
            ['probe_package', 'write, no storage', 'anyone — free-standing registry check'],
            ['get_deal / list_deals / deal_for_package / ledger / parameters', 'view', '—'],
          ].map(([m, k, w]) => (
            <tr key={m} style={{ borderBottom: '1px solid var(--hairline)' }}>
              <td style={{ padding: '8px 8px 8px 0' }}>{m}</td>
              <td style={{ padding: '8px', color: 'var(--ink-soft)' }}>{k}</td>
              <td style={{ padding: '8px 0 8px 8px', color: 'var(--ink-soft)' }}>{w}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {params && (
        <>
          <h2 style={{ fontSize: 18, marginTop: 32 }}>Live parameters</h2>
          <table className="mono" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, maxWidth: 620 }}>
            <tbody>
              <tr style={{ borderBottom: '1px solid var(--hairline)' }}>
                <td style={{ padding: '8px 8px 8px 0' }}>uses_a_model</td>
                <td style={{ padding: 8, color: 'var(--ink-soft)' }}>{params.uses_a_model}</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--hairline)' }}>
                <td style={{ padding: '8px 8px 8px 0' }}>accept window</td>
                <td style={{ padding: 8, color: 'var(--ink-soft)' }}>{Number(params.accept_window_seconds) / 86400} days</td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--hairline)' }}>
                <td style={{ padding: '8px 8px 8px 0' }}>transfer window</td>
                <td style={{ padding: 8, color: 'var(--ink-soft)' }}>{Number(params.transfer_window_seconds) / 86400} days</td>
              </tr>
              <tr>
                <td style={{ padding: '8px 8px 8px 0' }}>check cooldown</td>
                <td style={{ padding: 8, color: 'var(--ink-soft)' }}>{Number(params.check_cooldown_seconds) / 60} minutes</td>
              </tr>
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
