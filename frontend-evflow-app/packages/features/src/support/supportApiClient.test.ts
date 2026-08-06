import { describe, it, expect, vi, beforeEach } from 'vitest';

// support/api imports stations/api -> api/baseUrl -> react-native. Stub it so
// the module graph loads under the node test environment.
vi.mock('react-native', () => ({ NativeModules: {} }));
vi.mock('../../../shared/src/auth/session', () => ({ getAuthHeaders: vi.fn() }));

import { getAuthHeaders } from '../../../shared/src/auth/session';
import { EVFLOW_API_BASE_URL } from '../../../shared/src/stations/api';
import {
  classifySupportStatus,
  SupportRequestError,
  submitSupportTicket,
  toSupportFailureKind,
  toSupportRetryAfterSeconds
} from '../../../shared/src/support/api';

const mockedGetAuthHeaders = vi.mocked(getAuthHeaders);
const ENDPOINT = `${EVFLOW_API_BASE_URL}/api/v1/support/tickets`;
const TICKET = { subject: 'Charger stuck', message: 'It never unlocked.', reply_to: null };

function response(init: {
  ok?: boolean;
  status?: number;
  headers?: Record<string, string>;
  json?: () => Promise<unknown>;
}) {
  const headers = init.headers ?? {};
  return {
    ok: init.ok ?? true,
    status: init.status ?? 202,
    headers: { get: (name: string) => headers[name] ?? null },
    json: init.json ?? (async () => ({ ticket_id: 'abc123', message: 'sent' }))
  } as unknown as Response;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedGetAuthHeaders.mockReturnValue(null);
});

describe('classifySupportStatus', () => {
  it('maps 401 to unauthorized', () => {
    expect(classifySupportStatus(401)).toBe('unauthorized');
  });

  // 403 used to be folded in with 401 here. It is a different condition: this
  // endpoint accepts anonymous callers and so never returns 401, and its only
  // 403 comes from the CORS write-origin guard. Telling the driver their session
  // expired sent them to a login screen that could not fix the problem.
  it('maps 403 to blocked, not unauthorized', () => {
    expect(classifySupportStatus(403)).toBe('blocked');
  });

  it('maps payload rejections to invalid', () => {
    expect(classifySupportStatus(400)).toBe('invalid');
    expect(classifySupportStatus(413)).toBe('invalid');
    expect(classifySupportStatus(422)).toBe('invalid');
  });

  it('maps 429 to rate_limited', () => {
    expect(classifySupportStatus(429)).toBe('rate_limited');
  });

  it('treats a JSON 503 as the API saying support email is unconfigured', () => {
    expect(classifySupportStatus(503, 'application/json')).toBe('email_disabled');
  });

  it('treats an HTML or bodiless 503 as an edge outage, not a mail misconfiguration', () => {
    expect(classifySupportStatus(503, 'text/html')).toBe('server');
    expect(classifySupportStatus(503, null)).toBe('server');
  });

  it('maps a mail relay failure and anything unrecognised to server', () => {
    expect(classifySupportStatus(502)).toBe('server');
    expect(classifySupportStatus(500)).toBe('server');
    expect(classifySupportStatus(418)).toBe('server');
  });
});

describe('submitSupportTicket', () => {
  it('POSTs JSON to the support endpoint and returns the parsed confirmation', async () => {
    const fetcher = vi.fn().mockResolvedValue(response({}));

    const result = await submitSupportTicket(TICKET, fetcher as unknown as typeof fetch);

    expect(fetcher).toHaveBeenCalledWith(ENDPOINT, {
      body: JSON.stringify(TICKET),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST'
    });
    expect(result).toEqual({ ticket_id: 'abc123', message: 'sent' });
  });

  it('attaches the bearer token when the driver is signed in', async () => {
    mockedGetAuthHeaders.mockReturnValue({ Authorization: 'Bearer test-token' });
    const fetcher = vi.fn().mockResolvedValue(response({}));

    await submitSupportTicket(TICKET, fetcher as unknown as typeof fetch);

    expect(fetcher).toHaveBeenCalledWith(
      ENDPOINT,
      expect.objectContaining({
        headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' }
      })
    );
  });

  it('accepts the 202 the API actually returns', async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ status: 202 }));
    await expect(submitSupportTicket(TICKET, fetcher as unknown as typeof fetch)).resolves.toBeTruthy();
  });

  it('reports a rejected request as network, never as a server response', async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(submitSupportTicket(TICKET, fetcher as unknown as typeof fetch)).rejects.toMatchObject({
      kind: 'network',
      status: null
    });
  });

  it('carries the status and Retry-After hint on a 429', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      response({ ok: false, status: 429, headers: { 'Retry-After': '45' } })
    );

    await expect(submitSupportTicket(TICKET, fetcher as unknown as typeof fetch)).rejects.toMatchObject({
      kind: 'rate_limited',
      retryAfterSeconds: 45,
      status: 429
    });
  });

  it('ignores an unusable Retry-After rather than showing a wrong hint', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      response({ ok: false, status: 429, headers: { 'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT' } })
    );

    await expect(submitSupportTicket(TICKET, fetcher as unknown as typeof fetch)).rejects.toMatchObject({
      retryAfterSeconds: null
    });
  });

  it('never puts the server error body into the thrown error message', async () => {
    const leak = 'smtp relay mail.internal rejected sender support@evflow';
    const fetcher = vi.fn().mockResolvedValue(
      response({
        ok: false,
        status: 502,
        headers: { 'Content-Type': 'application/json' },
        json: async () => ({ detail: leak })
      })
    );

    await expect(submitSupportTicket(TICKET, fetcher as unknown as typeof fetch)).rejects.toThrow(
      /^Support ticket request failed \(server, status 502\)$/
    );
  });

  it('treats a 2xx with an unreadable body as success', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      response({
        json: async () => {
          throw new SyntaxError('Unexpected end of JSON input');
        }
      })
    );

    await expect(submitSupportTicket(TICKET, fetcher as unknown as typeof fetch)).resolves.toBeNull();
  });
});

describe('toSupportFailureKind / toSupportRetryAfterSeconds', () => {
  it('reads the kind and hint off a SupportRequestError', () => {
    const error = new SupportRequestError('rate_limited', 429, 30);
    expect(toSupportFailureKind(error)).toBe('rate_limited');
    expect(toSupportRetryAfterSeconds(error)).toBe(30);
  });

  it('falls back to server with no hint for anything else thrown', () => {
    expect(toSupportFailureKind(new Error('boom'))).toBe('server');
    expect(toSupportFailureKind(undefined)).toBe('server');
    expect(toSupportRetryAfterSeconds(new Error('boom'))).toBeNull();
  });
});
