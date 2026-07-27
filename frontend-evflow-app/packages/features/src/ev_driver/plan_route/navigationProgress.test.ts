import { describe, expect, it } from 'vitest';
import { advanceStep, isOffRoute, matchRoute } from './navigationProgress';

describe('navigation progress', () => {
  const line: [number, number][] = [[106.0, -6.0], [106.01, -6.0], [106.02, -6.0]];
  it('matches a fix and reports decreasing remaining distance', () => {
    const early = matchRoute({ latitude: -6, longitude: 106.002 }, line);
    const late = matchRoute({ latitude: -6, longitude: 106.015 }, line);
    expect(early.distanceM).toBeLessThan(2);
    expect(late.remainingM).toBeLessThan(early.remainingM);
  });
  it('advances after passing a maneuver', () => {
    expect(advanceStep([{ instruction: 'turn', location: [106.01, -6] }, { instruction: 'arrive' }], 0, { latitude: -6, longitude: 106.01 })).toBe(1);
  });
  it('requires three consecutive off-route fixes', () => {
    expect(isOffRoute(2)).toBe(false);
    expect(isOffRoute(3)).toBe(true);
  });
});
