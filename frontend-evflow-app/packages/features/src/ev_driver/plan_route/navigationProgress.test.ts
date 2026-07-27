import { describe, expect, it } from 'vitest';
import { advanceStep, isOffRoute, maneuverDistances, matchRoute, monotonicDistance } from './navigationProgress';

describe('navigation progress', () => {
  const line: [number, number][] = [[106.0, -6.0], [106.01, -6.0], [106.02, -6.0]];
  it('matches a fix and reports decreasing remaining distance', () => {
    const early = matchRoute({ latitude: -6, longitude: 106.002 }, line);
    const late = matchRoute({ latitude: -6, longitude: 106.015 }, line);
    expect(early.distanceM).toBeLessThan(2);
    expect(late.remainingM).toBeLessThan(early.remainingM);
  });
  it('advances after passing a maneuver', () => {
    const steps = [{ instruction: 'depart', location: [106, -6] as [number, number] }, { instruction: 'turn', location: [106.01, -6] as [number, number] }, { instruction: 'arrive', location: [106.02, -6] as [number, number] }];
    const distances = maneuverDistances(steps, line);
    expect(advanceStep(steps, 0, { latitude: -6, longitude: 106.015 }, matchRoute({ latitude: -6, longitude: 106.015 }, line).travelledM, distances)).toBe(1);
  });
  it('advances when a GPS jump crosses a maneuver without entering its radius', () => {
    const steps = [{ instruction: 'depart', location: [106, -6] as [number, number] }, { instruction: 'turn', location: [106.01, -6] as [number, number] }, { instruction: 'arrive', location: [106.02, -6] as [number, number] }];
    expect(advanceStep(steps, 0, { latitude: -6, longitude: 106.018 }, matchRoute({ latitude: -6, longitude: 106.018 }, line).travelledM, maneuverDistances(steps, line))).toBe(1);
  });
  it('requires three consecutive off-route fixes', () => {
    expect(isOffRoute(2)).toBe(false);
    expect(isOffRoute(3)).toBe(true);
  });
  it('never lets cumulative travelled distance move backwards', () => {
    expect(monotonicDistance(12, 8)).toBe(12);
  });
});
