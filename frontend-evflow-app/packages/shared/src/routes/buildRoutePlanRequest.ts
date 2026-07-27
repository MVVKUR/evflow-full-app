export interface RoutePlanInputLegacy {
  origin: string;
  destination: string;
  vehicleRangeKm: number;
  preferredConnectorTypes: string[];
}

export function buildRoutePlanRequest(input: RoutePlanInputLegacy) {
  return {
    origin: input.origin.trim(),
    destination: input.destination.trim(),
    vehicleRangeKm: input.vehicleRangeKm,
    preferredConnectorTypes: [...new Set(input.preferredConnectorTypes)]
  };
}

