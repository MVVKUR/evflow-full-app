import type { Charger, ChargerFilter } from '../types';

export function filterChargers(chargers: Charger[], filter: ChargerFilter): Charger[] {
  const query = filter.query?.trim().toLowerCase();

  return chargers.filter((charger) => {
    const matchesQuery =
      !query ||
      charger.name.toLowerCase().includes(query) ||
      charger.address.toLowerCase().includes(query);
    const matchesConnectors =
      !filter.connectorTypes?.length ||
      filter.connectorTypes.some((connector) => charger.connectorTypes.includes(connector));
    const matchesPower = !filter.minPowerKw || charger.maxPowerKw >= filter.minPowerKw;
    const matchesStatus = !filter.onlyAvailable || charger.status === 'available';

    return matchesQuery && matchesConnectors && matchesPower && matchesStatus;
  });
}

