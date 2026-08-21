import {
  fetchPlannerBenchmark,
  fetchPlannerCell,
  type PlannerBenchmarkResponse,
  type PlannerCellDetailApi
} from '@evflow/shared';
import { getMockSiteFeasibility } from './siteFeasibilityMockData';
import { getMockNearbyStationPerformance } from './nearbyStationPerformance';
import type { NearbyStationBenchmark, RoadType, SiteFeasibilityData } from './siteFeasibilityTypes';

export async function getSiteFeasibility(siteId: string): Promise<SiteFeasibilityData> {
  if (siteId.startsWith('mock-optimal-')) return getMockSiteFeasibility(siteId);

  const [detail, benchmarkResult] = await Promise.all([
    fetchPlannerCell(siteId),
    fetchPlannerBenchmark(siteId).catch(() => null)
  ]);
  return plannerCellToSiteFeasibility(detail, benchmarkResult);
}

export function plannerCellToSiteFeasibility(
  detail: PlannerCellDetailApi,
  benchmark: PlannerBenchmarkResponse | null
): SiteFeasibilityData {
  const score = Math.round(Math.min(Math.max(detail.score ?? 0, 0), 1) * 100);
  return {
    optimalSiteId: detail.cell_id,
    locationCode: detail.cell_id,
    locationName: cleanAreaName(detail.kota),
    locationScore: score,
    heatmapScore: score,
    commercialPoiCount: Math.max(0, detail.poi.total ?? sumPoi(detail.poi)),
    nearestSpkluDistanceKm: detail.nearest_station_m === null ? 5 : detail.nearest_station_m / 1000,
    roadType: roadTypeFromNodes(detail.road_nodes),
    residentialPoints: Math.round(Math.min(Math.max(detail.land_use.residential ?? 0, 0), 1) * 50),
    financial: null,
    nearbyStations: benchmark ? benchmarkStations(benchmark) : []
  };
}

export function roadTypeFromNodes(roadNodes: number): RoadType {
  if (roadNodes >= 20) return 'primary';
  if (roadNodes >= 8) return 'secondary';
  return 'local';
}

function benchmarkStations(response: PlannerBenchmarkResponse): NearbyStationBenchmark[] {
  return response.stations.map((station) => ({
    id: station.id,
    name: station.name ?? station.operator ?? 'Unnamed SPKLU',
    distanceKm: station.distance_m / 1000,
    ...getMockNearbyStationPerformance(station),
    availableConnectors: station.available_connectors,
    totalConnectors: station.total_connectors
  }));
}

function cleanAreaName(value: string | null) {
  return value?.replace(/^(Kota|Kabupaten)\s+/i, '').trim() || 'Jabodetabek Opportunity Zone';
}

function sumPoi(poi: Record<string, number>) {
  return Object.entries(poi).reduce((total, [key, value]) => key === 'total' ? total : total + value, 0);
}
