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
 * What a session starts on. A driver opening the map wants the stations they
 * can actually reach, so the screen asks for their own area first rather than
 * every station in the country.
 */
export const defaultStationAreaMode: StationAreaMode = 'near';

/**
 * The mode that needs no coordinates, so it is what an unsatisfiable 'near'
 * request degrades to. Deliberately separate from defaultStationAreaMode: now
 * that the default is 'near', reusing it here would label a result built
 * without a fix as a proximity result.
 */
export const fallbackStationAreaMode: StationAreaMode = 'all';

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
    mode: fallbackStationAreaMode,
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

  // Deliberately does NOT promise a national list: while the permission answer
  // is still pending nothing is fetched at all, so claiming "showing all
  // stations until then" described a screen the driver was not looking at.
  return 'Allow location access to see stations near you.';
}

/**
 * True while a "near me" request has neither a fix nor an answer: the driver
 * has not been asked yet, or has been asked and has not replied.
 *
 * Distinguished from the other coordinate-less cases on purpose. 'denied',
 * 'unavailable' and 'gps_error' are answers — final ones — so the degrade to
 * "all" is the result and should be shown at once. 'undetermined' is an open
 * question, and treating it as a refusal is what makes the screen paint every
 * station in the country for the moment before the driver replies.
 */
function isAwaitingLocationAnswer(requestedMode: StationAreaMode, location: UserLocationSnapshot): boolean {
  if (requestedMode !== 'near' || hasUsableCoordinates(location)) {
    return false;
  }

  return location.status === 'undetermined';
}

/** What the screen should do about location the moment it opens. */
export type MountLocationDecision =
  /** Ask now, unprompted by the driver. */
  | 'request_permission'
  /** The question is open, but this platform has to earn the prompt with a tap. */
  | 'await_driver_action'
  /** Nothing to ask: a fix is in hand, the answer is final, or none is needed. */
  | 'skip';

export type MountLocationContext = {
  /**
   * The mode the session opens on, restored from the last committed choice.
   * A driver who deliberately picked "all" is not asked for a location they
   * have said they do not need.
   */
  storedMode: StationAreaMode;
  location: UserLocationSnapshot;
  /**
   * Whether an unsolicited prompt is affordable on this platform. A native OS
   * dialog is modal, dismissible, and offered again next launch. A browser
   * prompt is one shot per origin and a refusal sticks, so the web passes
   * false and earns its prompt from an explicit tap instead of spending the
   * only one it gets on first paint.
   */
  canPromptOnMount: boolean;
  /** A prompt the driver already triggered is in flight; do not stack a second. */
  alreadyRequested: boolean;
};

/**
 * Whether opening the screen should request location by itself.
 *
 * A session starts on "near me", which cannot be answered without a fix, so
 * something has to go and get one. Which of the three answers applies is a
 * function of the persisted mode and the permission status alone, so it is
 * decided here rather than as a condition buried in a mount effect.
 */
export function getMountLocationDecision({
  alreadyRequested,
  canPromptOnMount,
  location,
  storedMode
}: MountLocationContext): MountLocationDecision {
  if (!isAwaitingLocationAnswer(storedMode, location)) {
    return 'skip';
  }

  if (alreadyRequested || !canPromptOnMount) {
    return 'await_driver_action';
  }

  return 'request_permission';
}

/** Whether the stations request can run yet, or is still waiting on a human. */
export type StationFetchDecision = 'fetch' | 'await_permission';

/**
 * Holds the stations request back while a "near me" permission question is
 * still open. Fetching here would run the unbounded list query and paint every
 * station in the country, only to replace them with a handful the instant the
 * driver answers.
 */
export function getStationFetchDecision(
  requestedMode: StationAreaMode,
  location: UserLocationSnapshot
): StationFetchDecision {
  return isAwaitingLocationAnswer(requestedMode, location) ? 'await_permission' : 'fetch';
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

/**
 * Titles the results by the mode actually used, except while the near-me
 * question is open: nothing has been fetched then, and heading an empty list
 * "All SPKLU Stations" would report that the country has none.
 */
export function getAreaResultsTitle(
  resolved: ResolvedStationAreaMode,
  fetchDecision: StationFetchDecision
): string {
  if (fetchDecision === 'await_permission' || resolved.mode === 'near') {
    return 'Nearby SPKLU Stations';
  }

  return 'All SPKLU Stations';
}

export function getEmptyResultsMessage(
  resolved: ResolvedStationAreaMode,
  distanceKm: number,
  fetchDecision: StationFetchDecision
): string {
  // Empty because nothing was asked for yet, not because nothing was found.
  if (fetchDecision === 'await_permission') {
    return 'Allow location access to see the stations around you, or switch to all stations.';
  }

  if (resolved.mode === 'near') {
    return `No SPKLU stations within ${toValidRadiusKm(distanceKm)} km of you. Try a larger distance or switch to all stations.`;
  }

  return 'No SPKLU stations found.';
}

export type LocationPermissionPrompt = {
  body: string;
  buttonLabel: string;
  title: string;
};

/**
 * Copy for the card that asks for a location. It promises only what the app
 * can deliver: there is no stand-in coordinate to fall back to, so the card
 * offers a retry and an explanation, never a "default location".
 */
export function getLocationPermissionPrompt(
  resolved: ResolvedStationAreaMode,
  status: LocationPermissionStatus
): LocationPermissionPrompt {
  return {
    body: resolved.reason ?? getUnavailableNearMeReason(status),
    buttonLabel: getLocationPermissionButtonLabel(status),
    title: resolved.degraded ? 'Near me needs your location' : 'Use your current location'
  };
}

function getLocationPermissionButtonLabel(status: LocationPermissionStatus): string {
  if (status === 'denied' || status === 'unavailable' || status === 'gps_error') {
    return 'Try Again';
  }

  return 'Use Current Location';
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
