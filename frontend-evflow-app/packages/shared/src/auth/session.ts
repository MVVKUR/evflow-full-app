import type { TokenResponse } from './api';

const sessionKey = 'evflow.auth.session';
let memorySession: TokenResponse | null = null;

export function saveAuthSession(session: TokenResponse) {
  memorySession = session;

  try {
    getSessionStorage()?.setItem(sessionKey, JSON.stringify(session));
  } catch {
    // Native and restricted browsers can fall back to the in-memory cache.
  }
}

export function getAuthSession() {
  if (memorySession) {
    return memorySession;
  }

  try {
    const rawSession = getSessionStorage()?.getItem(sessionKey);

    if (!rawSession) {
      return null;
    }

    memorySession = JSON.parse(rawSession) as TokenResponse;
    return memorySession;
  } catch {
    return null;
  }
}

export function clearAuthSession() {
  memorySession = null;

  try {
    getSessionStorage()?.removeItem(sessionKey);
  } catch {
    // Native and restricted browsers can fall back to the in-memory cache.
  }
}

function getSessionStorage() {
  if (typeof globalThis === 'undefined') {
    return null;
  }

  return globalThis.sessionStorage ?? null;
}
