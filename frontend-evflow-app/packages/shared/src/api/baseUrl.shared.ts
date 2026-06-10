export const DEFAULT_EVFLOW_API_BASE_URL = 'https://ev-flow-api.opensoft.id';

export const LOCAL_BACKEND_PORT = 8000;

export function normalizeApiBaseUrl(baseUrl: string | undefined) {
  const trimmed = baseUrl?.trim();
  return trimmed ? trimmed.replace(/\/+$/, '') : DEFAULT_EVFLOW_API_BASE_URL;
}

let lastLoggedBaseUrl: string | null = null;

export function logDevApiBaseUrl(baseUrl: string, overrideEnvVar: string) {
  if (lastLoggedBaseUrl === baseUrl) {
    return;
  }
  lastLoggedBaseUrl = baseUrl;
  console.info(`[evflow] dev mode: API base URL is ${baseUrl} (set ${overrideEnvVar} to override)`);
}
