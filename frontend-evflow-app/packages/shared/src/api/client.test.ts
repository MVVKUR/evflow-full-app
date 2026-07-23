import { describe, it, expect, vi } from 'vitest';

import { createApiClient, toQueryString } from './client';

describe('toQueryString', () => {
  it('returns an empty string when there are no params', () => {
    expect(toQueryString({})).toBe('');
  });

  it('serialises string and number values', () => {
    expect(toQueryString({ q: 'chademo', limit: 20 })).toBe('?q=chademo&limit=20');
  });

  it('serialises boolean values', () => {
    expect(toQueryString({ verified: true })).toBe('?verified=true');
  });

  it('omits undefined, null and empty-string values', () => {
    expect(
      toQueryString({ a: 'keep', b: undefined, c: null, d: '' })
    ).toBe('?a=keep');
  });

  it('appends each array item under the same key and skips empty items', () => {
    expect(toQueryString({ connector: ['ccs', 'chademo', ''] })).toBe(
      '?connector=ccs&connector=chademo'
    );
  });

  it('returns an empty string when every value is omitted', () => {
    expect(toQueryString({ a: undefined, b: null, c: '' })).toBe('');
  });
});

describe('createApiClient', () => {
  it('performs a GET against baseUrl + path and returns parsed JSON', async () => {
    const payload = { total: 3 };
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload
    });

    const client = createApiClient({ baseUrl: 'https://api.test', fetcher: fetcher as unknown as typeof fetch });
    const result = await client.get<typeof payload>('/api/v1/stats');

    expect(fetcher).toHaveBeenCalledWith('https://api.test/api/v1/stats');
    expect(result).toEqual(payload);
  });

  it('throws with the status code when the response is not ok', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({})
    });

    const client = createApiClient({ baseUrl: 'https://api.test', fetcher: fetcher as unknown as typeof fetch });

    await expect(client.get('/api/v1/stats')).rejects.toThrow(
      'EVFlow API request failed with status 503'
    );
  });
});
