export type RouteFieldErrors = Record<string, string>;

export class RouteApiError extends Error {
  readonly status: number | null;
  readonly code?: string;
  readonly fieldErrors: RouteFieldErrors;
  readonly safeDetail?: unknown;
  readonly isNetworkError: boolean;
  constructor(input: { message: string; status?: number | null; code?: string; fieldErrors?: RouteFieldErrors; safeDetail?: unknown; isNetworkError?: boolean }) {
    super(input.message); this.name = 'RouteApiError'; this.status = input.status ?? null; this.code = input.code; this.fieldErrors = input.fieldErrors ?? {}; this.safeDetail = input.safeDetail; this.isNetworkError = input.isNetworkError ?? false;
  }
}

const fieldAliases: Record<string, string> = { origin: 'origin', destination: 'destination', current_soc_pct: 'current_soc_pct', minimum_arrival_soc_pct: 'minimum_arrival_soc_pct', ev_model_id: 'vehicle', vehicle: 'vehicle', usable_range_km: 'vehicle', preferences: 'preferences' };
function safeMessage(value: unknown, fallback: string): string { if (typeof value === 'string' && value.trim()) return value; if (value && typeof value === 'object') { const candidate = value as Record<string, unknown>; if (typeof candidate.message === 'string') return candidate.message; if (typeof candidate.msg === 'string') return candidate.msg; } return fallback; }

export function normaliseRouteApiError(status: number, payload: unknown, fallback: string): RouteApiError {
  const body = payload && typeof payload === 'object' ? payload as Record<string, unknown> : {};
  const detail = body.detail; const fieldErrors: RouteFieldErrors = {}; let message = safeMessage(detail, safeMessage(body.message, fallback)); let code = typeof body.code === 'string' ? body.code : undefined;
  if (Array.isArray(detail)) {
    for (const issue of detail) { if (!issue || typeof issue !== 'object') continue; const item = issue as Record<string, unknown>; const loc = Array.isArray(item.loc) ? item.loc.map(String) : []; const rawField = [...loc].reverse().find((part) => fieldAliases[part]); const field = rawField ? fieldAliases[rawField] : undefined; const issueMessage = safeMessage(item.msg, 'Invalid value'); if (field && !fieldErrors[field]) fieldErrors[field] = issueMessage; }
    message = Object.keys(fieldErrors).length ? 'Fix the highlighted route details.' : fallback;
  } else if (detail && typeof detail === 'object') {
    const detailObject = detail as Record<string, unknown>; code = typeof detailObject.code === 'string' ? detailObject.code : code; message = safeMessage(detailObject, fallback); const backendFields = detailObject.field_errors;
    if (backendFields && typeof backendFields === 'object' && !Array.isArray(backendFields)) for (const [rawField, rawMessage] of Object.entries(backendFields as Record<string, unknown>)) fieldErrors[fieldAliases[rawField] ?? rawField] = safeMessage(rawMessage, 'Invalid value');
  }
  const safeDetail = Array.isArray(detail)
    ? detail.map((issue) => issue && typeof issue === 'object' ? { loc: (issue as Record<string, unknown>).loc, msg: (issue as Record<string, unknown>).msg, type: (issue as Record<string, unknown>).type } : issue)
    : detail && typeof detail === 'object'
      ? { code: (detail as Record<string, unknown>).code, message: (detail as Record<string, unknown>).message, field_errors: (detail as Record<string, unknown>).field_errors }
      : detail;
  return new RouteApiError({ status, message, code, fieldErrors, safeDetail });
}
