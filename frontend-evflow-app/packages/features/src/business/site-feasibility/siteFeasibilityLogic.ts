import type { OptimalSite } from '../demandHeatmap';
import type {
  NearbyStationBenchmark,
  RoadType,
  SiteFeasibilityData,
  SiteFeasibilityScores
} from './siteFeasibilityTypes';

const trafficPoints: Record<RoadType, number> = { primary: 50, secondary: 35, local: 15 };

export function calculatePoiScore(commercialPoiCount: number) {
  return Math.min(Math.max(commercialPoiCount, 0) / 20 * 100, 100);
}

export function calculateOverlapScore(nearestSpkluDistanceKm: number) {
  return Math.min(Math.max(nearestSpkluDistanceKm, 0) / 5 * 100, 100);
}

export function calculateActivityScore(roadType: RoadType, residentialPoints: number) {
  return Math.min(trafficPoints[roadType] + Math.min(Math.max(residentialPoints, 0), 50), 100);
}

export function calculateLocationScore(heatmap: number, overlap: number, poi: number, activity: number) {
  return Math.round(0.4 * heatmap + 0.3 * overlap + 0.15 * poi + 0.15 * activity);
}

export function calculateSiteScores(data: SiteFeasibilityData): SiteFeasibilityScores {
  const poi = calculatePoiScore(data.commercialPoiCount);
  const overlap = calculateOverlapScore(data.nearestSpkluDistanceKm);
  const activity = calculateActivityScore(data.roadType, data.residentialPoints);
  return {
    heatmap: data.heatmapScore,
    poi,
    overlap,
    activity,
    location: data.locationScore ?? calculateLocationScore(data.heatmapScore, overlap, poi, activity)
  };
}

export function getLocationPriority(score: number) {
  return score >= 85 ? 'High Priority' : score >= 70 ? 'Moderate Priority' : 'Low Priority';
}

export function getHeatmapSummary(score: number) {
  return score >= 80 ? 'Located in Red Demand Zone' : score >= 40 ? 'Located in Yellow Demand Zone' : 'Located in Green Demand Zone';
}

export function getHeatmapDescription(score: number) {
  return score >= 80
    ? 'Red Zone • High priority for unmet demand'
    : score >= 40
      ? 'Yellow Zone • Moderate demand; monitor for future growth'
      : 'Green Zone • Low priority due to limited commercial activity';
}

export function getPoiSummary(score: number) {
  return score >= 70 ? 'Strong Commercial Activity' : 'Limited Commercial Activity';
}

export function getPoiDescription(score: number, count: number) {
  const density = score >= 80 ? 'High density' : score >= 40 ? 'Moderate density' : 'Low density';
  return `${count} Commercial POIs • ${density}`;
}

export function getOverlapSummary(score: number) {
  return score >= 70 ? 'Low Network Overlap' : 'High Network Overlap';
}

export function getOverlapDescription(score: number, distanceKm: number) {
  const risk = score >= 80 ? 'Low' : score >= 40 ? 'Moderate' : 'High';
  return `Nearest SPKLU ${distanceKm.toFixed(1)} km away • ${risk} network overlap risk`;
}

export function getActivityDescription(roadType: RoadType, residentialPoints: number) {
  const traffic = roadType === 'primary' ? 'Heavy traffic volume' : roadType === 'secondary' ? 'Moderate traffic flow' : 'Local traffic only';
  const residential = residentialPoints >= 40 ? 'High-density residential' : residentialPoints >= 20 ? 'Moderate residential zone' : 'Low-density residential';
  return `${traffic} • ${residential}`;
}

export function getPaybackStatus(paybackYears: number) {
  return paybackYears < 3 ? 'Rapid capital recovery' : paybackYears <= 5 ? 'Standard capital recovery' : 'Long-term capital recovery';
}

export function formatRevenueIdr(value: number) {
  if (value >= 1_000_000) return `Rp. ${new Intl.NumberFormat('id-ID', { maximumFractionDigits: 1 }).format(value / 1_000_000)} Juta`;
  return `Rp. ${new Intl.NumberFormat('id-ID').format(value)}`;
}

export function getNearbyStationsWithinRadius(stations: NearbyStationBenchmark[], radiusKm = 5) {
  return stations.filter((station) => station.distanceKm <= radiusKm);
}

export function sortStationsByDistance(stations: NearbyStationBenchmark[]) {
  return [...stations].sort((left, right) => left.distanceKm - right.distanceKm);
}

export function resolveOptimalSite(sites: OptimalSite[], markerId: string) {
  return sites.find((site) => site.id === markerId) ?? null;
}
