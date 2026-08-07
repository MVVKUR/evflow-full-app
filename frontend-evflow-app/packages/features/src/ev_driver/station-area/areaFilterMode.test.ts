import { describe, expect, it } from 'vitest';
import {
  allStationsLimit,
  defaultDistanceKm,
  defaultStationAreaMode,
  distanceOptions,
  fallbackStationAreaMode,
  getAreaFilterLabels,
  getAreaResultsTitle,
  getEmptyResultsMessage,
  getLocationPermissionPrompt,
  getMountLocationDecision,
  getStationFetchDecision,
  getStationQueryPlan,
  hasUsableCoordinates,
  isDistanceOption,
  isStationAreaMode,
  nearbyStationsLimit,
  resolveStationAreaMode,
  shouldRequestLocationForNearMe,
  shouldShowRadiusRing,
  stationAreaModeOptions,
  toValidRadiusKm,
  type MountLocationContext,
  type UserLocationSnapshot
} from './areaFilterMode';

const located: UserLocationSnapshot = {
  coordinates: { latitude: -6.9147, longitude: 107.6098 },
  status: 'granted'
};

const denied: UserLocationSnapshot = { coordinates: null, status: 'denied' };
const undetermined: UserLocationSnapshot = { coordinates: null, status: 'undetermined' };
const unavailable: UserLocationSnapshot = { coordinates: null, status: 'unavailable' };
const gpsError: UserLocationSnapshot = { coordinates: null, status: 'gps_error' };

/**
 * A fix that resolved with a status but no coordinates is the shape the web
 * reader produces once it stops substituting a stand-in point, so the two are
 * covered separately.
 */
const grantedWithoutCoordinates: UserLocationSnapshot = { coordinates: null, status: 'granted' };

const nativeMount = (
  storedMode: MountLocationContext['storedMode'],
  location: UserLocationSnapshot
): MountLocationContext => ({
  alreadyRequested: false,
  canPromptOnMount: true,
  location,
  storedMode
});

const webMount = (
  storedMode: MountLocationContext['storedMode'],
  location: UserLocationSnapshot
): MountLocationContext => ({ ...nativeMount(storedMode, location), canPromptOnMount: false });

describe('station area mode resolution', () => {
  it('keeps "near me" when a real fix is available', () => {
    const resolved = resolveStationAreaMode('near', located);

    expect(resolved).toEqual({
      degraded: false,
      mode: 'near',
      reason: null,
      requestedMode: 'near'
    });
  });

  it('leaves "all" alone whether or not a fix is available', () => {
    expect(resolveStationAreaMode('all', located).mode).toBe('all');
    expect(resolveStationAreaMode('all', denied)).toEqual({
      degraded: false,
      mode: 'all',
      reason: null,
      requestedMode: 'all'
    });
  });

  it.each([
    ['denied', denied, 'permission is blocked'],
    ['unavailable', unavailable, 'unavailable on this device'],
    ['gps_error', gpsError, 'could not be read'],
    ['undetermined', undetermined, 'Allow location access']
  ])('degrades "near me" to "all" and explains why when location is %s', (_status, location, expectedReason) => {
    const resolved = resolveStationAreaMode('near', location);

    expect(resolved.mode).toBe('all');
    expect(resolved.degraded).toBe(true);
    expect(resolved.requestedMode).toBe('near');
    expect(resolved.reason).toContain(expectedReason);
  });

  it('falls back to the mode that needs no coordinates, not to the session default', () => {
    // These were one constant while the default was 'all'. Now that a session
    // starts on 'near', reusing the default here would report a result built
    // without coordinates as a proximity result.
    expect(resolveStationAreaMode('near', denied).mode).toBe(fallbackStationAreaMode);
    expect(fallbackStationAreaMode).toBe('all');
  });

  it('starts a session on "near me" so the map opens on the driver own area', () => {
    expect(defaultStationAreaMode).toBe('near');
  });

  it('never presents a degraded "near me" as a proximity result', () => {
    const resolved = resolveStationAreaMode('near', denied);

    expect(shouldShowRadiusRing('near', denied)).toBe(false);
    expect(getAreaResultsTitle(resolved, getStationFetchDecision('near', denied))).toBe('All SPKLU Stations');
    expect(getAreaFilterLabels(resolved, defaultDistanceKm)).toEqual([]);
    expect(getStationQueryPlan('near', denied, defaultDistanceKm)).toEqual({
      endpoint: 'list',
      limit: allStationsLimit
    });
  });

  it('remembers what the driver asked for while it is downgraded', () => {
    const denialResolution = resolveStationAreaMode('near', denied);

    // The screen keeps holding 'near', so the same request re-resolves to a
    // real proximity query the moment a fix arrives.
    expect(denialResolution.requestedMode).toBe('near');
    expect(resolveStationAreaMode(denialResolution.requestedMode, located).mode).toBe('near');
  });
});

