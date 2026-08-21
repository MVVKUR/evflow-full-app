import { describe, expect, it } from 'vitest';
import { getMockNearbyStationPerformance, getTrendPresentation } from './nearbyStationPerformance';

describe('nearby station prototype performance adapter', () => {
  it('returns deterministic prototype values for the same station ID', () => {
    const first = getMockNearbyStationPerformance({ id: 'station-a' });
    const second = getMockNearbyStationPerformance({ id: 'station-a' });
    expect(second).toEqual(first);
    expect(first.monthlyRevenueIdr).toBeGreaterThan(0);
    expect(first.averageDailySessions).toBeGreaterThan(0);
  });

  it('uses distinct deterministic values for different station IDs', () => {
    expect(getMockNearbyStationPerformance({ id: 'station-a' }))
      .not.toEqual(getMockNearbyStationPerformance({ id: 'station-b' }));
  });

  it('centralizes positive, negative, and neutral trend presentation', () => {
    expect(getTrendPresentation(8)).toEqual({ text: '↗ 8%', tone: 'positive' });
    expect(getTrendPresentation(-11)).toEqual({ text: '↘ 11%', tone: 'negative' });
    expect(getTrendPresentation(0)).toEqual({ text: '0%', tone: 'neutral' });
  });
});
