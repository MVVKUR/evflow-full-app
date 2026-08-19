import { describe, expect, it, vi } from 'vitest';

vi.mock('react-native', () => ({ NativeModules: {} }));

import type { PlannerBenchmarkResponse, PlannerCellDetailApi } from '@evflow/shared';
import { calculateSiteScores } from './siteFeasibilityLogic';
import { plannerCellToSiteFeasibility, roadTypeFromNodes } from './siteFeasibilityData';

const provenance = { population_source: 'projection', features_source: 'OSM', demand_basis: 'coverage', cell_size_m: 500 };
const detail: PlannerCellDetailApi = {
  cell_id: 'JBDTBK_22311', kota: 'Kota Jakarta Barat', latitude: -6.17, longitude: 106.7,
  score: 0.7449, rank_overall: 10, cells_total: 27219, in_scored_set: true, overlap_frac: 1,
  population: 1000, poi: { total: 6, mall: 1 }, land_use: { residential: 0.4 },
  road_nodes: 25, road_length_m: 1200, station_count: 0, connector_count: 0,
  nearest_station_m: 2000, stations_2km: 1, provenance
};
const benchmark: PlannerBenchmarkResponse = {
  cell_id: detail.cell_id, radius_km: 5, provenance,
  stations: [{ id: 'station-a', name: 'Station A', operator: 'PLN', power_kw: 50, speed_tier: 'fast', distance_m: 1200, available_connectors: 2, total_connectors: 4 }]
};

describe('planner cell feasibility adapter', () => {
  it('keeps the backend suitability score authoritative and converts metres to kilometres', () => {
    const data = plannerCellToSiteFeasibility(detail, benchmark);
    expect(data.locationCode).toBe('JBDTBK_22311');
    expect(data.locationName).toBe('Jakarta Barat');
    expect(data.nearestSpkluDistanceKm).toBe(2);
    expect(calculateSiteScores(data).location).toBe(74);
  });

  it('carries real station identity, distance and connector availability', () => {
    const [station] = plannerCellToSiteFeasibility(detail, benchmark).nearbyStations;
    expect(station).toMatchObject({
      id: 'station-a', name: 'Station A', distanceKm: 1.2,
      availableConnectors: 2, totalConnectors: 4
    });
  });

  it('documents the temporary road-node classification boundary', () => {
    expect(roadTypeFromNodes(20)).toBe('primary');
    expect(roadTypeFromNodes(8)).toBe('secondary');
    expect(roadTypeFromNodes(7)).toBe('local');
  });
});
