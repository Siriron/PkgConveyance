import { createClient } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import { STUDIONET_CONFIG } from '../../config/chains';

export function getReadClient() {
  return createClient({ chain: studionet });
}

export async function getWriteClient(account: `0x${string}`) {
  await ensureChain();
  const client = createClient({ chain: studionet, account, provider: (window as any).ethereum });
  // Defensive: not in every SDK version, guard before calling.
  if (typeof (client as any).connect === 'function') {
    try {
      await (client as any).connect('studionet');
    } catch {
      // non-fatal — some SDK builds don't need or support this call
    }
  }
  return client;
}

export async function ensureChain() {
  const eth = (window as any).ethereum;
  if (!eth) return;
  try {
    await eth.request({
      method: 'wallet_switchEthereumChain',
      params: [{ chainId: STUDIONET_CONFIG.chainId }],
    });
  } catch (err: any) {
    if (err && err.code === 4902) {
      await eth.request({ method: 'wallet_addEthereumChain', params: [STUDIONET_CONFIG] });
      await eth.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: STUDIONET_CONFIG.chainId }],
      });
    } else if (err && err.code === -32002) {
      await new Promise((r) => setTimeout(r, 3000));
    } else {
      throw err;
    }
  }
}

export class TimeoutError extends Error {
  txHash: string;
  isTimeout = true;
  constructor(hash: string, explorerUrl: string) {
    super(
      `Consensus is taking longer than expected. Your transaction was submitted — check its status directly: ${explorerUrl}`
    );
    this.txHash = hash;
  }
}

export const RECEIPT_CONFIG = { retries: 120, interval: 4000 };
