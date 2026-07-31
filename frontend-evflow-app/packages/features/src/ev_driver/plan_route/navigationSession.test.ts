import { describe, expect, it, vi } from 'vitest';
import { createRouteSessionCleaner, NavigationWatcherSession, shouldDeleteReplacedPlanningSession } from './navigationSession';

describe('navigation session lifecycle', () => {
  it('keeps one watcher across multiple fixes and removes it once', async () => {
    const remove = vi.fn();
    let emit: ((value: number) => void) | undefined;
    const factory = vi.fn(async (onValue: (value: number) => void) => { emit = onValue; return { remove }; });
    const values: number[] = [];
    const session = new NavigationWatcherSession(factory);
    await Promise.all([session.start((value) => values.push(value)), session.start((value) => values.push(value))]);
    emit?.(1); emit?.(2); emit?.(3);
    session.stop(); session.stop();
    expect(factory).toHaveBeenCalledTimes(1);
    expect(values).toEqual([1, 2, 3]);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it('starts a new watcher after Overview when navigation resumes in a new session', async () => {
    const factory = vi.fn(async () => ({ remove: vi.fn() }));
    const active = new NavigationWatcherSession(factory);
    await active.start(() => undefined); active.stop();
    const resumed = new NavigationWatcherSession(factory);
    await resumed.start(() => undefined);
    expect(factory).toHaveBeenCalledTimes(2);
  });

  it('deletes each route session idempotently', async () => {
    const remove = vi.fn(async () => undefined);
    const cleanup = createRouteSessionCleaner(remove);
    await cleanup('plan-1'); await cleanup('plan-1'); await cleanup('plan-2');
    expect(remove.mock.calls).toEqual([['plan-1'], ['plan-2']]);
  });

  it('keeps the prior planning session when recalculating with a charging waypoint', () => {
    expect(shouldDeleteReplacedPlanningSession('initial-route', 'route-with-stop', 'station-1')).toBe(false);
  });

  it('cleans up a replaced session only for a non-waypoint route replacement', () => {
    expect(shouldDeleteReplacedPlanningSession('initial-route', 'replacement-route')).toBe(true);
    expect(shouldDeleteReplacedPlanningSession('same-route', 'same-route')).toBe(false);
  });
});
