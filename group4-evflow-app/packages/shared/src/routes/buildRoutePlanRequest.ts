import type { RoutePlanRequest } from '../types';

export function buildRoutePlanRequest(input: RoutePlanRequest): RoutePlanRequest {
  return {
    origin: input.origin.trim(),
    destination: input.destination.trim(),
    vehicleRangeKm: input.vehicleRangeKm,
    preferredConnectorTypes: [...new Set(input.preferredConnectorTypes)]
  };
}

