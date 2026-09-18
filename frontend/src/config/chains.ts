// Single source of truth for network and contract configuration.
// Deliberately a plain literal, not an environment variable: this project's own
// standing rule is that redeploying to a new address means editing one line here,
// with no dashboard, dotfile, or env-var indirection to keep in sync.

export const CONTRACT_ADDRESS = '0x0000000000000000000000000000000000000000';

export const STUDIONET_CONFIG = {
  chainId: '0xF22F', // 61999
  chainName: 'GenLayer StudioNet',
  rpcUrls: ['https://studio.genlayer.com/api'],
  nativeCurrency: { name: 'GEN', symbol: 'GEN', decimals: 18 },
  blockExplorerUrls: ['https://explorer-studio.genlayer.com'],
};

export const EXPLORER_TX_URL = (hash: string) =>
  `https://explorer-studio.genlayer.com/transactions/${hash}`;

export const EXPLORER_CONTRACT_URL = (address: string) =>
  `https://explorer-studio.genlayer.com/contracts/${address}`;

export const CHECK_COOLDOWN_SECONDS = 300;
