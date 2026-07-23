export const DEFAULT_EVFLOW_API_BASE_URL = 'https://ev-flow-api.opensoft.id';

export const LOCAL_BACKEND_PORT = 8000;

export function normalizeApiBaseUrl(baseUrl: string | undefined) {
  const trimmed = baseUrl?.trim();
  if (!trimmed) {
    return DEFAULT_EVFLOW_API_BASE_URL;
  }
  // "/" means same-origin: the API is served on the web origin (e.g. behind a
  // reverse proxy), so requests use relative paths like /api/v1/...
  if (trimmed === '/') {
    return '';
  }
  // Strip trailing slashes without a regex (linear scan; no backtracking).
  let end = trimmed.length;
  while (end > 0 && trimmed[end - 1] === '/') {
    end -= 1;
  }
  return trimmed.slice(0, end);
}

let lastLoggedBaseUrl: string | null = null;

export function logDevApiBaseUrl(baseUrl: string, overrideEnvVar: string) {
  if (lastLoggedBaseUrl === baseUrl) {
    return;
  }
  lastLoggedBaseUrl = baseUrl;
  console.info(`[evflow] dev mode: API base URL is ${baseUrl} (set ${overrideEnvVar} to override)`);
}