describe('usable coordinates', () => {
  it('accepts a finite in-range pair', () => {
    expect(hasUsableCoordinates(located)).toBe(true);
    expect(hasUsableCoordinates({ coordinates: { latitude: 0, longitude: 0 }, status: 'granted' })).toBe(true);
  });

  it('rejects a missing pair', () => {
    expect(hasUsableCoordinates(denied)).toBe(false);
  });

  it.each([
    ['NaN latitude', { latitude: Number.NaN, longitude: 107 }],
    ['infinite longitude', { latitude: -6.9, longitude: Number.POSITIVE_INFINITY }],
    ['out-of-range latitude', { latitude: 91, longitude: 107 }],
    ['out-of-range longitude', { latitude: -6.9, longitude: -181 }]
  ])('rejects %s even when the status claims granted', (_label, coordinates) => {
    expect(hasUsableCoordinates({ coordinates, status: 'granted' })).toBe(false);
  });
});

describe('station query plan', () => {
  it('queries the nearby endpoint with the driver coordinates and radius', () => {
    expect(getStationQueryPlan('near', located, 3)).toEqual({
      endpoint: 'nearby',
      latitude: -6.9147,
      limit: nearbyStationsLimit,
      longitude: 107.6098,
      radiusKm: 3
    });
  });

  it('queries the nearby endpoint at the default distance too', () => {
    // The old implicit routing sent the default distance to the list endpoint,
    // so an explicit "near me" at 8 km was impossible to express.
    const plan = getStationQueryPlan('near', located, defaultDistanceKm);

    expect(plan.endpoint).toBe('nearby');
    expect(plan).toMatchObject({ radiusKm: defaultDistanceKm });
  });

  it('queries the list endpoint for "all"', () => {
    expect(getStationQueryPlan('all', located, 3)).toEqual({
      endpoint: 'list',
      limit: allStationsLimit
    });
  });

  it.each([
    ['denied', denied],
    ['undetermined', undetermined],
    ['unavailable', unavailable],
    ['gps_error', gpsError]
  ])('never plans a nearby query without coordinates when location is %s', (_status, location) => {
    const plan = getStationQueryPlan('near', location, 5);

    expect(plan).toEqual({ endpoint: 'list', limit: allStationsLimit });
  });

  it('never plans a nearby query from coordinates that are not real numbers', () => {
    const plan = getStationQueryPlan('near', { coordinates: { latitude: Number.NaN, longitude: 107 }, status: 'granted' }, 5);

    expect(plan.endpoint).toBe('list');
  });

  it('substitutes no location of its own when the fix is missing', () => {
    const plan = getStationQueryPlan('near', denied, 5);

    expect(plan).not.toHaveProperty('latitude');
    expect(plan).not.toHaveProperty('longitude');
  });

  it.each([0, -4, Number.NaN, Number.POSITIVE_INFINITY])('falls back to the default radius for %s', (distanceKm) => {
    expect(getStationQueryPlan('near', located, distanceKm)).toMatchObject({ radiusKm: defaultDistanceKm });
    expect(toValidRadiusKm(distanceKm)).toBe(defaultDistanceKm);
  });

  it('accepts every distance the slider can produce', () => {
    distanceOptions.forEach((option) => {
      expect(getStationQueryPlan('near', located, option)).toMatchObject({ radiusKm: option });
    });
  });
});

