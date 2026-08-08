import type { StationApiItem } from '@evflow/shared';
import type { AvailabilityEstimate, AvailabilityState } from '../station-status/aggregateConnectorStatuses';

/**
 * AC 3.4.1: when the station the driver opened is fully occupied — or the
 * estimated wait exceeds the threshold — the SAME detail screen must offer
 * nearby stations that are actually free right now.
 */

/** Alternatives are searched around the OCCUPIED STATION, not around the driver. */
export const ALTERNATIVES_RADIUS_KM = 10;

/** AC 3.4.1's example threshold: a wait beyond this is as bad as "full". */
export const ALTERNATIVES_WAIT_THRESHOLD_MINUTES = 15;

/** How many alternatives the section shows. */
export const ALTERNATIVES_LIMIT = 4;

/**
 * How many stations to ask the API for. Deliberately larger than the shown
 * limit: full and status-unknown neighbours are filtered out client-side, so a
 * fetch sized exactly to the display limit could end up rendering nothing in a
 * busy area even though free stations exist a little further down the list.
 */
export const ALTERNATIVES_FETCH_LIMIT = 25;

type AvailabilitySnapshot = {
  state: AvailabilityState;
  totalCount: number;
  availableCount: number;
  earliestEstimate: AvailabilityEstimate | null;
};

/**
 * Whether the detail screen should offer alternatives at all.
 *
 * True only when live data POSITIVELY says charging here now is a bad idea:
 * every connector taken or broken, or the soonest-free estimate is beyond the
 * threshold. `unknown` (and no data at all) stays false — "we could not read
 * the status" must never be presented to the driver as "this station is full".
 */
export function shouldOfferAlternatives(availability: AvailabilitySnapshot | null): boolean {
  if (!availability || availability.totalCount <= 0 || availability.state === 'unknown') {
    return false;
  }
  if (availability.availableCount <= 0) {
    return true;
  }
  const waitMinutes = availability.earliestEstimate?.minutes;
  return typeof waitMinutes === 'number' && waitMinutes > ALTERNATIVES_WAIT_THRESHOLD_MINUTES;
}

/**
 * Pick which nearby stations qualify as alternatives.
 *
 * Only stations whose live count reports a free connector qualify: a null or
 * absent `available_connectors` means the server could not say, and an
 * "alternative" that turns out to be just as full defeats the feature. The
 * station being viewed is excluded — recommending the place the driver is
 * already looking at is noise. Distance order is kept (nearest first, missing
 * distances last) so the top entries are the cheapest detours.
 */
export function selectNearbyAlternatives(
  items: StationApiItem[],
  currentStationId: string,
  limit: number = ALTERNATIVES_LIMIT
): StationApiItem[] {
  return items
    .filter((item) => item.id !== currentStationId)
    .filter((item) => typeof item.available_connectors === 'number' && item.available_connectors > 0)
    .sort((left, right) => (left.distance_km ?? Number.POSITIVE_INFINITY) - (right.distance_km ?? Number.POSITIVE_INFINITY))
    .slice(0, Math.max(0, limit));
}
