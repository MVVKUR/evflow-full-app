export type RoadType = 'primary' | 'secondary' | 'local';

export type FinancialProjection = {
  sessionsPerDay: number;
  energyPerDayKwh: number;
  monthlyRevenueIdr: number;
  paybackYears: number;
};

export type NearbyStationBenchmark = {
  id: string;
  name: string;
  distanceKm: number;
  averageDailySessions: number;
  averageWeeklySessions: number;
  averageMonthlySessions: number;
};

export type SiteFeasibilityData = {
  optimalSiteId: string;
  locationCode: string;
  locationName: string;
  heatmapScore: number;
  commercialPoiCount: number;
  nearestSpkluDistanceKm: number;
  roadType: RoadType;
  residentialPoints: number;
  financial: FinancialProjection;
  nearbyStations: NearbyStationBenchmark[];
};

export type SiteFeasibilityTab = 'feasibility' | 'financial' | 'nearby';

export type SiteFeasibilityScores = {
  heatmap: number;
  poi: number;
  overlap: number;
  activity: number;
  location: number;
};
