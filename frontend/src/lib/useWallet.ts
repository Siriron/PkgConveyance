import { useCallback, useEffect, useState } from 'react';

export function useWallet() {
  const [account, setAccount] = useState<`0x${string}` | null>(null);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    const eth = (window as any).ethereum;
    if (!eth) return;
    eth
      .request({ method: 'eth_accounts' })
      .then((accounts: string[]) => {
        if (accounts[0]) setAccount(accounts[0] as `0x${string}`);
      })
      .catch(() => {});
    const handleAccountsChanged = (accounts: string[]) =>
      setAccount((accounts[0] as `0x${string}`) || null);
    if (eth.on) eth.on('accountsChanged', handleAccountsChanged);
    return () => {
      if (eth.removeListener) eth.removeListener('accountsChanged', handleAccountsChanged);
    };
  }, []);

  const connect = useCallback(async () => {
    const eth = (window as any).ethereum;
    if (!eth) {
      alert('No wallet found. Install MetaMask or a compatible wallet to use PkgConveyance.');
      return;
    }
    setConnecting(true);
    try {
      const accounts = await eth.request({ method: 'eth_requestAccounts' });
      if (accounts[0]) setAccount(accounts[0] as `0x${string}`);
    } finally {
      setConnecting(false);
    }
  }, []);

  return { account, connect, connecting };
}
