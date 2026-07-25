import type { GeocodingItem, RecommendedStop, RoutePlanResponse } from '@evflow/shared';

export type PlanRouteViewMode = 'input' | 'search' | 'simulation' | 'active_navigation';

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
