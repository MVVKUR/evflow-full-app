import { describe, it, expect, vi, afterEach } from 'vitest';

import { DEFAULT_EVFLOW_API_BASE_URL, normalizeApiBaseUrl, logDevApiBaseUrl } from './baseUrl.shared';

describe('normalizeApiBaseUrl', () => {
  it('falls back to the default when the value is undefined or empty', () => {
    expect(normalizeApiBaseUrl(undefined)).toBe(DEFAULT_EVFLOW_API_BASE_URL);
    expect(normalizeApiBaseUrl('')).toBe(DEFAULT_EVFLOW_API_BASE_URL);
    expect(normalizeApiBaseUrl('   ')).toBe(DEFAULT_EVFLOW_API_BASE_URL);
  });

  it('treats a lone "/" as same-origin (empty base URL)', () => {
    expect(normalizeApiBaseUrl('/')).toBe('');
  });

  it('strips trailing slashes', () => {
    expect(normalizeApiBaseUrl('https://api.example.com/')).toBe('https://api.example.com');
    expect(normalizeApiBaseUrl('https://api.example.com///')).toBe('https://api.example.com');
    expect(normalizeApiBaseUrl('  https://api.example.com/  ')).toBe('https://api.example.com');
  });

  it('passes a well-formed base URL through unchanged', () => {
    expect(normalizeApiBaseUrl('https://api.example.com')).toBe('https://api.example.com');
  });
});

describe('logDevApiBaseUrl', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('logs the first time and deduplicates repeat calls for the same URL', () => {
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {});

    // Use a unique URL so this assertion is independent of the module-level
    // dedup cache, which persists across tests within the process.
    const url = `https://dedup-${Date.now()}.example.com`;
    logDevApiBaseUrl(url, 'EVFLOW_API_BASE_URL');
    logDevApiBaseUrl(url, 'EVFLOW_API_BASE_URL');

    expect(infoSpy).toHaveBeenCalledTimes(1);
    expect(infoSpy).toHaveBeenCalledWith(expect.stringContaining(url));
    expect(infoSpy).toHaveBeenCalledWith(expect.stringContaining('EVFLOW_API_BASE_URL'));
  });

  it('logs again when the base URL changes', () => {
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {});

    logDevApiBaseUrl(`https://a-${Date.now()}.example.com`, 'EVFLOW_API_BASE_URL');
    logDevApiBaseUrl(`https://b-${Date.now()}.example.com`, 'EVFLOW_API_BASE_URL');

    expect(infoSpy).toHaveBeenCalledTimes(2);
  });
});