describe('area filter presentation', () => {
  it('draws the radius ring only for a resolved near-me query', () => {
    expect(shouldShowRadiusRing('near', located)).toBe(true);
    expect(shouldShowRadiusRing('all', located)).toBe(false);
    expect(shouldShowRadiusRing('near', denied)).toBe(false);
  });

  it('chips the area and radius for near me only', () => {
    expect(getAreaFilterLabels(resolveStationAreaMode('near', located), 5)).toEqual(['Near me', '5 km']);
    expect(getAreaFilterLabels(resolveStationAreaMode('all', located), 5)).toEqual([]);
    expect(getAreaFilterLabels(resolveStationAreaMode('near', denied), 5)).toEqual([]);
  });

  it('titles the results by the mode actually used', () => {
    expect(getAreaResultsTitle(resolveStationAreaMode('near', located), 'fetch')).toBe('Nearby SPKLU Stations');
    expect(getAreaResultsTitle(resolveStationAreaMode('all', located), 'fetch')).toBe('All SPKLU Stations');
    expect(getAreaResultsTitle(resolveStationAreaMode('near', denied), 'fetch')).toBe('All SPKLU Stations');
  });

  it('does not call an unanswered near-me result "all stations"', () => {
    // Nothing has been fetched in this state, so the heading would otherwise
    // report an empty list as the complete national one.
    expect(getAreaResultsTitle(resolveStationAreaMode('near', undetermined), 'await_permission')).toBe(
      'Nearby SPKLU Stations'
    );
  });

  it('suggests a way out of an empty near-me result', () => {
    const message = getEmptyResultsMessage(resolveStationAreaMode('near', located), 3, 'fetch');

    expect(message).toContain('3 km');
    expect(message).toContain('all stations');
    expect(getEmptyResultsMessage(resolveStationAreaMode('all', located), 3, 'fetch')).toBe('No SPKLU stations found.');
  });

  it('explains an empty list that is waiting on permission rather than reporting no stations', () => {
    const message = getEmptyResultsMessage(resolveStationAreaMode('near', undetermined), 3, 'await_permission');

    expect(message).toContain('Allow location access');
    expect(message).not.toContain('No SPKLU stations');
  });

  it('offers exactly the two documented modes', () => {
    expect(stationAreaModeOptions.map((option) => option.key)).toEqual(['near', 'all']);
  });
});

describe('permission prompting', () => {
  it('prompts when the driver has not been asked yet or the read errored', () => {
    expect(shouldRequestLocationForNearMe(undetermined)).toBe(true);
    expect(shouldRequestLocationForNearMe(gpsError)).toBe(true);
  });

  it('does not re-prompt when already located or hard-blocked', () => {
    expect(shouldRequestLocationForNearMe(located)).toBe(false);
    expect(shouldRequestLocationForNearMe(denied)).toBe(false);
    expect(shouldRequestLocationForNearMe(unavailable)).toBe(false);
  });
});

describe('asking for location on open', () => {
  it('asks on a platform that can afford the prompt, so the session default is answerable', () => {
    // Without this the screen opens on 'near', finds no fix, and degrades to
    // the whole country every single time.
    expect(getMountLocationDecision(nativeMount('near', undetermined))).toBe('request_permission');
  });

  it('waits for a tap where the prompt is one-shot instead of spending it on first paint', () => {
    expect(getMountLocationDecision(webMount('near', undetermined))).toBe('await_driver_action');
  });

  it('asks for nothing when a usable fix is already in hand', () => {
    expect(getMountLocationDecision(nativeMount('near', located))).toBe('skip');
    expect(getMountLocationDecision(webMount('near', located))).toBe('skip');
  });

  it.each([
    ['denied', denied],
    ['unavailable', unavailable],
    ['gps_error', gpsError]
  ])('asks for nothing when the answer is already final: %s', (_status, location) => {
    // These are answers, not silence. Re-asking on every open would nag on a
    // refusal and retry-loop on a failed read; the card offers a manual retry.
    expect(getMountLocationDecision(nativeMount('near', location))).toBe('skip');
    expect(getMountLocationDecision(webMount('near', location))).toBe('skip');
  });

  it.each([
    ['undetermined', undetermined],
    ['denied', denied],
    ['unavailable', unavailable],
    ['gps_error', gpsError],
    ['granted with no coordinates', grantedWithoutCoordinates]
  ])('never asks when the driver deliberately chose all stations: %s', (_status, location) => {
    expect(getMountLocationDecision(nativeMount('all', location))).toBe('skip');
    expect(getMountLocationDecision(webMount('all', location))).toBe('skip');
  });

  it('does not stack a second prompt on top of one the driver already triggered', () => {
    expect(
      getMountLocationDecision({ ...nativeMount('near', undetermined), alreadyRequested: true })
    ).toBe('await_driver_action');
  });

  it('does not prompt for a permission that is already granted but produced no coordinates', () => {
    // Nothing to ask for: the permission is not the obstacle, so the request
    // degrades visibly and the card's retry re-reads the position instead.
    expect(getMountLocationDecision(nativeMount('near', grantedWithoutCoordinates))).toBe('skip');
    expect(getStationFetchDecision('near', grantedWithoutCoordinates)).toBe('fetch');
    expect(resolveStationAreaMode('near', grantedWithoutCoordinates).degraded).toBe(true);
  });
});

