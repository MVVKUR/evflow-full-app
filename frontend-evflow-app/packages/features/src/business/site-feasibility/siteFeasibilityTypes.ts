export type RoadType = 'primary' | 'secondary' | 'local';

export type FinancialProjection = {
  sessionsPerDay: number;
  energyPerDayKwh: number;
  monthlyRevenueIdr: number;
  paybackYears: number | null;
  breaksEven: boolean;
  utilisation?: number;
  capacitySessionsPerDay?: number;
  demandBasis?: string;
  costBasis?: string;
  inputSources?: Record<string, string>;
  projectionKind: 'backend' | 'mock';
};

export type NearbyStationBenchmark = {
  id: string;
  name: string;
  distanceKm: number;
  averageDailySessions: number;
  dailySessionsTrendPct: number;
  monthlyRevenueIdr: number;
  monthlyRevenueTrendPct: number;
  availableConnectors?: number;
  totalConnectors?: number;
};

export type SiteFeasibilityData = {
  optimalSiteId: string;
  locationCode: string;
  locationName: string;
  locationScore?: number;
  heatmapScore: number;
  commercialPoiCount: number;
  nearestSpkluDistanceKm: number;
  roadType: RoadType;
  residentialPoints: number;
  financial: FinancialProjection | null;
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
