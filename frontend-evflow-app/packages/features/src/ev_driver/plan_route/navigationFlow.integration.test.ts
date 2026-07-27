import { describe, expect, it, vi } from 'vitest';
import { NavigationWatcherSession, createRouteSessionCleaner } from './navigationSession';
import { advanceStep, isOffRoute, maneuverDistances, matchRoute } from './navigationProgress';
import { isImmersiveRouteView, transitionRouteView } from './routeViewState';

describe('mocked active-navigation movement flow', () => {
  it('moves, advances, reroutes, pauses, resumes, ends, and deletes the route', async () => {
    type Fix = { latitude: number; longitude: number };
    const line: [number, number][] = [[106, -6], [106.01, -6], [106.02, -6]];
    const steps = [
      { instruction: 'depart', location: [106, -6] as [number, number] },
      { instruction: 'turn right', location: [106.01, -6] as [number, number] },
      { instruction: 'arrive', location: [106.02, -6] as [number, number] },
    ];
    const along = maneuverDistances(steps, line);
    const remove = vi.fn();
    let emit: ((fix: Fix) => void) | undefined;
    const watch = vi.fn(async (onFix: (fix: Fix) => void) => { emit = onFix; return { remove }; });
    const deleteRequest = vi.fn(async () => undefined);
    const cleanup = createRouteSessionCleaner(deleteRequest);
    let mode = transitionRouteView('simulation', 'start_navigation');
    let remainingM = Infinity;
    let stepIndex = 0;
    let estimatedCurrentSoc = 72;
    let projectedArrivalSoc = 44;
    let offRouteFixes = 0;
    let reroutes = 0;

    const active = new NavigationWatcherSession<Fix>(watch);
    await active.start((fix) => {
      const matched = matchRoute(fix, line);
      remainingM = matched.remainingM;
      stepIndex = advanceStep(steps, stepIndex, matched.point, matched.travelledM, along);
      offRouteFixes = matched.distanceM > 50 ? offRouteFixes + 1 : 0;
      if (isOffRoute(offRouteFixes)) reroutes += 1;
      estimatedCurrentSoc = Math.min(estimatedCurrentSoc, 72 - matched.travelledM / 1000);
      projectedArrivalSoc = Math.min(projectedArrivalSoc, 44 - matched.travelledM / 10000);
    });

    expect(isImmersiveRouteView(mode)).toBe(true);
    emit?.({ latitude: -6, longitude: 106.002 });
    const initialRemaining = remainingM;
    emit?.({ latitude: -6, longitude: 106.015 });
    expect(remainingM).toBeLessThan(initialRemaining);
    expect(stepIndex).toBe(1);
    expect(estimatedCurrentSoc).toBeLessThan(72);
    expect(projectedArrivalSoc).toBeLessThan(44);
    emit?.({ latitude: -6.01, longitude: 106.015 });
    emit?.({ latitude: -6.01, longitude: 106.015 });
    emit?.({ latitude: -6.01, longitude: 106.015 });
    expect(reroutes).toBe(1);

    active.stop();
    mode = transitionRouteView(mode, 'overview');
    expect(isImmersiveRouteView(mode)).toBe(false);
    expect(remove).toHaveBeenCalledTimes(1);

    mode = transitionRouteView(mode, 'start_navigation');
    const resumed = new NavigationWatcherSession<Fix>(watch);
    await resumed.start(() => undefined);
    expect(isImmersiveRouteView(mode)).toBe(true);
    expect(watch).toHaveBeenCalledTimes(2);
    resumed.stop();
    mode = transitionRouteView(mode, 'end_navigation');
    await cleanup('plan-integration');
    expect(isImmersiveRouteView(mode)).toBe(false);
    expect(deleteRequest).toHaveBeenCalledWith('plan-integration');
  });
});
