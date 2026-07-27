import type { ManualVehicleInput, RecommendedStop, RouteLocationInput, RoutePlanRequest, RoutePreferencesInput } from '@evflow/shared';

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
  waypointStationId?: string;
}): RoutePlanRequest {
  return {
    origin: input.origin,
    destination: input.destination,
    current_soc_pct: input.currentSocPct,
    minimum_arrival_soc_pct: input.minimumArrivalSocPct,
    preferences: input.preferences,
    vehicle: input.manualVehicle,
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
