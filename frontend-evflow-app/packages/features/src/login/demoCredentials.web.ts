// Demo password for the one-tap quick-access personas, read from the build
// environment. Web (Vite) inlines VITE_* env vars at build time — the value is
// set in the web Containerfile (and a local .env), so it is configurable per
// deployment instead of being a hard-coded literal in source.
//
// This is NOT a real secret: a frontend value always ships inside the bundle,
// and the personas auto-register on the API. Moving it out of source keeps the
// code clean and the value swappable, not hidden.
const viteEnv = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;

export const DEMO_PASSWORD = viteEnv?.VITE_DEMO_PASSWORD ?? '';
