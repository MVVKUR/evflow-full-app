import { EVFLOW_API_BASE_URL } from '../stations/api';
import { toQueryString } from '../api/client';

export type WalletBalanceApiResponse = {
  balance_idr: number;
  currency: string;
  updated_at: string;
};

export type TopupApiItem = {
  id: string;
  external_id: string;
  xendit_invoice_id: string | null;
  amount_idr: number;
  status: string;
  invoice_url: string | null;
  created_at: string;
  paid_at: string | null;
};

export type TopupCreatedApiResponse = {
  topup_id: string;
  amount_idr: number;
  status: string;
  invoice_url: string;
};

export async function fetchWalletBalance(fetcher: typeof fetch = fetch) {
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/wallet`);

  if (!response.ok) {
    throw new Error(`EVFlow wallet request failed with status ${response.status}`);
  }

  return response.json() as Promise<WalletBalanceApiResponse>;
}

export async function createWalletTopup(amountIdr: number, fetcher: typeof fetch = fetch) {
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/wallet/topup`, {
    body: JSON.stringify({ amount_idr: amountIdr }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  if (!response.ok) {
    throw new Error(`EVFlow wallet top-up request failed with status ${response.status}`);
  }

  return response.json() as Promise<TopupCreatedApiResponse>;
}

export async function fetchWalletTopups(limit = 20, fetcher: typeof fetch = fetch) {
  const query = toQueryString({ limit });
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/wallet/topups${query}`);

  if (!response.ok) {
    throw new Error(`EVFlow wallet top-ups request failed with status ${response.status}`);
  }

  return response.json() as Promise<TopupApiItem[]>;
}
