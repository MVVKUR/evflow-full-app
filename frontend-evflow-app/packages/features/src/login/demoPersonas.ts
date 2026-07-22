import { AuthApiError, login, register, saveAuthSession, type TokenResponse } from '@evflow/shared';

export type DemoPersonaKey = 'driver' | 'operator';

export type DemoPersona = {
  key: DemoPersonaKey;
  username: string;
  fullName: string;
  initials: string;
  subtitle: string;
  avatarColor: string;
  subtitleColor: string;
};

// Deliberately public demo credential: the quick-access personas exist purely so
// demo-day reviewers can sign in with one tap. Never reuse this for real accounts.
export const DEMO_PASSWORD = 'evflow-demo-2026';

export const demoPersonas: readonly DemoPersona[] = [
  {
    key: 'driver',
    username: 'rizki',
    fullName: 'Muhammad Rizki',
    initials: 'MR',
    subtitle: 'EV Driver · Personal Account',
    avatarColor: '#00696F',
    subtitleColor: '#00696F'
  },
  {
    key: 'operator',
    username: 'fleet.operator',
    fullName: 'Fleet Operator',
    initials: 'FO',
    subtitle: 'Business Planner · Jabodetabek',
    avatarColor: '#00565F',
    subtitleColor: '#0DA6AF'
  }
];

/**
 * Signs the persona in, transparently registering the demo account on first use.
 * Throws AuthApiError (status 409 means the username exists with a different
 * password) or a network error when the API is unreachable.
 */
export async function ensureDemoSession(persona: DemoPersona): Promise<TokenResponse> {
  try {
    const session = await login({ password: DEMO_PASSWORD, username: persona.username });
    saveAuthSession(session);
    return session;
  } catch (error: unknown) {
    const isUnknownCredentials = error instanceof AuthApiError && error.status === 401;

    if (!isUnknownCredentials) {
      throw error;
    }
  }

  const session = await register({
    full_name: persona.fullName,
    password: DEMO_PASSWORD,
    username: persona.username
  });
  saveAuthSession(session);
  return session;
}
