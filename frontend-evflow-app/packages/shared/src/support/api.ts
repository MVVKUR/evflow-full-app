import { EVFLOW_API_BASE_URL } from '../stations/api';
import { getAuthHeaders } from '../auth/session';

const SUPPORT_TICKETS_PATH = '/api/v1/support/tickets';

export type SupportTicketRequest = {
  subject: string;
  message: string;
  reply_to?: string | null;
};

export type SupportTicketResponse = {
  ticket_id: string;
  message: string;
};

export type SupportFailureKind =
  | 'network'
  | 'unauthorized'
  | 'blocked'
  | 'invalid'
  | 'email_disabled'
  | 'rate_limited'
  | 'server';

export class SupportRequestError extends Error {
  readonly kind: SupportFailureKind;
  readonly status: number | null;
  readonly retryAfterSeconds: number | null;

  constructor(kind: SupportFailureKind, status: number | null = null, retryAfterSeconds: number | null = null) {
    // This message is for logs only. The screen picks its copy from `kind`, so
    // a server error body can never be rendered to the driver.
    super(`Support ticket request failed (${kind}${status === null ? '' : `, status ${status}`})`);
    this.name = 'SupportRequestError';
    this.kind = kind;
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export function classifySupportStatus(status: number, contentType: string | null = null): SupportFailureKind {
  // 403 here is NOT an expired session. The support endpoint accepts anonymous
  // callers, so it can never return 401 -- optional_current_user swallows auth
  // failures. The only 403 it produces is the CORS write-origin guard, which
  // means the request came from an origin the API does not trust. Telling the
  // driver to log in would send them round a loop that cannot fix it.
  if (status === 403) {
    return 'blocked';
  }

  if (status === 401) {
    return 'unauthorized';
  }

  if (status === 400 || status === 413 || status === 422) {
    return 'invalid';
  }

  if (status === 429) {
    return 'rate_limited';
  }

  // The endpoint answers 503 specifically when SMTP is not configured. nginx and
  // Cloudflare also answer 503 when the API container is down, and telling a
  // driver "email is not set up" then would send them away from a fault that
  // fixes itself. Only the API's own JSON 503 means the mailer is unconfigured;
  // an HTML (or bodiless) 503 came from the edge and is a plain outage.
  if (status === 503) {
    return isJsonContentType(contentType) ? 'email_disabled' : 'server';
  }

  return 'server';
}

function isJsonContentType(contentType: string | null): boolean {
  return contentType !== null && contentType.toLowerCase().includes('json');
}

export function toSupportFailureKind(error: unknown): SupportFailureKind {
  return error instanceof SupportRequestError ? error.kind : 'server';
}

export function toSupportRetryAfterSeconds(error: unknown): number | null {
  return error instanceof SupportRequestError ? error.retryAfterSeconds : null;
}

// Resolves with the API's confirmation, or null when the accepted response had
// no readable body. Rejects only with SupportRequestError.
export async function submitSupportTicket(
  request: SupportTicketRequest,
  fetcher: typeof fetch = fetch
): Promise<SupportTicketResponse | null> {
  const authHeaders = getAuthHeaders();
  let response: Response;

  try {
    response = await fetcher(`${EVFLOW_API_BASE_URL}${SUPPORT_TICKETS_PATH}`, {
      body: JSON.stringify(request),
      headers: {
        ...(authHeaders ?? {}),
        'Content-Type': 'application/json'
      },
      method: 'POST'
    });
  } catch {
    // fetch only rejects when the request never completed (offline, DNS, TLS),
    // so this branch is always connectivity and never an API response.
    throw new SupportRequestError('network');
  }

  if (!response.ok) {
    // Headers only: reading the body would put the server's own error text one
    // assignment away from the screen.
    const headers = response.headers ?? null;
    throw new SupportRequestError(
      classifySupportStatus(response.status, headers?.get('Content-Type') ?? null),
      response.status,
      parseRetryAfterSeconds(headers?.get('Retry-After') ?? null)
    );
  }

  try {
    return (await response.json()) as SupportTicketResponse;
  } catch {
    // A 2xx with an unreadable body still means the ticket was accepted.
    return null;
  }
}

// Only the delta-seconds form is honoured. The HTTP-date form would need clock
// agreement between device and server, and a wrong hint is worse than none.
function parseRetryAfterSeconds(headerValue: string | null): number | null {
  if (!headerValue) {
    return null;
  }

  const seconds = Number(headerValue.trim());
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return null;
  }

  return Math.ceil(seconds);
}
