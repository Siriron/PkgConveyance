import { useWallet } from '../lib/useWallet';

function shortAddress(addr: string) {
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export function Topbar({
  route,
  onNavigate,
}: {
  route: string;
  onNavigate: (r: string) => void;
}) {
  const { account, connect, connecting } = useWallet();

  return (
    <div className="topbar">
      <a
        className="wordmark"
        href="/"
        onClick={(e) => {
          e.preventDefault();
          onNavigate('/');
        }}
      >
        <span className="mark" />
        <span className="name">PkgConveyance</span>
        <span className="tag">npm ownership escrow</span>
      </a>
      <nav className="tabs">
        <button className={route === '/' ? 'active' : ''} onClick={() => onNavigate('/')}>
          Deals
        </button>
        <button className={route === '/new' ? 'active' : ''} onClick={() => onNavigate('/new')}>
          New deal
        </button>
        <button className={route === '/docs' ? 'active' : ''} onClick={() => onNavigate('/docs')}>
          Docs
        </button>
      </nav>
      {account ? (
        <span className="wallet-pill">{shortAddress(account)}</span>
      ) : (
        <button className="connect-btn" onClick={connect} disabled={connecting}>
          {connecting ? 'Connecting…' : 'Connect wallet'}
        </button>
      )}
    </div>
  );
}
