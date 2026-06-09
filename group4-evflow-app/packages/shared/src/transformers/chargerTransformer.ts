import type { Charger } from '../types';

type ChargerApiResponse = {
  id: string;
  display_name: string;
  location: {
    address: string;
    lat: number;
    lng: number;
  };
  status: Charger['status'];
  connectors: string[];
  max_power_kw: number;
};

export function toCharger(response: ChargerApiResponse): Charger {
  return {
    id: response.id,
    name: response.display_name,
    address: response.location.address,
    latitude: response.location.lat,
    longitude: response.location.lng,
    status: response.status,
    connectorTypes: response.connectors,
    maxPowerKw: response.max_power_kw
  };
}

