// Native (Expo / Metro) counterpart of demoCredentials.web.ts. Expo exposes
// build-time env vars prefixed EXPO_PUBLIC_* on process.env. See the web file
// for why this is intentionally not a hard-coded secret.
export const DEMO_PASSWORD =
  (typeof process !== 'undefined' ? process.env?.EXPO_PUBLIC_DEMO_PASSWORD : undefined) ?? '';
