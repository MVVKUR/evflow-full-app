import { describe, it, expect, vi, beforeEach } from 'vitest';

// stations/api (imported transitively via ./api) pulls in api/baseUrl, which
// imports react-native. Stub it so the module graph loads in the node env.
vi.mock('react-native', () => ({ NativeModules: {} }));
// Control the auth header state per test without touching real session storage.
vi.mock('../auth/session', () => ({ getAuthHeaders: vi.fn() }));

import { getAuthHeaders } from '../auth/session';
import { EVFLOW_API_BASE_URL } from '../stations/api';
import { AuthRequiredError } from '../wallet/api';
import {
  fetchChargingQuote,
  startChargingSession,
  settleChargingSession,
  fetchChargingSession,
  fetchChargingSessions,
  InsufficientBalanceError
} from './api';

const mockedGetAuthHeaders = vi.mocked(getAuthHeaders);
const AUTH = { Authorization: 'Bearer test-token' };

function response(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body
  } as unknown as Response;
}

function makeFetcher(value: Response) {
  return vi.fn().mockResolvedValue(value) as unknown as typeof fetch;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedGetAuthHeaders.mockReturnValue(AUTH);
});

describe('fetchChargingQuote', () => {
  it('POSTs the energy amount with auth + JSON headers and parses the quote', async () => {
    const quote = { total_due_idr: 15000, currency: 'IDR' };
    const fetcher = makeFetcher(response(quote));

    const result = await fetchChargingQuote(12.5, fetcher);

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/charging/quote`);
    expect(options.method).toBe('POST');
    expect(options.headers).toMatchObject({ ...AUTH, 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual({ energy_kwh: 12.5 });
    expect(result).toEqual(quote);
  });

  it('throws with the status code on a non-ok response', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 500 }));
    await expect(fetchChargingQuote(1, fetcher)).rejects.toThrow(
      'EVFlow charging quote failed with status 500'
    );
  });

  it('throws AuthRequiredError when no auth headers are available', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response({}));
    await expect(fetchChargingQuote(1, fetcher)).rejects.toBeInstanceOf(AuthRequiredError);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe('startChargingSession', () => {
  it('POSTs the session payload, defaulting optional fields to null', async () => {
    const session = { id: 'sess-1', status: 'active' };
    const fetcher = makeFetcher(response(session));

    const result = await startChargingSession(
      { stationId: 'station-1', energyKwh: 8 },
      fetcher
    );

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions`);
    expect(options.method).toBe('POST');
    expect(options.headers).toMatchObject({ ...AUTH, 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual({
      station_id: 'station-1',
      energy_kwh: 8,
      station_name: null,
      connector_type: null,
      power_kw: null
    });
    expect(result).toEqual(session);
  });

  it('passes through provided optional fields', async () => {
    const fetcher = makeFetcher(response({ id: 'sess-2' }));

    await startChargingSession(
      {
        stationId: 'station-2',
        energyKwh: 10,
        stationName: 'PLN Sudirman',
        connectorType: 'CCS2',
        powerKw: 50
      },
      fetcher
    );

    const [, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      station_id: 'station-2',
      energy_kwh: 10,
      station_name: 'PLN Sudirman',
      connector_type: 'CCS2',
      power_kw: 50
    });
  });

  it('throws InsufficientBalanceError on HTTP 402', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 402 }));
    await expect(
      startChargingSession({ stationId: 's', energyKwh: 1 }, fetcher)
    ).rejects.toBeInstanceOf(InsufficientBalanceError);
  });

  it('throws with the status code on other non-ok responses', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 500 }));
    await expect(
      startChargingSession({ stationId: 's', energyKwh: 1 }, fetcher)
    ).rejects.toThrow('EVFlow start charging session failed with status 500');
  });

  it('throws AuthRequiredError when unauthenticated', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response({}));
    await expect(
      startChargingSession({ stationId: 's', energyKwh: 1 }, fetcher)
    ).rejects.toBeInstanceOf(AuthRequiredError);
  });
});

describe('settleChargingSession', () => {
  it('POSTs the delivered energy to the settle endpoint', async () => {
    const session = { id: 'sess-1', status: 'completed' };
    const fetcher = makeFetcher(response(session));

    const result = await settleChargingSession('sess-1', 7.25, fetcher);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions/sess-1/settle`);
    expect(options.method).toBe('POST');
    expect(options.headers).toMatchObject({ ...AUTH, 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual({ delivered_kwh: 7.25 });
    expect(result).toEqual(session);
  });

  it('throws with the status code on a non-ok response', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 409 }));
    await expect(settleChargingSession('sess-1', 1, fetcher)).rejects.toThrow(
      'EVFlow settle charging session failed with status 409'
    );
  });

  it('throws AuthRequiredError when unauthenticated', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response({}));
    await expect(settleChargingSession('sess-1', 1, fetcher)).rejects.toBeInstanceOf(
      AuthRequiredError
    );
  });
});

describe('fetchChargingSession', () => {
  it('GETs a single session with auth headers', async () => {
    const session = { id: 'sess-9' };
    const fetcher = makeFetcher(response(session));

    const result = await fetchChargingSession('sess-9', fetcher);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions/sess-9`);
    expect(options.method).toBeUndefined();
    expect(options.headers).toMatchObject(AUTH);
    expect(result).toEqual(session);
  });

  it('throws with the status code on a non-ok response', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 404 }));
    await expect(fetchChargingSession('missing', fetcher)).rejects.toThrow(
      'EVFlow charging session request failed with status 404'
    );
  });

  it('throws AuthRequiredError when unauthenticated', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response({}));
    await expect(fetchChargingSession('sess-9', fetcher)).rejects.toBeInstanceOf(
      AuthRequiredError
    );
  });
});

describe('fetchChargingSessions', () => {
  it('GETs the list with the default limit of 20', async () => {
    const sessions = [{ id: 'a' }, { id: 'b' }];
    const fetcher = makeFetcher(response(sessions));

    const result = await fetchChargingSessions(undefined, fetcher);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions?limit=20`);
    expect(options.headers).toMatchObject(AUTH);
    expect(result).toEqual(sessions);
  });

  it('GETs the list with a custom limit', async () => {
    const fetcher = makeFetcher(response([]));
    await fetchChargingSessions(5, fetcher);
    const [url] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/charging/sessions?limit=5`);
  });

  it('throws with the status code on a non-ok response', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 500 }));
    await expect(fetchChargingSessions(20, fetcher)).rejects.toThrow(
      'EVFlow charging sessions request failed with status 500'
    );
  });

  it('throws AuthRequiredError when unauthenticated', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response([]));
    await expect(fetchChargingSessions(20, fetcher)).rejects.toBeInstanceOf(AuthRequiredError);
  });
});

describe('InsufficientBalanceError', () => {
  it('carries the default message and name', () => {
    const error = new InsufficientBalanceError();
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe('InsufficientBalanceError');
    expect(error.message).toContain('Insufficient wallet balance');
  });
});