describe('holding the stations request', () => {
  it('waits while the near-me permission question is still open', () => {
    expect(getStationFetchDecision('near', undetermined)).toBe('await_permission');
  });

  it('fetches at once when near me has a real fix', () => {
    expect(getStationFetchDecision('near', located)).toBe('fetch');
  });

  it.each([
    ['denied', denied],
    ['unavailable', unavailable],
    ['gps_error', gpsError]
  ])('fetches the degraded result at once once the answer is final: %s', (_status, location) => {
    // There is nothing left to wait for, so the honest downgrade to "all" is
    // the final result and should render immediately rather than hang.
    expect(getStationFetchDecision('near', location)).toBe('fetch');
  });

  it.each([
    ['undetermined', undetermined],
    ['denied', denied],
    ['located', located]
  ])('never holds an "all" request back for a location it does not use: %s', (_status, location) => {
    expect(getStationFetchDecision('all', location)).toBe('fetch');
  });

  it('holds the request precisely when the unbounded query would be wasted', () => {
    // The held state is the one where the national list would be fetched,
    // painted, and then thrown away the moment the driver answers.
    expect(getStationQueryPlan('near', undetermined, defaultDistanceKm)).toEqual({
      endpoint: 'list',
      limit: allStationsLimit
    });
    expect(getStationFetchDecision('near', undetermined)).toBe('await_permission');
  });
});

describe('location permission card copy', () => {
  it.each([
    ['denied', denied, 'permission is blocked', 'Try Again'],
    ['unavailable', unavailable, 'unavailable on this device', 'Try Again'],
    ['gps_error', gpsError, 'could not be read', 'Try Again'],
    ['undetermined', undetermined, 'Allow location access', 'Use Current Location']
  ])('explains %s and offers an action that exists', (_status, location, expectedBody, expectedLabel) => {
    const prompt = getLocationPermissionPrompt(resolveStationAreaMode('near', location), location.status);

    expect(prompt.title).toBe('Near me needs your location');
    expect(prompt.body).toContain(expectedBody);
    expect(prompt.buttonLabel).toBe(expectedLabel);
  });

  it.each([
    ['denied', denied],
    ['unavailable', unavailable],
    ['gps_error', gpsError],
    ['undetermined', undetermined]
  ])('never offers a stand-in location the app cannot produce: %s', (_status, location) => {
    const prompt = getLocationPermissionPrompt(resolveStationAreaMode('near', location), location.status);

    // The card used to promise "default EV center coordinates in Jakarta",
    // which described a fabricated fix rather than anything the app now has.
    expect(prompt.body).not.toMatch(/default/i);
    expect(prompt.body).not.toMatch(/jakarta/i);
    expect(prompt.buttonLabel).not.toMatch(/default/i);
  });

  it('does not claim near me is broken when the driver asked for all stations', () => {
    const prompt = getLocationPermissionPrompt(resolveStationAreaMode('all', undetermined), 'undetermined');

    expect(prompt.title).toBe('Use your current location');
    expect(prompt.body).toContain('Allow location access');
  });
});

describe('value guards', () => {
  it('recognises only the two modes', () => {
    expect(isStationAreaMode('near')).toBe(true);
    expect(isStationAreaMode('all')).toBe(true);
    expect(isStationAreaMode('nearby')).toBe(false);
    expect(isStationAreaMode(null)).toBe(false);
    expect(isStationAreaMode(undefined)).toBe(false);
  });

  it('recognises only the slider distances', () => {
    distanceOptions.forEach((option) => expect(isDistanceOption(option)).toBe(true));
    expect(isDistanceOption(7)).toBe(false);
    expect(isDistanceOption('8')).toBe(false);
  });
});
