import { TransactionStatus } from 'genlayer-js/types';
import { CONTRACT_ADDRESS, EXPLORER_TX_URL } from '../../config/chains';
import { getReadClient, getWriteClient, RECEIPT_CONFIG, TimeoutError } from './client';

export async function readView<T = any>(functionName: string, args: any[] = []): Promise<T> {
  const client = getReadClient();
  const raw = await client.readContract({
    address: CONTRACT_ADDRESS as `0x${string}`,
    functionName,
    args,
  });
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as T;
    } catch {
      return raw as unknown as T;
    }
  }
  return raw as T;
}

export interface WriteResult {
  hash: string;
  status: 'confirmed' | 'timeout';
  returnValue?: any;
}

export async function writeMethod(
  account: `0x${string}`,
  functionName: string,
  args: any[],
  value: bigint = BigInt(0)
): Promise<WriteResult> {
  const client = await getWriteClient(account);

  const hash = await client.writeContract({
    address: CONTRACT_ADDRESS as `0x${string}`,
    functionName,
    args,
    value,
  });

  try {
    const receipt = await client.waitForTransactionReceipt({
      hash,
      status: TransactionStatus.ACCEPTED,
      retries: RECEIPT_CONFIG.retries,
      interval: RECEIPT_CONFIG.interval,
    } as any);
    return { hash, status: 'confirmed', returnValue: (receipt as any)?.data ?? receipt };
  } catch (err) {
    throw new TimeoutError(hash, EXPLORER_TX_URL(hash));
  }
}
