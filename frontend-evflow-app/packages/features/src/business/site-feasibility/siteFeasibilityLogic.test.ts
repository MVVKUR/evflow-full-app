import { describe, expect, it } from 'vitest';
import { generateMockOptimalSites, jakartaViewport } from '../demandHeatmap';
import {
  calculateActivityScore,
  calculateLocationScore,
  calculateOverlapScore,
  calculatePoiScore,
  getHeatmapDescription,
  getNearbyStationsWithinRadius,
  getOverlapDescription,
  getPaybackStatus,
  getPoiDescription,
  resolveOptimalSite,
  sortStationsByDistance
} from './siteFeasibilityLogic';
import { getSiteFeasibility } from './siteFeasibilityMockData';

describe('Epic 5 feasibility calculations', () => {
  it('calculates and caps the POI density score', () => {
    expect(calculatePoiScore(16)).toBe(80);
    expect(calculatePoiScore(20)).toBe(100);
    expect(calculatePoiScore(25)).toBe(100);
  });

  it('calculates and caps the network overlap score', () => {
    expect(calculateOverlapScore(4)).toBe(80);
    expect(calculateOverlapScore(5)).toBe(100);
    expect(calculateOverlapScore(6)).toBe(100);
  });

  it('combines road and residential activity points', () => {
    expect(calculateActivityScore('primary', 35)).toBe(85);
    expect(calculateActivityScore('secondary', 20)).toBe(55);
    expect(calculateActivityScore('local', 50)).toBe(65);
  });

  it('weights and rounds only the final location score', () => {
    expect(calculateLocationScore(88, 80, 95, 85)).toBe(86);
    expect(calculateLocationScore(81, 73, 67, 54)).toBe(72);
  });
});

describe('Epic 5 dynamic classifications', () => {
  it('uses the heatmap description thresholds', () => {
    expect(getHeatmapDescription(80)).toContain('Red Zone');
    expect(getHeatmapDescription(40)).toContain('Yellow Zone');
    expect(getHeatmapDescription(39)).toContain('Green Zone');
  });

  it('uses the POI density thresholds', () => {
    expect(getPoiDescription(80, 16)).toBe('16 Commercial POIs • High density');
    expect(getPoiDescription(40, 8)).toContain('Moderate density');
    expect(getPoiDescription(39, 4)).toContain('Low density');
  });

  it('uses the overlap risk thresholds', () => {
    expect(getOverlapDescription(80, 4)).toContain('Low network overlap risk');
    expect(getOverlapDescription(40, 2)).toContain('Moderate network overlap risk');
    expect(getOverlapDescription(39, 1.9)).toContain('High network overlap risk');
  });

  it('classifies payback periods at the boundaries', () => {
    expect(getPaybackStatus(2.9)).toBe('Rapid capital recovery');
    expect(getPaybackStatus(3)).toBe('Standard capital recovery');
    expect(getPaybackStatus(5)).toBe('Standard capital recovery');
    expect(getPaybackStatus(5.1)).toBe('Long-term capital recovery');
  });
});

describe('Epic 5 nearby station and marker selection logic', () => {
  const stations = [
    { id: 'far', name: 'Far', distanceKm: 5.1, averageDailySessions: 1, averageWeeklySessions: 7, averageMonthlySessions: 30 },
    { id: 'second', name: 'Second', distanceKm: 2, averageDailySessions: 1, averageWeeklySessions: 7, averageMonthlySessions: 30 },
    { id: 'first', name: 'First', distanceKm: 1, averageDailySessions: 1, averageWeeklySessions: 7, averageMonthlySessions: 30 },
    { id: 'edge', name: 'Edge', distanceKm: 5, averageDailySessions: 1, averageWeeklySessions: 7, averageMonthlySessions: 30 }
  ];

  it('filters to five kilometres inclusively and sorts without mutating input', () => {
    const filtered = getNearbyStationsWithinRadius(stations);
    expect(filtered.map((station) => station.id)).toEqual(['second', 'first', 'edge']);
    expect(sortStationsByDistance(filtered).map((station) => station.id)).toEqual(['first', 'second', 'edge']);
    expect(filtered[0]?.id).toBe('second');
  });

  it('resolves Optimal Sites but ignores SPKLU and POI marker IDs', () => {
    const sites = generateMockOptimalSites(jakartaViewport);
    expect(resolveOptimalSite(sites, 'mock-optimal-94')?.score).toBe(94);
    expect(resolveOptimalSite(sites, 'spklu-menteng')).toBeNull();
    expect(resolveOptimalSite(sites, 'poi-mall')).toBeNull();
  });

  it('provides stable feasibility data for every generated Optimal Site', async () => {
    const sites = generateMockOptimalSites(jakartaViewport);
    const records = await Promise.all(sites.map((site) => getSiteFeasibility(site.id)));
    expect(records.map((record) => record.optimalSiteId)).toEqual(sites.map((site) => site.id));
    expect(records.every((record) => record.locationCode.startsWith('LOC-JKT-'))).toBe(true);
  });
});
