export const DEFAULT_EVFLOW_API_BASE_URL = 'https://ev-flow-api.opensoft.id';

export function normalizeApiBaseUrl(baseUrl: string | undefined) {
  const trimmed = baseUrl?.trim();
  return trimmed ? trimmed.replace(/\/+$/, '') : DEFAULT_EVFLOW_API_BASE_URL;
}
