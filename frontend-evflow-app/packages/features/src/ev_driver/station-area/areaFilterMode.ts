import type { LocationPermissionStatus } from '../utils/location';

/**
 * Which stations the driver asked to see.
 *
 * Before this filter existed the screen picked its endpoint implicitly: any
 * non-default connector/speed/distance value routed to /stations/nearby and
 * everything else routed to /stations. That meant the driver could not ask for
 * "all stations" while also filtering by connector, and could not ask for
 * "near me" at the default 8 km. The mode is now an explicit choice.
 */
export type StationAreaMode = 'near' | 'all';

export type AreaCoordinates = {
  latitude: number;
  longitude: number;
};

export type UserLocationSnapshot = {
  coordinates: AreaCoordinates | null;
  status: LocationPermissionStatus;
};

/**
 * 'all' matches what the screen did by default before this filter existed, and
 * unlike 'near' it is always satisfiable, so it is also the degraded fallback.
 */
export const defaultStationAreaMode: StationAreaMode = 'all';

/** The single distance scale for this screen: slider stops, chips and radius all read it. */
export const distanceOptions = [3, 5, 8, 10] as const;

export type DistanceOption = (typeof distanceOptions)[number];

export const defaultDistanceKm: DistanceOption = 8;

/** /stations is unbounded, so the list mode has to cap itself. */
export const allStationsLimit = 1000;

/** /stations/nearby is already bounded by radius_km; this only guards a dense city centre. */
export const nearbyStationsLimit = 200;

export const stationAreaModeOptions: ReadonlyArray<{ key: StationAreaMode; label: string }> = [
  { key: 'near', label: 'Near me' },
  { key: 'all', label: 'All stations' }
];

export function isStationAreaMode(value: unknown): value is StationAreaMode {
  return value === 'near' || value === 'all';
}

export function isDistanceOption(value: unknown): value is DistanceOption {
  return distanceOptions.some((option) => option === value);
}

/**
 * "Near me" needs a real fix. A snapshot that reports 'granted' but carries no
 * usable pair of finite coordinates is still unusable, so the coordinates are
 * checked rather than the permission status.
 */
export function hasUsableCoordinates(location: UserLocationSnapshot): boolean {
  const coordinates = location.coordinates;

  if (!coordinates) {
    return false;
  }

  return (
    Number.isFinite(coordinates.latitude) &&
    Number.isFinite(coordinates.longitude) &&
    Math.abs(coordinates.latitude) <= 90 &&
    Math.abs(coordinates.longitude) <= 180
  );
}

export type ResolvedStationAreaMode = {
  /**
   * The mode actually used for the query, and the one the control should show
   * as selected. Never 'near' without coordinates.
   */
  mode: StationAreaMode;
  /**
   * What the driver asked for. Held in screen state so that a request denied
   * for want of a fix re-resolves to 'near' by itself once one arrives,
   * instead of making the driver choose again.
   */
  requestedMode: StationAreaMode;
  degraded: boolean;
  /** Why the request was downgraded, for display. Null when nothing was downgraded. */
  reason: string | null;
};

/**
 * Downgrades an impossible "near me" request to "all" and says why.
 *
 * Substituting a stand-in coordinate here would be worse than the downgrade:
 * the driver would be shown a ranked, distance-labelled list built around a
 * place they are not.
 */
export function resolveStationAreaMode(
  requestedMode: StationAreaMode,
  location: UserLocationSnapshot
): ResolvedStationAreaMode {
  if (requestedMode !== 'near') {
    return { degraded: false, mode: 'all', reason: null, requestedMode };
  }

  if (hasUsableCoordinates(location)) {
    return { degraded: false, mode: 'near', reason: null, requestedMode };
  }

  return {
    degraded: true,
    mode: defaultStationAreaMode,
    reason: getUnavailableNearMeReason(location.status),
    requestedMode
  };
}

function getUnavailableNearMeReason(status: LocationPermissionStatus): string {
  if (status === 'denied') {
    return 'Location permission is blocked, so stations near you cannot be found. Showing all stations instead.';
  }

  if (status === 'unavailable') {
    return 'Location services are unavailable on this device, so stations near you cannot be found. Showing all stations instead.';
  }

  if (status === 'gps_error') {
    return 'Your location could not be read, so stations near you cannot be found. Showing all stations instead.';
  }

  return 'Allow location access to see only stations near you. Showing all stations until then.';
}

export type StationQueryPlan =
  | { endpoint: 'nearby'; latitude: number; longitude: number; limit: number; radiusKm: number }
  | { endpoint: 'list'; limit: number };

/**
 * The only place that decides which stations endpoint runs. Returning a plan
 * rather than calling fetch keeps the decision testable without a network stub.
 */
export function getStationQueryPlan(
  requestedMode: StationAreaMode,
  location: UserLocationSnapshot,
  distanceKm: number
): StationQueryPlan {
  const resolved = resolveStationAreaMode(requestedMode, location);

  // resolveStationAreaMode already guarantees coordinates exist for 'near'; the
  // second read is only here to narrow the nullable type.
  if (resolved.mode === 'near' && location.coordinates) {
    return {
      endpoint: 'nearby',
      latitude: location.coordinates.latitude,
      limit: nearbyStationsLimit,
      longitude: location.coordinates.longitude,
      radiusKm: toValidRadiusKm(distanceKm)
    };
  }

  return { endpoint: 'list', limit: allStationsLimit };
}

/** A radius of 0, NaN or Infinity would return either nothing or the whole country. */
export function toValidRadiusKm(distanceKm: number): number {
  if (!Number.isFinite(distanceKm) || distanceKm <= 0) {
    return defaultDistanceKm;
  }

  return distanceKm;
}

/** The radius ring is a claim about where the driver is, so it needs a real fix behind it. */
export function shouldShowRadiusRing(requestedMode: StationAreaMode, location: UserLocationSnapshot): boolean {
  return resolveStationAreaMode(requestedMode, location).mode === 'near';
}

/**
 * Chips for the results header. 'all' is the default, so like the other
 * filters it stays unchipped; a downgraded request is not chipped either
 * because the notice already explains it.
 */
export function getAreaFilterLabels(resolved: ResolvedStationAreaMode, distanceKm: number): string[] {
  if (resolved.mode !== 'near') {
    return [];
  }

  return ['Near me', `${toValidRadiusKm(distanceKm)} km`];
}

export function getAreaResultsTitle(resolved: ResolvedStationAreaMode): string {
  return resolved.mode === 'near' ? 'Nearby SPKLU Stations' : 'All SPKLU Stations';
}

export function getEmptyResultsMessage(resolved: ResolvedStationAreaMode, distanceKm: number): string {
  if (resolved.mode === 'near') {
    return `No SPKLU stations within ${toValidRadiusKm(distanceKm)} km of you. Try a larger distance or switch to all stations.`;
  }

  return 'No SPKLU stations found.';
}

/**
 * True when picking "Near me" should trigger a permission prompt instead of
 * just failing: the driver has never been asked, or the last read errored.
 */
export function shouldRequestLocationForNearMe(location: UserLocationSnapshot): boolean {
  if (hasUsableCoordinates(location)) {
    return false;
  }

  return location.status === 'undetermined' || location.status === 'gps_error';
}
