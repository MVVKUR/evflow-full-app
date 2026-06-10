import { NativeModules } from 'react-native';
import { LOCAL_BACKEND_PORT, logDevApiBaseUrl, normalizeApiBaseUrl } from './baseUrl.shared';

declare const __DEV__: boolean | undefined;

type RuntimeGlobal = typeof globalThis & {
  process?: {
    env?: Record<string, string | undefined>;
  };
};

type SourceCodeModule = {
  scriptURL?: string;
  getConstants?: () => { scriptURL?: string };
};

const LOCAL_HOST_PATTERN =
  /^(localhost|\[::1\]|127(\.\d{1,3}){3}|10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2})$/;

function getBundleScriptUrl() {
  const sourceCode = (NativeModules as { SourceCode?: SourceCodeModule | null } | undefined)?.SourceCode;
  try {
    // The New Architecture (TurboModules, default in Expo Go SDK 52+) exposes
    // native constants only via getConstants(); the legacy bridge hoists
    // scriptURL directly onto the module object.
    return sourceCode?.getConstants?.().scriptURL ?? sourceCode?.scriptURL;
  } catch {
    return undefined;
  }
}

// Metro serves the JS bundle from the dev machine, so the bundle URL host
// (LAN IP for a physical device, localhost/10.0.2.2 for emulators) is a host
// the device can also use to reach the local backend.
function getDevServerHost() {
  const scriptURL = getBundleScriptUrl();
  if (!scriptURL) {
    return undefined;
  }
  const host = scriptURL.match(/^https?:\/\/(\[[^\]]+\]|[^:/]+)/)?.[1];
  // Tunnel mode (expo start --tunnel) serves the bundle from a public
  // ngrok/exp.direct host that does not route to the local backend, so only
  // loopback/LAN/emulator hosts qualify; anything else falls back to the
  // deployed API.
  if (!host || !LOCAL_HOST_PATTERN.test(host)) {
    return undefined;
  }
  return host;
}

export function getEvflowApiBaseUrl() {
  const env = (globalThis as RuntimeGlobal).process?.env;
  const override =
    env?.EXPO_PUBLIC_EVFLOW_API_BASE_URL ?? env?.EXPO_PUBLIC_API_BASE_URL ?? env?.EVFLOW_API_BASE_URL;

  const isDev = typeof __DEV__ !== 'undefined' && __DEV__ === true;

  // In dev default to the backend running on the dev machine so frontend work
  // never mutates production data; release builds keep the deployed API.
  if (!override?.trim() && isDev) {
    const devHost = getDevServerHost();
    if (devHost) {
      const localBaseUrl = normalizeApiBaseUrl(`http://${devHost}:${LOCAL_BACKEND_PORT}`);
      logDevApiBaseUrl(localBaseUrl, 'EXPO_PUBLIC_EVFLOW_API_BASE_URL');
      return localBaseUrl;
    }
  }

  const baseUrl = normalizeApiBaseUrl(override);
  if (isDev) {
    logDevApiBaseUrl(baseUrl, 'EXPO_PUBLIC_EVFLOW_API_BASE_URL');
  }
  return baseUrl;
}
