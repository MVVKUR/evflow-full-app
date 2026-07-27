import type { StationApiItem as Station } from '../stations/api';

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

export interface ManualVehicleInput {
  usable_range_km: number;
  battery_kwh?: number;
  name?: string;
  max_dc_charge_kw?: number;
  connector_type?: string;
}

export interface RoutePlanRequest {
  origin: RouteLocationInput;
  destination: RouteLocationInput;
  current_soc_pct: number;
  ev_model_id?: string;
  vehicle?: ManualVehicleInput;
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
  computed_at?: string | null;
  estimated_arrival_at?: string | null;
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
  leg_index?: number;
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
  matched_connector_type?: string | null;
  available_connector_count?: number;
  best_available_power_kw?: number | null;
  detour_within_budget?: boolean;
}

export interface RoutePlanAssumptions {
  reserve_soc_pct: number;
  weather_applied: boolean;
  traffic_applied: boolean;
  connector_data_inferred: boolean;
  energy_model_version: string;
  maximum_detour_km?: number;
  route_type?: 'fastest' | 'shortest' | string;
  prefer_fast_charging?: boolean;
}

export interface RoutePlanResponse {
  route_plan_id: string;
  route_status: 'direct_route_available' | 'charging_required' | 'no_suitable_station' | string;
  directly_reachable: boolean;
  vehicle: VehicleSummary;
  summary: TripSummary;
  route: RoutePlanGeometryAndSteps;
  recommended_stop?: RecommendedStop | null;
  user_requested_stop?: RecommendedStop | null;
  charging_stops?: RecommendedStop[];
  alternative_stops?: RecommendedStop[];
  warning?: RouteWarning | null;
  assumptions: RoutePlanAssumptions;
}

export interface ActiveRouteEvaluationRequest {
  route_plan_id: string;
  current_position: RouteLocationInput;
  destination: RouteLocationInput;
  current_soc_pct?: number;
  navigation_start_soc_pct?: number;
  cumulative_distance_travelled_km?: number;
  measured_current_soc_pct?: number;
  active_waypoint_station_id?: string;
  minimum_arrival_soc_pct?: number;
  maximum_detour_km?: number;
  ev_model_id?: string;
  vehicle?: ManualVehicleInput;
}

export interface ActiveRouteEvaluationResponse {
  route_plan_id?: string;
  route_status: 'direct_route_available' | 'charging_required' | 'no_suitable_station' | string;
  remaining_distance_km: number;
  remaining_duration_minutes: number;
  projected_arrival_soc_pct: number;
  estimated_current_soc_pct: number;
  current_soc_source: 'distance_estimate' | 'vehicle_telemetry' | 'legacy_current_soc' | string;
  remaining_energy_kwh: number;
  estimated_energy_kwh: number;
  energy_model_version: string;
  energy_assumptions: Record<string, string | number | boolean | null>;
  estimated_arrival_at?: string | null;
  candidate_stops: RecommendedStop[];
  warning?: RouteWarning | null;
}

export interface RouteWarning {
  triggered?: boolean;
  code: string;
  message: string;
  suggested_actions?: string[];
  severity?: string;
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
