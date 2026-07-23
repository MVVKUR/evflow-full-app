import { EVFLOW_API_BASE_URL } from '../stations/api';
import { getAuthHeaders } from '../auth/session';
import { AuthRequiredError } from '../wallet/api';

export type ChargingQuoteApiResponse = {
  energy_kwh: number;
  base_rate_idr: number;
  admin_fee_idr: number;
  energy_cost_idr: number;
  total_due_idr: number;
  currency: string;
};

export type ChargingSessionApiResponse = {
  id: string;
  station_id: string;
  station_name: string | null;
  connector_type: string | null;
  power_kw: number | null;
  energy_kwh: number;
  base_rate_idr: number;
  admin_fee_idr: number;
  deposit_idr: number;
  delivered_kwh: number | null;
  actual_cost_idr: number | null;
  refund_idr: number | null;
  status: string;
  created_at: string;
  completed_at: string | null;
  wallet_balance_idr: number;
};

export type StartChargingSessionInput = {
  stationId: string;
  energyKwh: number;
  stationName?: string | null;
  connectorType?: string | null;
  powerKw?: number | null;
};

/** Thrown when the wallet can't cover the deposit (HTTP 402). */
export class InsufficientBalanceError extends Error {
  constructor(message = 'Insufficient wallet balance to start charging.') {
    super(message);
    this.name = 'InsufficientBalanceError';
  }
}

export async function fetchChargingQuote(energyKwh: number, fetcher: typeof fetch = fetch) {
  const authHeaders = requireAuthHeaders();
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/charging/quote`, {
    method: 'POST',
    headers: { ...authHeaders, 'Content-Type': 'application/json' },
    body: JSON.stringify({ energy_kwh: energyKwh })
  });

  if (!response.ok) {
    throw new Error(`EVFlow charging quote failed with status ${response.status}`);
  }

  return response.json() as Promise<ChargingQuoteApiResponse>;
}

export async function startChargingSession(input: StartChargingSessionInput, fetcher: typeof fetch = fetch) {
  const authHeaders = requireAuthHeaders();
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions`, {
    method: 'POST',
    headers: { ...authHeaders, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      station_id: input.stationId,
      energy_kwh: input.energyKwh,
      station_name: input.stationName ?? null,
      connector_type: input.connectorType ?? null,
      power_kw: input.powerKw ?? null
    })
  });

  if (response.status === 402) {
    throw new InsufficientBalanceError();
  }
  if (!response.ok) {
    throw new Error(`EVFlow start charging session failed with status ${response.status}`);
  }

  return response.json() as Promise<ChargingSessionApiResponse>;
}

export async function settleChargingSession(sessionId: string, deliveredKwh: number, fetcher: typeof fetch = fetch) {
  const authHeaders = requireAuthHeaders();
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions/${sessionId}/settle`, {
    method: 'POST',
    headers: { ...authHeaders, 'Content-Type': 'application/json' },
    body: JSON.stringify({ delivered_kwh: deliveredKwh })
  });

  if (!response.ok) {
    throw new Error(`EVFlow settle charging session failed with status ${response.status}`);
  }

  return response.json() as Promise<ChargingSessionApiResponse>;
}

export async function fetchChargingSession(sessionId: string, fetcher: typeof fetch = fetch) {
  const headers = requireAuthHeaders();
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions/${sessionId}`, { headers });

  if (!response.ok) {
    throw new Error(`EVFlow charging session request failed with status ${response.status}`);
  }

  return response.json() as Promise<ChargingSessionApiResponse>;
}

export async function fetchChargingSessions(limit = 20, fetcher: typeof fetch = fetch) {
  const headers = requireAuthHeaders();
  const response = await fetcher(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions?limit=${limit}`, { headers });

  if (!response.ok) {
    throw new Error(`EVFlow charging sessions request failed with status ${response.status}`);
  }

  return response.json() as Promise<ChargingSessionApiResponse[]>;
}

function requireAuthHeaders() {
  const headers = getAuthHeaders();

  if (!headers) {
    throw new AuthRequiredError();
  }

  return headers;
}
