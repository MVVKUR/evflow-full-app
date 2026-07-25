import type { Station } from '../types';

export interface RouteLocationInput {
  latitude: number;
  longitude: number;
  label?: string;
}

export interface RoutePreferencesInput {
  route_type?: string;
  maximum_detour_km?: number;
  prefer_fast_charging?: boolean;
}

export interface RoutePlanRequest {
  origin: RouteLocationInput;
  destination: RouteLocationInput;
  current_soc_pct: number;
  minimum_arrival_soc_pct?: number;
  preferences?: RoutePreferencesInput;
  waypoint_station_id?: string;
}

export interface VehicleSummary {
  id: string;
  name: string;
  battery_kwh: number;
  efficiency_wh_per_km: number;
  efficiency_source: string;
}

export interface TripSummary {
  distance_km: number;
  duration_minutes: number;
  estimated_energy_kwh: number;
  estimated_arrival_soc_pct: number;
  minimum_arrival_soc_pct: number;
}

export interface RouteGeometry {
  type: string;
  coordinates: [number, number][];
}

export interface RouteStep {
  instruction: string;
  name?: string;
  distance_m?: number;
  duration_s?: number;
  location?: [number, number];
}

export interface RoutePlanGeometryAndSteps {
  type: string;
  geometry: RouteGeometry;
  steps: RouteStep[];
}

export interface RecommendedStop {
  station: Station;
  distance_from_origin_km: number;
  detour_km: number;
  arrival_soc_pct: number;
  recommended_target_soc_pct: number;
  energy_to_add_kwh: number;
  estimated_charging_minutes: number;
  effective_charging_power_kw: number;
  connector_compatible: boolean;
  availability: string;
  data_confidence: string;
}

export interface RoutePlanAssumptions {
  reserve_soc_pct: number;
  weather_applied: boolean;
  traffic_applied: boolean;
  connector_data_inferred: boolean;
  energy_model_version: string;
}

export interface RoutePlanResponse {
  route_plan_id: string;
  directly_reachable: boolean;
  vehicle: VehicleSummary;
  summary: TripSummary;
  route: RoutePlanGeometryAndSteps;
  recommended_stop?: RecommendedStop | null;
  assumptions: RoutePlanAssumptions;
}

export interface GeocodingItem {
  id: string;
  label: string;
  subtitle: string;
  latitude: number;
  longitude: number;
  distance_km?: number | null;
  type: 'place' | 'station';
  station?: Station | null;
  attribution: string;
}

export interface GeocodingSearchResponse {
  query: string;
  items: GeocodingItem[];
}
