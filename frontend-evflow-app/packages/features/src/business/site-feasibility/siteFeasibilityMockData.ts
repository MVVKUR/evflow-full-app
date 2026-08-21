import type { SiteFeasibilityData } from './siteFeasibilityTypes';

const commonNearbyStations = [
  { id: 'nearby-thamrin', name: 'SPKLU PLN Sukses Thamrin Hub', distanceKm: 1.2, averageDailySessions: 16, averageWeeklySessions: 108, averageMonthlySessions: 472 },
  { id: 'nearby-voltron', name: 'SPKLU Voltron', distanceKm: 1.8, averageDailySessions: 17, averageWeeklySessions: 116, averageMonthlySessions: 501 },
  { id: 'nearby-kuningan', name: 'SPKLU Kuningan City', distanceKm: 3.6, averageDailySessions: 14, averageWeeklySessions: 96, averageMonthlySessions: 418 },
  { id: 'nearby-outside', name: 'SPKLU Kelapa Gading', distanceKm: 6.4, averageDailySessions: 12, averageWeeklySessions: 82, averageMonthlySessions: 352 }
];

const siteMetadata: Record<string, Pick<SiteFeasibilityData, 'locationCode' | 'locationName'>> = {
  'mock-optimal-94': { locationCode: 'LOC-JKT-8821', locationName: 'Senayan Corridor' },
  'mock-optimal-88': { locationCode: 'LOC-JKT-7314', locationName: 'Menteng Central' },
  'mock-optimal-82': { locationCode: 'LOC-JKT-6042', locationName: 'Kemang Corridor' },
  'mock-optimal-76': { locationCode: 'LOC-JKT-5198', locationName: 'Puri Growth Zone' },
  'mock-optimal-72': { locationCode: 'LOC-JKT-4431', locationName: 'Cakung Commercial' }
};

const primarySite: SiteFeasibilityData = {
  optimalSiteId: 'mock-optimal-94',
  locationCode: 'LOC-JKT-8821',
  locationName: 'Senayan Corridor',
  heatmapScore: 88,
  commercialPoiCount: 19,
  nearestSpkluDistanceKm: 4,
  roadType: 'primary',
  residentialPoints: 35,
  financial: {
    sessionsPerDay: 18,
    energyPerDayKwh: 324,
    monthlyRevenueIdr: 24_000_000,
    paybackYears: 2.9,
    breaksEven: true,
    projectionKind: 'mock'
  },
  nearbyStations: commonNearbyStations
};

function createFallbackSite(siteId: string): SiteFeasibilityData {
  const markerScore = Number(siteId.match(/(\d+)$/)?.[1] ?? 80);
  const metadata = siteMetadata[siteId] ?? {
    locationCode: `LOC-JKT-${String(4000 + markerScore * 13).padStart(4, '0')}`,
    locationName: 'Jakarta Opportunity Zone'
  };
  const offset = markerScore % 5;
  return {
    optimalSiteId: siteId,
    ...metadata,
    heatmapScore: Math.min(95, markerScore),
    commercialPoiCount: 13 + offset,
    nearestSpkluDistanceKm: 2.8 + offset * 0.25,
    roadType: markerScore >= 82 ? 'primary' : markerScore >= 76 ? 'secondary' : 'local',
    residentialPoints: 26 + offset * 3,
    financial: {
      sessionsPerDay: 13 + offset,
      energyPerDayKwh: (13 + offset) * 18,
      monthlyRevenueIdr: (18 + offset) * 1_000_000,
      paybackYears: 3.1 + offset * 0.25,
      breaksEven: true,
      projectionKind: 'mock'
    },
    nearbyStations: commonNearbyStations.map((station, index) => ({ ...station, distanceKm: station.distanceKm + index * 0.15 + offset * 0.1 }))
  };
}

export function getMockSiteFeasibility(siteId: string): SiteFeasibilityData {
  return siteId === primarySite.optimalSiteId ? primarySite : createFallbackSite(siteId);
}
