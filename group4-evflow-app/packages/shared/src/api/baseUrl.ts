import { normalizeApiBaseUrl } from './baseUrl.shared';

type RuntimeGlobal = typeof globalThis & {
  process?: {
    env?: Record<string, string | undefined>;
  };
};

export function getEvflowApiBaseUrl() {
  const env = (globalThis as RuntimeGlobal).process?.env;

  return normalizeApiBaseUrl(
    env?.EXPO_PUBLIC_EVFLOW_API_BASE_URL ?? env?.EXPO_PUBLIC_API_BASE_URL ?? env?.EVFLOW_API_BASE_URL
  );
}
