import { describe, expect, it } from 'vitest';
import {
  ALTERNATIVES_LIMIT,
  ALTERNATIVES_WAIT_THRESHOLD_MINUTES,
  selectNearbyAlternatives,
  shouldOfferAlternatives
} from './nearbyAlternatives';
import type { StationApiItem } from '@evflow/shared';

function availability(overrides: Partial<Parameters<typeof shouldOfferAlternatives>[0] & object> = {}) {
  return {
    state: 'available' as const,
    totalCount: 4,
    availableCount: 2,
    earliestEstimate: null,
    ...overrides
  };
}

function apiStation(overrides: Partial<StationApiItem> = {}): StationApiItem {
  return {
    id: 'pln_spklu-1',
    name: 'SPKLU Test',
    sources: ['pln_spklu'],
    latitude: -6.2,
    longitude: 106.8,
    address: null,
    province: null,
    city: null,
    operator: null,
    power_kw: 50,
    charge_type: null,
    speed_tier: null,
    connectors: [],
    connector_types: [],
    connector_inferred: null,
    status: null,
    date_verified: null,
    distance_km: 1.2,
    total_connectors: 4,
    available_connectors: 2,
    ...overrides
  };
}

describe('shouldOfferAlternatives (AC 3.4.1 trigger)', () => {
  it('offers alternatives when every connector is taken', () => {
    expect(shouldOfferAlternatives(availability({ state: 'occupied', availableCount: 0 }))).toBe(true);
  });

  it('offers alternatives when the station is fully out of service', () => {
    // Broken is as unusable as occupied: the driver cannot charge here either way.
    expect(shouldOfferAlternatives(availability({ state: 'out_of_service', availableCount: 0 }))).toBe(true);
  });

  it('offers alternatives when the wait estimate exceeds the threshold even with a plug technically free', () => {
    expect(
      shouldOfferAlternatives(
        availability({
          availableCount: 1,
          earliestEstimate: { availableAt: null, minutes: ALTERNATIVES_WAIT_THRESHOLD_MINUTES + 1 }
        })
      )
    ).toBe(true);
  });

  it('stays quiet when a connector is free and no long wait is estimated', () => {
    expect(shouldOfferAlternatives(availability())).toBe(false);
    expect(
      shouldOfferAlternatives(
        availability({ earliestEstimate: { availableAt: null, minutes: ALTERNATIVES_WAIT_THRESHOLD_MINUTES } })
      )
    ).toBe(false);
  });

  it('stays quiet without live data: no status, zero connectors, or unknown state', () => {
    // "We do not know" must never be presented as "this station is full".
    expect(shouldOfferAlternatives(null)).toBe(false);
    expect(shouldOfferAlternatives(availability({ totalCount: 0, availableCount: 0 }))).toBe(false);
    expect(shouldOfferAlternatives(availability({ state: 'unknown', availableCount: 0 }))).toBe(false);
  });
});

describe('selectNearbyAlternatives (AC 3.4.1 list)', () => {
  it('keeps only stations with a free connector right now', () => {
    const picked = selectNearbyAlternatives(
      [
        apiStation({ id: 'a', available_connectors: 0 }),
        apiStation({ id: 'b', available_connectors: 3 }),
        apiStation({ id: 'c', available_connectors: null }),
        apiStation({ id: 'd', available_connectors: undefined }),
        apiStation({ id: 'e', available_connectors: 1 })
      ],
      'current'
    );
    expect(picked.map((s) => s.id)).toEqual(['b', 'e']);
  });

  it('never recommends the station the driver is already looking at', () => {
    const picked = selectNearbyAlternatives(
      [apiStation({ id: 'current', available_connectors: 4 }), apiStation({ id: 'other' })],
      'current'
    );
    expect(picked.map((s) => s.id)).toEqual(['other']);
  });

  it('orders by distance and caps the list', () => {
    const picked = selectNearbyAlternatives(
      [
        apiStation({ id: 'far', distance_km: 9.4 }),
        apiStation({ id: 'near', distance_km: 0.4 }),
        apiStation({ id: 'mid', distance_km: 3.1 }),
        apiStation({ id: 'mid2', distance_km: 4.0 }),
        apiStation({ id: 'far2', distance_km: 8.8 }),
        apiStation({ id: 'far3', distance_km: 9.0 })
      ],
      'current'
    );
    expect(picked.length).toBe(ALTERNATIVES_LIMIT);
    expect(picked[0].id).toBe('near');
    expect(picked.map((s) => s.id)).toEqual(['near', 'mid', 'mid2', 'far2']);
  });

  it('treats a missing distance as farthest instead of dropping the station', () => {
    const picked = selectNearbyAlternatives(
      [apiStation({ id: 'nodist', distance_km: null }), apiStation({ id: 'near', distance_km: 0.5 })],
      'current',
    );
    expect(picked.map((s) => s.id)).toEqual(['near', 'nodist']);
  });
});
