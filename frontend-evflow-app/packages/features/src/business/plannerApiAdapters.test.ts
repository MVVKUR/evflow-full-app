import { describe, expect, it } from 'vitest';
import type { PlannerCandidateApi, PlannerCellsGeoJsonResponse, StationApiItem } from '@evflow/shared';
import {
  plannerCandidateToOptimalSite,
  plannerCellsToMetricPolygons,
  plannerCellsToPolygons,
  plannerLandUseToPolygons,
  plannerStationsToMarkers,
  scoreToDemandPriority
} from './plannerApiAdapters';

describe('planner API adapters', () => {
  it('converts normalized candidate scores and real cell IDs without inventing coordinates', () => {
    const candidate: PlannerCandidateApi = {
      cluster_id: 1, cell_id: 'JBDTBK_13989', kota: 'Kota Jakarta Selatan', score: 0.864,
      latitude: -6.22, longitude: 106.81, population: 1000, poi_total: 19,
      station_count: 0, nearest_station_m: 4000, stations_2km: 0, cluster_size: 30
    };
    expect(plannerCandidateToOptimalSite(candidate)).toEqual({
      id: 'JBDTBK_13989', district: 'Jakarta Selatan', score: 86,
      latitude: -6.22, longitude: 106.81
    });
  });

  it('swaps GeoJSON longitude/latitude into Leaflet latitude/longitude', () => {
    const response = {
      features: [{
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [[[106.8, -6.2], [106.81, -6.2], [106.8, -6.21], [106.8, -6.2]]] },
        properties: { cell_id: 'cell-1', kota: null, value: 0.8, score: 0.8, population: 1, poi_total: 1, station_count: 0, nearest_station_m: null }
      }]
    } as PlannerCellsGeoJsonResponse;
    const [polygon] = plannerCellsToPolygons(response);
    expect(polygon?.coordinates[0]).toEqual([-6.2, 106.8]);
    expect(polygon?.fillColor).toBe('#ef4444');
  });

  it('maps the documented frontend semantic bands at their boundaries', () => {
    expect(scoreToDemandPriority(0.75)).toBe('high');
    expect(scoreToDemandPriority(0.5)).toBe('moderate');
    expect(scoreToDemandPriority(0.49)).toBe('low');
  });

  it('turns positive planner metrics into geographically anchored density polygons', () => {
    const response = metricResponse('cell-1', 25);
    const [polygon] = plannerCellsToMetricPolygons(response, '#123456', 'population');
    expect(polygon).toMatchObject({
      id: 'population-cell-1-0',
      fillColor: '#123456'
    });
    expect(polygon?.coordinates[0]).toEqual([-6.2, 106.8]);
  });

  it('classifies each cell by its dominant land-use API metric', () => {
    const [polygon] = plannerLandUseToPolygons({
      commercial: metricResponse('cell-1', 0.2),
      residential: metricResponse('cell-1', 0.8)
    });
    expect(polygon?.fillColor).toBe('#8B5CF6');
  });

  it('prefixes real station IDs so station taps cannot resolve as optimal sites', () => {
    const station = {
      id: 'station-1', name: 'SPKLU Test', latitude: -6.2, longitude: 106.8
    } as StationApiItem;
    expect(plannerStationsToMarkers([station])[0]).toMatchObject({
      id: 'station:station-1',
      label: 'SPKLU Test',
      type: 'station'
    });
  });
});

function metricResponse(cellId: string, value: number): PlannerCellsGeoJsonResponse {
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [[[106.8, -6.2], [106.81, -6.2], [106.8, -6.21], [106.8, -6.2]]]
      },
      properties: {
        cell_id: cellId, kota: null, value, score: 0.8, population: 1,
        poi_total: 1, station_count: 0, nearest_station_m: null
      }
    }],
    metric: 'score',
    weights_applied: {},
    cells_returned: 1,
    cells_in_viewport: 1,
    truncated: false,
    provenance: {
      population_source: 'mock', features_source: 'mock', demand_basis: 'mock', cell_size_m: 500
    }
  };
}
