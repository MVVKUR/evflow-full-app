import { describe, it, expect, vi, beforeEach } from 'vitest';

// wallet/api imports stations/api -> api/baseUrl -> react-native. Stub it so
// the module graph loads under the node test environment.
vi.mock('react-native', () => ({ NativeModules: {} }));
vi.mock('../auth/session', () => ({ getAuthHeaders: vi.fn() }));

import { getAuthHeaders } from '../auth/session';
import { EVFLOW_API_BASE_URL } from '../stations/api';
import {
  fetchWalletBalance,
  createWalletTopup,
  fetchWalletTopup,
  fetchWalletTopups,
  AuthRequiredError
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

describe('fetchWalletBalance', () => {
  it('GETs the wallet endpoint with auth headers and parses the balance', async () => {
    const balance = { balance_idr: 50000, currency: 'IDR', updated_at: '2026-07-23' };
    const fetcher = makeFetcher(response(balance));

    const result = await fetchWalletBalance(fetcher);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/wallet`);
    expect(options.headers).toMatchObject(AUTH);
    expect(result).toEqual(balance);
  });

  it('throws with the status code on a non-ok response', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 500 }));
    await expect(fetchWalletBalance(fetcher)).rejects.toThrow(
      'EVFlow wallet request failed with status 500'
    );
  });

  it('throws AuthRequiredError when unauthenticated', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response({}));
    await expect(fetchWalletBalance(fetcher)).rejects.toBeInstanceOf(AuthRequiredError);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe('createWalletTopup', () => {
  it('POSTs the top-up amount with auth + JSON headers and parses the invoice', async () => {
    const created = {
      topup_id: 'top-1',
      amount_idr: 100000,
      status: 'PENDING',
      invoice_url: 'https://pay.test/inv'
    };
    const fetcher = makeFetcher(response(created));

    const result = await createWalletTopup(100000, fetcher);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/wallet/topup`);
    expect(options.method).toBe('POST');
    expect(options.headers).toMatchObject({ ...AUTH, 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual({ amount_idr: 100000 });
    expect(result).toEqual(created);
  });

  it('throws with the status code on a non-ok response', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 422 }));
    await expect(createWalletTopup(100000, fetcher)).rejects.toThrow(
      'EVFlow wallet top-up request failed with status 422'
    );
  });

  it('throws AuthRequiredError when unauthenticated', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response({}));
    await expect(createWalletTopup(100000, fetcher)).rejects.toBeInstanceOf(AuthRequiredError);
  });
});

describe('fetchWalletTopup', () => {
  it('GETs a single top-up by id with auth headers', async () => {
    const topup = { id: 'top-1', status: 'PAID' };
    const fetcher = makeFetcher(response(topup));

    const result = await fetchWalletTopup('top-1', fetcher);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/wallet/topups/top-1`);
    expect(options.headers).toMatchObject(AUTH);
    expect(result).toEqual(topup);
  });

  it('throws with the status code on a non-ok response', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 404 }));
    await expect(fetchWalletTopup('missing', fetcher)).rejects.toThrow(
      'EVFlow wallet top-up status request failed with status 404'
    );
  });

  it('throws AuthRequiredError when unauthenticated', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response({}));
    await expect(fetchWalletTopup('top-1', fetcher)).rejects.toBeInstanceOf(AuthRequiredError);
  });
});

describe('fetchWalletTopups', () => {
  it('GETs the list with the default limit query', async () => {
    const topups = [{ id: 'a' }, { id: 'b' }];
    const fetcher = makeFetcher(response(topups));

    const result = await fetchWalletTopups(undefined, fetcher);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/wallet/topups?limit=20`);
    expect(options.headers).toMatchObject(AUTH);
    expect(result).toEqual(topups);
  });

  it('GETs the list with a custom limit query', async () => {
    const fetcher = makeFetcher(response([]));
    await fetchWalletTopups(3, fetcher);
    const [url] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/wallet/topups?limit=3`);
  });

  it('throws with the status code on a non-ok response', async () => {
    const fetcher = makeFetcher(response({}, { ok: false, status: 500 }));
    await expect(fetchWalletTopups(20, fetcher)).rejects.toThrow(
      'EVFlow wallet top-ups request failed with status 500'
    );
  });

  it('throws AuthRequiredError when unauthenticated', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = makeFetcher(response([]));
    await expect(fetchWalletTopups(20, fetcher)).rejects.toBeInstanceOf(AuthRequiredError);
  });
});

describe('AuthRequiredError', () => {
  it('carries the default message and name', () => {
    const error = new AuthRequiredError();
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe('AuthRequiredError');
    expect(error.message).toContain('log in');
  });
});
