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

  it('offers the fleet operator as selectable', () => {
    const operator = demoPersonas.find((p) => p.key === 'operator');
    expect(operator).toBeDefined();
    expect(operator?.comingSoon).toBeFalsy();
  });

  it('keeps both demo personas selectable', () => {
    expect(demoPersonas.filter((p) => !p.comingSoon).map((p) => p.key)).toEqual(['driver', 'operator']);
  });
});
