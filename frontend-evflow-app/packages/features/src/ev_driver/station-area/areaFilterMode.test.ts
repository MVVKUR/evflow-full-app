import { describe, expect, it } from 'vitest';
import {
  allStationsLimit,
  defaultDistanceKm,
  defaultStationAreaMode,
  distanceOptions,
  getAreaFilterLabels,
  getAreaResultsTitle,
  getEmptyResultsMessage,
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

  it('always falls back to the mode that needs no coordinates', () => {
    expect(resolveStationAreaMode('near', denied).mode).toBe(defaultStationAreaMode);
    expect(defaultStationAreaMode).toBe('all');
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
    expect(getAreaResultsTitle(resolveStationAreaMode('near', located))).toBe('Nearby SPKLU Stations');
    expect(getAreaResultsTitle(resolveStationAreaMode('all', located))).toBe('All SPKLU Stations');
    expect(getAreaResultsTitle(resolveStationAreaMode('near', denied))).toBe('All SPKLU Stations');
  });

  it('suggests a way out of an empty near-me result', () => {
    const message = getEmptyResultsMessage(resolveStationAreaMode('near', located), 3);

    expect(message).toContain('3 km');
    expect(message).toContain('all stations');
    expect(getEmptyResultsMessage(resolveStationAreaMode('all', located), 3)).toBe('No SPKLU stations found.');
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
