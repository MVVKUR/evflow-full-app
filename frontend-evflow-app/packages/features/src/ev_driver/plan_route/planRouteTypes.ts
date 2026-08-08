import type { GeocodingItem, RoutePlanResponse } from '@evflow/shared';

export type RouteViewMode = 'input' | 'simulation' | 'active_navigation' | 'completed';
export type PlanRouteViewMode = RouteViewMode;

export interface LocationState {
  latitude: number;
  longitude: number;
  label: string;
}

export interface PlanRouteState {
  origin: LocationState | null;
  destination: LocationState | null;
  currentSocPct: number;
  socInputText: string;
  isSimulating: boolean;
  error: string | null;
  simulationResult: RoutePlanResponse | null;
  searchQuery: string;
  searchResults: GeocodingItem[];
  isSearching: boolean;
  activeNavigationStepIndex: number;
}

/** Coordinates the user tagged on the map while choosing an origin or destination. */
export interface PickedMapPoint {
  latitude: number;
  longitude: number;
}
