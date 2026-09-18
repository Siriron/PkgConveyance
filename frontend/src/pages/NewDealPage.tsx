import { useState } from 'react';
import { useWallet } from '../lib/useWallet';
import { writeMethod } from '../lib/genlayer/contract';

function randomDealId() {
  return 'deal-' + Math.random().toString(36).slice(2, 10);
}

export function NewDealPage({ onNavigate }: { onNavigate: (r: string) => void }) {
  const { account, connect } = useWallet();
  const [dealId] = useState(randomDealId);
  const [packageName, setPackageName] = useState('');
  const [seller, setSeller] = useState('');
  const [sellerUsername, setSellerUsername] = useState('');
  const [buyerUsername, setBuyerUsername] = useState('');
  const [escrowGen, setEscrowGen] = useState('1');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [txHash, setTxHash] = useState<string | null>(null);

  async function submit() {
    if (!account) {
      await connect();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const weiValue = BigInt(Math.round(parseFloat(escrowGen || '0') * 1e18));
      const res = await writeMethod(
        account,
        'open_deal',
        [dealId, packageName.trim(), seller.trim(), sellerUsername.trim(), buyerUsername.trim()],
        weiValue
      );
      setTxHash(res.hash);
      const returned = typeof res.returnValue === 'string' ? res.returnValue : '';
      if (returned.startsWith('[')) {
        setError(returned);
      } else {
        onNavigate(`/deals/${dealId}`);
      }
    } catch (err: any) {
      setError(err?.message || 'Could not open this deal.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="hero" style={{ paddingBottom: 24 }}>
        <h1 style={{ fontSize: 30 }}>Open a deal</h1>
        <p className="lede">
          You are the buyer. Escrow the price now; it returns automatically if the seller
          never arms, or if the maintainer add never happens before the transfer deadline.
        </p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="form-grid">
        <div className="form-field">
          <label>Deal ID</label>
          <input className="mono" value={dealId} disabled />
          <div className="form-hint">Generated for you — shareable with the seller.</div>
        </div>

        <div className="form-field">
          <label>Package name</label>
          <input
            className="mono"
            placeholder="left-pad"
            value={packageName}
            onChange={(e) => setPackageName(e.target.value)}
          />
          <div className="form-hint">Must already exist on the npm registry.</div>
        </div>

        <div className="form-field">
          <label>Seller's wallet address</label>
          <input
            className="mono"
            placeholder="0x…"
            value={seller}
            onChange={(e) => setSeller(e.target.value)}
          />
        </div>

        <div className="form-field">
          <label>Seller's npm username</label>
          <input
            className="mono"
            placeholder="the current maintainer's npm login"
            value={sellerUsername}
            onChange={(e) => setSellerUsername(e.target.value)}
          />
          <div className="form-hint">
            Checked live against the registry before your escrow is accepted.
          </div>
        </div>

        <div className="form-field">
          <label>Your npm username</label>
          <input
            className="mono"
            placeholder="the npm login you want added as maintainer"
            value={buyerUsername}
            onChange={(e) => setBuyerUsername(e.target.value)}
          />
        </div>

        <div className="form-field">
          <label>Escrow amount (GEN)</label>
          <input
            className="mono"
            type="number"
            min="0"
            step="0.01"
            value={escrowGen}
            onChange={(e) => setEscrowGen(e.target.value)}
          />
        </div>

        <button className="action-btn" onClick={submit} disabled={submitting}>
          {submitting ? 'Escrowing…' : account ? 'Escrow and open deal' : 'Connect wallet'}
        </button>

        {txHash && (
          <div className="pending-note">
            Consensus can take a few minutes for the first check.{' '}
            <a
              className="tx-link"
              href={`https://explorer-studio.genlayer.com/transactions/${txHash}`}
              target="_blank"
              rel="noreferrer"
            >
              View transaction
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
