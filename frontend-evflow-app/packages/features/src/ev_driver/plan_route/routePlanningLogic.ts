import type { ManualVehicleInput, RecommendedStop, RouteLocationInput, RoutePlanRequest, RoutePlanResponse, RoutePreferencesInput } from '@evflow/shared';

export type RouteInputField = 'origin' | 'destination' | 'current_soc_pct' | 'minimum_arrival_soc_pct' | 'vehicle' | 'preferences';
export type RouteInputErrors = Partial<Record<RouteInputField, string>>;
export type ChargingPreference = 'fastest' | 'least_detour' | 'available_now';
export type RoutePresentation = 'direct' | 'charging_recommended' | 'charging_added' | 'no_suitable_station';
export type LocationEntryDecision = 'use_location' | 'request_permission' | 'manual_or_retry';

export function locationEntryDecision(status: string, hasCoordinates: boolean): LocationEntryDecision {
  if (hasCoordinates) return 'use_location';
  if (status === 'undetermined') return 'request_permission';
  return 'manual_or_retry';
}

export function routePresentation(result: RoutePlanResponse): RoutePresentation {
  if (result.route_status === 'no_suitable_station' || result.warning?.code === 'no_suitable_station') return 'no_suitable_station';
  if (result.user_requested_stop) return 'charging_added';
  if (result.route_status === 'direct_route_available' || result.directly_reachable) return 'direct';
  return 'charging_recommended';
}

export function canStartNavigation(result: RoutePlanResponse): boolean {
  const presentation = routePresentation(result);
  return presentation === 'direct' || presentation === 'charging_added';
}

export function preferencesForChoice(choice: ChargingPreference, current: Required<RoutePreferencesInput>): Required<RoutePreferencesInput> {
  if (choice === 'least_detour') return { ...current, route_type: 'shortest', prefer_fast_charging: false };
  if (choice === 'available_now') return { ...current, route_type: 'fastest', prefer_fast_charging: false };
  return { ...current, route_type: 'fastest', prefer_fast_charging: true };
}

export function choiceForPreferences(preferences: Required<RoutePreferencesInput>): ChargingPreference {
  if (preferences.route_type === 'shortest') return 'least_detour';
  return preferences.prefer_fast_charging ? 'fastest' : 'available_now';
}

export function validateRouteInput(input: {
  origin: RouteLocationInput | null;
  destination: RouteLocationInput | null;
  currentSocPct: number;
  minimumArrivalSocPct: number;
  hasVehicle: boolean;
}): RouteInputErrors {
  const errors: RouteInputErrors = {};
  if (!input.origin) errors.origin = 'Choose a starting location.';
  if (!input.destination) errors.destination = 'Choose a destination.';
  if (!Number.isFinite(input.currentSocPct) || input.currentSocPct < 0 || input.currentSocPct > 100) errors.current_soc_pct = 'Enter a battery level from 0% to 100%.';
  if (!Number.isFinite(input.minimumArrivalSocPct) || input.minimumArrivalSocPct < 0 || input.minimumArrivalSocPct > 50) errors.minimum_arrival_soc_pct = 'Reserve must be from 0% to 50%.';
  if (!input.hasVehicle) errors.vehicle = 'Select a vehicle profile or enter a usable range above zero.';
  if (input.origin && input.destination && Math.abs(input.origin.latitude - input.destination.latitude) < 0.000001 && Math.abs(input.origin.longitude - input.destination.longitude) < 0.000001) errors.destination = 'Destination must be different from the origin.';
  return errors;
}

export function clearFieldError(errors: RouteInputErrors, field: RouteInputField): RouteInputErrors {
  if (!errors[field]) return errors;
  const next = { ...errors };
  delete next[field];
  return next;
}

export function noSuitableStationReasons(stops: RecommendedStop[]): string[] {
  const reasons: string[] = [];
  if (stops.some((stop) => stop.detour_within_budget === false)) reasons.push('Some stations exceed the reachable detour corridor.');
  if (stops.some((stop) => !stop.connector_compatible)) reasons.push('Some stations lack a compatible connector.');
  if (stops.some((stop) => stop.connector_compatible && (stop.available_connector_count ?? 0) < 1)) reasons.push('Compatible stations currently have no free connector.');
  return reasons.length ? reasons : ['No candidate currently satisfies the route safety constraints.'];
}

export function hasUsableVehicle(hasProfile: boolean, manualVehicle: ManualVehicleInput): boolean {
  return hasProfile || Number.isFinite(manualVehicle.usable_range_km) && manualVehicle.usable_range_km > 0;
}

export function buildRouteRequest(input: {
  origin: RouteLocationInput;
  destination: RouteLocationInput;
  currentSocPct: number;
  minimumArrivalSocPct: number;
  preferences: Required<RoutePreferencesInput>;
  manualVehicle?: ManualVehicleInput;
  evModelId?: string;
  waypointStationId?: string;
}): RoutePlanRequest {
  return {
    origin: input.origin,
    destination: input.destination,
    current_soc_pct: input.currentSocPct,
    minimum_arrival_soc_pct: input.minimumArrivalSocPct,
    preferences: input.preferences,
    vehicle: input.manualVehicle,
    ev_model_id: input.evModelId,
    waypoint_station_id: input.waypointStationId,
  };
}

const noStationLabels: Record<string, string> = {
  choose_another_route: 'Choose another route',
  adjust_preferences: 'Adjust preferences',
  charge_before_departure: 'Charge before departure',
};

export function noStationActions(actions?: string[]): Array<{ code: string; label: string }> {
  const requested = actions?.length ? actions : Object.keys(noStationLabels);
  return requested.flatMap((code) => noStationLabels[code] ? [{ code, label: noStationLabels[code] }] : []);
}

export function formatRouteEta(value?: string | null): string {
  if (!value) return 'ETA unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'ETA unavailable';
  return `Arrives ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

export function suitableActiveStops(stops: RecommendedStop[], limit = 3): RecommendedStop[] {
  return stops
    .filter((stop) => stop.connector_compatible && (stop.available_connector_count ?? 0) > 0)
    .slice(0, limit);
}

export function nonIncreasingDrivingSoc(previousSocPct: number, backendSocPct: number): number {
  return Math.max(0, Math.min(previousSocPct, backendSocPct));
}
