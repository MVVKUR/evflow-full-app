import { describe, expect, it, vi } from 'vitest';

// @evflow/shared reaches react-native for session storage, whose Flow syntax
// vitest cannot parse. The persona table itself needs none of it.
vi.mock('react-native', () => ({ NativeModules: {}, Platform: { OS: 'web' } }));
vi.mock('@evflow/shared', () => ({
  AuthApiError: class extends Error {},
  login: vi.fn(),
  register: vi.fn(),
  saveAuthSession: vi.fn()
}));

import { demoPersonas } from './demoPersonas';

describe('demo personas', () => {
  it('offers the EV driver as selectable', () => {
    const driver = demoPersonas.find((p) => p.key === 'driver');
    expect(driver).toBeDefined();
    expect(driver?.comingSoon).toBeFalsy();
  });

  // Iteration 2 ships without the business-planner surface. The persona stays
  // visible so the role is discoverable, but it must never be signable-in:
  // logging in would land on /business/dashboard, which is not part of this
  // release.
  it('marks the fleet operator as coming soon so it cannot be signed into', () => {
    const operator = demoPersonas.find((p) => p.key === 'operator');
    expect(operator).toBeDefined();
    expect(operator?.comingSoon).toBe(true);
  });

  it('keeps exactly one selectable persona in this release', () => {
    expect(demoPersonas.filter((p) => !p.comingSoon).map((p) => p.key)).toEqual(['driver']);
  });
});
