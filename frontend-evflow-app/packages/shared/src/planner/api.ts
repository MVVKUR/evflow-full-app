import { getAuthHeaders } from '../auth/session';
import { EVFLOW_API_BASE_URL } from '../stations/api';

export type PlannerWeights = {
  coverage: number;
  population: number;
  activity: number;
  roads: number;
};

export const defaultPlannerWeights: PlannerWeights = {
  coverage: 0.35,
  population: 0.35,
  activity: 0.2,
  roads: 0.1
};

export type PlannerProvenance = {
  population_source: string;
  features_source: string;
  demand_basis: string;
  cell_size_m: number;
};

export type PlannerCandidateApi = {
  cluster_id: number;
  cell_id: string;
  kota: string | null;
  score: number;
  latitude: number;
  longitude: number;
  population: number;
  poi_total: number;
  station_count: number;
  nearest_station_m: number | null;
  stations_2km: number;
  cluster_size: number;
};

export type PlannerCandidatesResponse = {
  weights_applied: Record<string, number>;
  candidates: PlannerCandidateApi[];
  excluded_areas: string[];
  provenance: PlannerProvenance;
};

export type PlannerCellProperties = {
  cell_id: string;
  kota: string | null;
  value: number | null;
  score: number | null;
  population: number;
  poi_total: number;
  station_count: number;
  nearest_station_m: number | null;
};

export type PlannerGeoJsonGeometry = {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: number[][][] | number[][][][];
};

export type PlannerCellsGeoJsonResponse = {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: PlannerGeoJsonGeometry;
    properties: PlannerCellProperties;
  }>;
  metric: string;
  weights_applied: Record<string, number>;
  cells_returned: number;
  cells_in_viewport: number;
  truncated: boolean;
  provenance: PlannerProvenance;
};

export type PlannerCellDetailApi = {
  cell_id: string;
  kota: string | null;
  latitude: number;
  longitude: number;
  score: number | null;
  rank_overall: number | null;
  cells_total: number;
  in_scored_set: boolean;
  overlap_frac: number | null;
  population: number;
  poi: Record<string, number>;
  land_use: Record<string, number>;
  road_nodes: number;
  road_length_m: number;
  station_count: number;
  connector_count: number;
  nearest_station_m: number | null;
  stations_2km: number;
  provenance: PlannerProvenance;
};

export type PlannerNearbyStationApi = {
  id: string;
  name: string | null;
  operator: string | null;
  power_kw: number | null;
  speed_tier: string | null;
  distance_m: number;
  available_connectors: number;
  total_connectors: number;
};

export type PlannerBenchmarkResponse = {
  cell_id: string;
  radius_km: number;
  stations: PlannerNearbyStationApi[];
  provenance: PlannerProvenance;
};

export type PlannerViewportRequest = {
  west: number;
  south: number;
  east: number;
  north: number;
  metric?: string;
  limit?: number;
  weights?: PlannerWeights;
  signal?: AbortSignal;
};

export class PlannerApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'PlannerApiError';
    this.status = status;
  }
}

export async function fetchPlannerCandidates(
  options: { clusters?: number; quantile?: number; weights?: PlannerWeights } = {},
  fetcher: typeof fetch = fetch
) {
  const query = new URLSearchParams({
    clusters: String(options.clusters ?? 15),
    quantile: String(options.quantile ?? 0.9)
  });
  return plannerRequest<PlannerCandidatesResponse>(`/api/v1/planner/candidates?${query}`, {
    body: JSON.stringify(options.weights ?? defaultPlannerWeights),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST'
  }, fetcher);
}

export async function fetchPlannerCells(request: PlannerViewportRequest, fetcher: typeof fetch = fetch) {
  const weights = request.weights ?? defaultPlannerWeights;
  const query = new URLSearchParams({
    bbox: [request.west, request.south, request.east, request.north].join(','),
    metric: request.metric ?? 'score',
    limit: String(request.limit ?? 10_000),
    coverage: String(weights.coverage),
    population: String(weights.population),
    activity: String(weights.activity),
    roads: String(weights.roads)
  });
  return plannerRequest<PlannerCellsGeoJsonResponse>(`/api/v1/planner/cells.geojson?${query}`, {
    signal: request.signal
  }, fetcher);
}

export function fetchPlannerCell(cellId: string, fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerCellDetailApi>(`/api/v1/planner/cells/${encodeURIComponent(cellId)}`, {}, fetcher);
}

export function fetchPlannerBenchmark(cellId: string, radiusKm = 5, fetcher: typeof fetch = fetch, limit = 10) {
  const query = new URLSearchParams({ radius_km: String(radiusKm), limit: String(limit) });
  return plannerRequest<PlannerBenchmarkResponse>(
    `/api/v1/planner/benchmark/${encodeURIComponent(cellId)}?${query}`,
    {},
    fetcher
  );
}

async function plannerRequest<T>(path: string, init: RequestInit, fetcher: typeof fetch): Promise<T> {
  const authHeaders = getAuthHeaders();
  if (!authHeaders) throw new PlannerApiError(401, 'Sign in with a Business Planner account to load planning data.');

  const response = await fetcher(`${EVFLOW_API_BASE_URL}${path}`, {
    ...init,
    headers: { ...authHeaders, ...init.headers }
  });
  if (!response.ok) throw new PlannerApiError(response.status, await plannerErrorMessage(response));
  return response.json() as Promise<T>;
}

async function plannerErrorMessage(response: Response) {
  try {
    const payload = await response.clone().json() as { detail?: unknown };
    if (typeof payload.detail === 'string') return payload.detail;
  } catch {
    // Use the role-aware fallback below.
  }
  if (response.status === 401) return 'Your session expired. Sign in again to load planning data.';
  if (response.status === 403) return 'This planning data requires a Business Planner account.';
  return `Planner API request failed with status ${response.status}.`;
}
