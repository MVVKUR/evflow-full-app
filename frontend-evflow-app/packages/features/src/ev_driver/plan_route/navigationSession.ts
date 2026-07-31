export type RemovableSubscription = { remove(): void };
export type WatchFactory<T> = (
  onValue: (value: T) => void,
  onError?: () => void,
) => Promise<RemovableSubscription | null>;

/** Owns exactly one watcher for one mounted active-navigation session. */
export class NavigationWatcherSession<T> {
  private subscription: RemovableSubscription | null = null;
  private pending: Promise<void> | null = null;
  private stopped = false;

  constructor(private readonly factory: WatchFactory<T>) {}

  start(onValue: (value: T) => void, onError?: () => void): Promise<void> {
    if (this.subscription || this.pending) return this.pending ?? Promise.resolve();
    this.stopped = false;
    this.pending = this.factory(onValue, onError).then((subscription) => {
      if (!subscription) onError?.();
      if (this.stopped) subscription?.remove();
      else this.subscription = subscription;
    }).finally(() => { this.pending = null; });
    return this.pending;
  }

  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    this.subscription?.remove();
    this.subscription = null;
  }
}

export function createRouteSessionCleaner(deleteSession: (id: string) => Promise<void>) {
  const deleted = new Set<string>();
  return async (id?: string | null) => {
    if (!id || deleted.has(id)) return;
    deleted.add(id);
    await deleteSession(id);
  };
}

export function shouldDeleteReplacedPlanningSession(
  previousRoutePlanId: string | undefined,
  nextRoutePlanId: string,
  waypointStationId?: string,
): boolean {
  return Boolean(previousRoutePlanId && previousRoutePlanId !== nextRoutePlanId && !waypointStationId);
}
