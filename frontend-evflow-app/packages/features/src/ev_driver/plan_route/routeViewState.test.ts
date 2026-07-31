import { describe, expect, it } from 'vitest';
import { isImmersiveRouteView, showDesktopNavigation, showMobileNavigation, transitionPlannerSheet, transitionRouteView } from './routeViewState';

describe('route view state', () => {
  it.each([
    ['input', 'simulate', 'simulation'],
    ['simulation', 'start_navigation', 'active_navigation'],
    ['active_navigation', 'overview', 'simulation'],
    ['active_navigation', 'end_navigation', 'input'],
    ['active_navigation', 'cancel', 'input'],
    ['active_navigation', 'complete', 'completed'],
    ['completed', 'cancel', 'input'],
  ] as const)('%s + %s -> %s', (current, action, expected) => {
    expect(transitionRouteView(current, action)).toBe(expected);
  });

  it('is immersive only while actively navigating', () => {
    expect(['input', 'simulation', 'completed'].map((mode) => isImmersiveRouteView(mode as any))).toEqual([false, false, false]);
    expect(isImmersiveRouteView('active_navigation')).toBe(true);
  });
  it('hides desktop and mobile global navigation only in immersive mode', () => {
    expect(showDesktopNavigation(true, false)).toBe(true);
    expect(showDesktopNavigation(true, true)).toBe(false);
    expect(showMobileNavigation(false, false, false)).toBe(true);
    expect(showMobileNavigation(false, true, false)).toBe(false);
  });
  it('stores sheet expansion separately from the business route state', () => {
    expect(transitionPlannerSheet('peek', 'open')).toBe('expanded');
    expect(transitionPlannerSheet('peek', 'invalid')).toBe('expanded');
    expect(transitionPlannerSheet('expanded', 'close')).toBe('peek');
  });
});
