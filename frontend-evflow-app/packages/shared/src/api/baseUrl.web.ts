import { LOCAL_BACKEND_PORT, logDevApiBaseUrl, normalizeApiBaseUrl } from './baseUrl.shared';

type ViteImportMeta = ImportMeta & {
  env?: Record<string, string | boolean | undefined>;
};

function pickStringEnv(...values: Array<string | boolean | undefined>) {
  return values.find((value): value is string => typeof value === 'string' && value.trim() !== '');
}

export function getEvflowApiBaseUrl() {
  const env = (import.meta as ViteImportMeta).env;
  const override = pickStringEnv(env?.VITE_EVFLOW_API_BASE_URL, env?.VITE_API_BASE_URL, env?.VITE_API_BASE);

  // In dev builds default to the local backend so frontend work never mutates
  // production data; production builds keep the deployed API as the default.
  if (!override && env?.DEV) {
    const localBaseUrl = normalizeApiBaseUrl(`http://localhost:${LOCAL_BACKEND_PORT}`);
    logDevApiBaseUrl(localBaseUrl, 'VITE_EVFLOW_API_BASE_URL');
    return localBaseUrl;
  }

  const baseUrl = normalizeApiBaseUrl(override);
  if (env?.DEV) {
    logDevApiBaseUrl(baseUrl, 'VITE_EVFLOW_API_BASE_URL');
  }
  return baseUrl;
}
