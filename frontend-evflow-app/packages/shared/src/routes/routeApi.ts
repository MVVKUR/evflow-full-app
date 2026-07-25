import { getEvflowApiBaseUrl } from '../api/baseUrl';
import { getAuthHeaders } from '../auth/session';
import type { GeocodingSearchResponse, RoutePlanRequest, RoutePlanResponse } from './routeTypes';

export async function createRoutePlan(request: RoutePlanRequest, signal?: AbortSignal): Promise<RoutePlanResponse> {
  const baseUrl = getEvflowApiBaseUrl();
  const authHeaders = getAuthHeaders();

  const response = await fetch(`${baseUrl}/api/v1/route-plans`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authHeaders || {}),
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    let errorDetail = 'Route simulation failed';
    try {
      const err = await response.json();
      errorDetail = err.detail || errorDetail;
    } catch {
      // Ignore JSON parse error
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export async function searchGeocoding(
  query: string,
  originLat?: number,
  originLon?: number,
  limit: number = 5,
  signal?: AbortSignal
): Promise<GeocodingSearchResponse> {
  const baseUrl = getEvflowApiBaseUrl();
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (originLat !== undefined && originLon !== undefined) {
    params.set('lat', String(originLat));
    params.set('lon', String(originLon));
  }

  const response = await fetch(`${baseUrl}/api/v1/geocoding/search?${params.toString()}`, {
    signal,
  });

  if (!response.ok) {
    throw new Error(`Geocoding search failed with status ${response.status}`);
  }

  return response.json();
}

export async function reverseGeocode(
  lat: number,
  lon: number,
  signal?: AbortSignal
): Promise<{ label: string; address: string; city: string }> {
  const baseUrl = getEvflowApiBaseUrl();
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });

  try {
    const response = await fetch(`${baseUrl}/api/v1/geocoding/reverse?${params.toString()}`, {
      signal,
    });

    if (!response.ok) {
      return { label: `Location (${lat.toFixed(4)}, ${lon.toFixed(4)})`, address: '', city: '' };
    }

    return response.json();
  } catch {
    return { label: `Location (${lat.toFixed(4)}, ${lon.toFixed(4)})`, address: '', city: '' };
  }
}

