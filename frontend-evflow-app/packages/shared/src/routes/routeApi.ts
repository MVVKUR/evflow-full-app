import { getEvflowApiBaseUrl } from '../api/baseUrl';
import { getAuthHeaders } from '../auth/session';
import type {
  ActiveRouteEvaluationRequest,
  ActiveRouteEvaluationResponse,
  GeocodingSearchResponse,
  RoutePlanRequest,
  RoutePlanResponse,
} from './routeTypes';
import { normaliseRouteApiError, RouteApiError } from './routeApiError';
export { normaliseRouteApiError, RouteApiError } from './routeApiError';

async function parseFailure(response: Response, fallback: string): Promise<RouteApiError> {
  const payload = await response.json().catch(() => null);
  return normaliseRouteApiError(response.status, payload, fallback);
}

function networkFailure(cause: unknown, fallback: string): never {
  if (cause instanceof RouteApiError || (cause as { name?: string })?.name === 'AbortError') throw cause;
  throw new RouteApiError({ message: fallback, isNetworkError: true });
}

export async function checkRouteApiHealth(signal?: AbortSignal): Promise<void> {
  try {
    const response = await fetch(`${getEvflowApiBaseUrl()}/health`, { signal });
    if (!response.ok) throw await parseFailure(response, 'EV-FLOW is unavailable');
  } catch (cause) {
    networkFailure(cause, 'EV-FLOW is still offline.');
  }
}

export async function createRoutePlan(request: RoutePlanRequest, signal?: AbortSignal): Promise<RoutePlanResponse> {
  try {
    const response = await fetch(`${getEvflowApiBaseUrl()}/api/v1/route-plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(getAuthHeaders() || {}) },
      body: JSON.stringify(request),
      signal,
    });
    if (!response.ok) throw await parseFailure(response, 'Route simulation failed');
    return response.json();
  } catch (cause) {
    networkFailure(cause, 'Unable to reach EV-FLOW. Check your connection and retry.');
  }
}

export async function evaluateActiveRoute(request: ActiveRouteEvaluationRequest, signal?: AbortSignal): Promise<ActiveRouteEvaluationResponse> {
  try {
    const response = await fetch(`${getEvflowApiBaseUrl()}/api/v1/route-plans/active/evaluate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...(getAuthHeaders() || {}) },
      body: JSON.stringify(request), signal,
    });
    if (!response.ok) throw await parseFailure(response, 'Route evaluation failed');
    return response.json();
  } catch (cause) {
    networkFailure(cause, 'Unable to update navigation. Check your connection and retry.');
  }
}

export async function deleteRoutePlan(routePlanId: string, signal?: AbortSignal): Promise<void> {
  try {
    const response = await fetch(`${getEvflowApiBaseUrl()}/api/v1/route-plans/${encodeURIComponent(routePlanId)}`, {
      method: 'DELETE', headers: { ...(getAuthHeaders() || {}) }, signal,
    });
    if (!response.ok && response.status !== 404) throw await parseFailure(response, 'Unable to end route session');
  } catch (cause) {
    networkFailure(cause, 'Unable to close the route session. Check your connection and retry.');
  }
}

export async function searchGeocoding(query: string, originLat?: number, originLon?: number, limit = 5, signal?: AbortSignal): Promise<GeocodingSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (originLat !== undefined && originLon !== undefined) {
    params.set('lat', String(originLat));
    params.set('lon', String(originLon));
  }
  try {
    const response = await fetch(`${getEvflowApiBaseUrl()}/api/v1/geocoding/search?${params.toString()}`, { signal });
    if (!response.ok) throw await parseFailure(response, 'Location search failed');
    return response.json();
  } catch (cause) {
    networkFailure(cause, 'Unable to search locations. Check your connection and retry.');
  }
}

export async function reverseGeocode(lat: number, lon: number, signal?: AbortSignal): Promise<{ label: string; address: string; city: string }> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  try {
    const response = await fetch(`${getEvflowApiBaseUrl()}/api/v1/geocoding/reverse?${params.toString()}`, { signal });
    if (!response.ok) throw await parseFailure(response, 'Reverse geocoding failed');
    return response.json();
  } catch (cause) {
    networkFailure(cause, 'Unable to name the current location.');
  }
}
