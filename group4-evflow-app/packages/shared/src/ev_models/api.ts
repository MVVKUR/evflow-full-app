import { toQueryString } from '../api/client';
import { EVFLOW_API_BASE_URL } from '../stations/api';

export type EVModelApiItem = {
  id: string;
  name: string;
  make: string | null;
  model: string | null;
  battery_kwh: number | null;
  range_km: number | null;
  price_range: string | null;
  charging_time: string | null;
  source_url: string | null;
};

export type EVModelListApiResponse = {
  total: number;
  limit: number;
  offset: number;
  items: EVModelApiItem[];
};

export type EVModelListParams = {
  q?: string;
  limit?: number;
  offset?: number;
};

export async function fetchEvModels(params: EVModelListParams = {}, fetcher: typeof fetch = fetch) {
  const query = toQueryString({
    q: params.q,
    limit: params.limit,
    offset: params.offset
  });
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/ev-models${query}`);

  if (!response.ok) {
    throw new Error(`EVFlow EV models request failed with status ${response.status}`);
  }

  return response.json() as Promise<EVModelListApiResponse>;
}
