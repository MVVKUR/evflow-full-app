export type MockNearbyStationPerformance = {
  averageDailySessions: number;
  dailySessionsTrendPct: number;
  monthlyRevenueIdr: number;
  monthlyRevenueTrendPct: number;
};

export type TrendPresentation = {
  text: string;
  tone: 'positive' | 'negative' | 'neutral';
};

/**
 * Temporary deterministic prototype data. The planner benchmark API does not
 * yet expose historical station sessions, revenue, or trends.
 */
export function getMockNearbyStationPerformance(station: { id: string }): MockNearbyStationPerformance {
  const seed = stableHash(station.id);
  return {
    averageDailySessions: 12 + seed % 10,
    dailySessionsTrendPct: signedTrend(seed, 7, 12),
    monthlyRevenueIdr: (18 + Math.floor(seed / 17) % 15) * 1_000_000,
    monthlyRevenueTrendPct: signedTrend(seed, 29, 10)
  };
}

export function getTrendPresentation(value: number): TrendPresentation {
  const percentage = Math.round(Math.abs(value));
  if (value > 0) return { text: `↗ ${percentage}%`, tone: 'positive' };
  if (value < 0) return { text: `↘ ${percentage}%`, tone: 'negative' };
  return { text: '0%', tone: 'neutral' };
}

function stableHash(value: string) {
  return [...value].reduce((hash, character) => (hash * 31 + character.charCodeAt(0)) % 2_147_483_647, 17);
}

function signedTrend(seed: number, divisor: number, radius: number) {
  return Math.floor(seed / divisor) % (radius * 2 + 1) - radius;
}
