import { useEffect, useState, useCallback } from 'react';
import { useWallet } from '../lib/useWallet';
import { readView, writeMethod } from '../lib/genlayer/contract';
import { CHECK_COOLDOWN_SECONDS, EXPLORER_TX_URL } from '../config/chains';

interface Deal {
  deal_id: string;
  state: string;
  buyer: string;
  seller: string;
  package_name: string;
  buyer_npm_username: string;
  seller_npm_username: string;
  escrow: string;
  opened_at: string;
  accept_deadline: string;
  armed_at: string;
  transfer_deadline: string;
  verified_at: string;
  closed_at: string;
  baseline_maintainers: string;
  checks: string;
  last_check_at: string;
  last_check_outcome: string;
  last_check_note: string;
  last_check_maintainers: string;
  paid_to_seller: string;
  returned_to_buyer: string;
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div className="field">
      <div className="k">{k}</div>
      <div className="v">{v || '—'}</div>
    </div>
  );
}

export function DealDetailPage({ dealId, onNavigate }: { dealId: string; onNavigate: (r: string) => void }) {
  const { account, connect } = useWallet();
  const [deal, setDeal] = useState<Deal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [txHash, setTxHash] = useState<string | null>(null);

  const load = useCallback(() => {
    readView<Deal>('get_deal', [dealId])
      .then((d) => setDeal(d && d.deal_id ? d : null))
      .catch((err) => setError(err?.message || 'Could not load this deal.'));
  }, [dealId]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(method: string, args: any[] = []) {
    if (!account) {
      await connect();
      return;
    }
    setPending(method);
    setError(null);
    setTxHash(null);
    try {
      const res = await writeMethod(account, method, args);
      setTxHash(res.hash);
      load();
    } catch (err: any) {
      setError(err?.message || `${method} failed.`);
    } finally {
      setPending(null);
    }
  }

  if (error && !deal) {
    return (
      <div className="empty-state">
        {error}
        <br />
        <a href="/" onClick={(e) => { e.preventDefault(); onNavigate('/'); }}>← Back to deals</a>
      </div>
    );
  }

  if (!deal) {
    return <div className="empty-state">Loading…</div>;
  }

  const isBuyer = account && account.toLowerCase() === deal.buyer.toLowerCase();
  const isSeller = account && account.toLowerCase() === deal.seller.toLowerCase();
  const maintainers = deal.baseline_maintainers ? deal.baseline_maintainers.split(',') : [];

  return (
    <div>
      <a href="/" onClick={(e) => { e.preventDefault(); onNavigate('/'); }} className="tx-link">
        ← All deals
      </a>

      <div className="deal-header" style={{ marginTop: 18 }}>
        <h2>{deal.package_name}</h2>
        <span className={`state-chip ${deal.state}`}>{deal.state}</span>
      </div>
      <div className="meta" style={{ color: 'var(--ink-soft)', fontSize: 14 }}>{deal.deal_id}</div>

      {error && <div className="error-banner" style={{ marginTop: 16 }}>{error}</div>}
      {txHash && (
        <div className="pending-note">
          Submitted.{' '}
          <a className="tx-link" href={EXPLORER_TX_URL(txHash)} target="_blank" rel="noreferrer">
            View transaction
          </a>{' '}
          — consensus can take a few minutes.
        </div>
      )}

      <div className="field-grid">
        <Field k="Escrow" v={`${deal.escrow} wei`} />
        <Field k="Buyer wants" v={`@${deal.buyer_npm_username} added`} />
        <Field k="Seller maintains as" v={`@${deal.seller_npm_username}`} />
        <Field k="Baseline maintainers" v={maintainers.join(', ')} />
        <Field k="Opened" v={deal.opened_at} />
        <Field k="Accept deadline" v={deal.accept_deadline} />
        <Field k="Armed at" v={deal.armed_at} />
        <Field k="Transfer deadline" v={deal.transfer_deadline} />
        <Field k="Checks run" v={deal.checks} />
        <Field k="Last check" v={deal.last_check_at ? `${deal.last_check_at} — ${deal.last_check_outcome}` : '—'} />
      </div>

      {deal.last_check_note && (
        <div className="boundary-note" style={{ marginBottom: 20 }}>{deal.last_check_note}</div>
      )}

      {/* OFFERED */}
      {deal.state === 'OFFERED' && (
        <>
          <div className="action-panel">
            <h3>Arm this deal</h3>
            <p>
              Seller only. Confirms @{deal.seller_npm_username} is a maintainer of{' '}
              {deal.package_name} right now, and opens the transfer window.
            </p>
            <button
              className="action-btn"
              disabled={!!pending || (!!account && !isSeller)}
              onClick={() => run('arm', [deal.deal_id])}
            >
              {pending === 'arm' ? 'Confirming…' : isSeller ? 'Arm deal' : 'Seller only'}
            </button>
          </div>
          <div className="action-panel">
            <h3>Abandon</h3>
            <p>Either party can cancel while the deal is still OFFERED. Escrow returns to the buyer.</p>
            <button
              className="action-btn danger"
              disabled={!!pending || !(isBuyer || isSeller)}
              onClick={() => run('abandon', [deal.deal_id])}
            >
              {pending === 'abandon' ? 'Cancelling…' : 'Abandon deal'}
            </button>
          </div>
          <div className="action-panel">
            <h3>Refund</h3>
            <p>Anyone can trigger this once the accept deadline ({deal.accept_deadline}) has passed.</p>
            <button className="action-btn" disabled={!!pending} onClick={() => run('refund', [deal.deal_id])}>
              {pending === 'refund' ? 'Refunding…' : 'Refund to buyer'}
            </button>
          </div>
        </>
      )}

      {/* LOCKED */}
      {deal.state === 'LOCKED' && (
        <>
          <div className="action-panel">
            <h3>Check transfer</h3>
            <p>
              Anyone can call this. Reads registry.npmjs.org and registry.npmmirror.com and
              records whether @{deal.buyer_npm_username} now appears as a maintainer alongside
              @{deal.seller_npm_username}. Rate-limited to once every {CHECK_COOLDOWN_SECONDS / 60} minutes.
            </p>
            <button className="action-btn confirm" disabled={!!pending} onClick={() => run('check_transfer', [deal.deal_id])}>
              {pending === 'check_transfer' ? 'Checking both registries…' : 'Check transfer'}
            </button>
          </div>
          <div className="action-panel">
            <h3>Abandon</h3>
            <p>Seller only, once LOCKED — the seller may be mid-transfer and shouldn't be able to be cancelled on mid-flight.</p>
            <button
              className="action-btn danger"
              disabled={!!pending || (!!account && !isSeller)}
              onClick={() => run('abandon', [deal.deal_id])}
            >
              {pending === 'abandon' ? 'Cancelling…' : isSeller ? 'Abandon deal' : 'Seller only'}
            </button>
          </div>
          <div className="action-panel">
            <h3>Refund</h3>
            <p>Anyone can trigger this once the transfer deadline ({deal.transfer_deadline || 'not yet set'}) has passed.</p>
            <button className="action-btn" disabled={!!pending} onClick={() => run('refund', [deal.deal_id])}>
              {pending === 'refund' ? 'Refunding…' : 'Refund to buyer'}
            </button>
          </div>
        </>
      )}

      {/* VERIFIED */}
      {deal.state === 'VERIFIED' && (
        <div className="action-panel">
          <h3>Settle</h3>
          <p>
            Verified on {deal.verified_at} — @{deal.buyer_npm_username} is confirmed as a
            maintainer of {deal.package_name} on both registries. Anyone can trigger the payout.
          </p>
          <button className="action-btn confirm" disabled={!!pending} onClick={() => run('settle', [deal.deal_id])}>
            {pending === 'settle' ? 'Releasing…' : 'Release escrow to seller'}
          </button>
        </div>
      )}

      {/* Closed states */}
      {['SETTLED', 'REFUNDED', 'ABANDONED'].includes(deal.state) && (
        <div className="boundary-note">
          {deal.state === 'SETTLED'
            ? `Closed. ${deal.paid_to_seller} wei paid to the seller.`
            : `Closed. ${deal.returned_to_buyer} wei returned to the buyer.`}
        </div>
      )}
    </div>
  );
}
