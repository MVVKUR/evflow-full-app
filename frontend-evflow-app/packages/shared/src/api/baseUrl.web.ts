import { normalizeApiBaseUrl } from './baseUrl.shared';

type ViteImportMeta = ImportMeta & {
  env?: Record<string, string | undefined>;
};

export function getEvflowApiBaseUrl() {
  const env = (import.meta as ViteImportMeta).env;

  return normalizeApiBaseUrl(env?.VITE_EVFLOW_API_BASE_URL ?? env?.VITE_API_BASE_URL ?? env?.VITE_API_BASE);
}
