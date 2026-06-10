export type ChargerStatus = 'available' | 'occupied' | 'offline';

export type Charger = {
  id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  status: ChargerStatus;
  connectorTypes: string[];
  maxPowerKw: number;
};

export type ChargerFilter = {
  query?: string;
  connectorTypes?: string[];
  minPowerKw?: number;
  onlyAvailable?: boolean;
};

export type RoutePlanRequest = {
  origin: string;
  destination: string;
  vehicleRangeKm: number;
  preferredConnectorTypes: string[];
};

