import { StyleSheet, Text, View } from 'react-native';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import { locationIcon } from './siteFeasibilityIcons';
import { getTrendPresentation, type TrendPresentation } from './nearbyStationPerformance';
import { formatRevenueIdr, getNearbyStationsWithinRadius, sortStationsByDistance } from './siteFeasibilityLogic';
import type { NearbyStationBenchmark } from './siteFeasibilityTypes';

export function NearbyStationsTab({ stations }: { stations: NearbyStationBenchmark[] }) {
  const nearby = sortStationsByDistance(getNearbyStationsWithinRadius(stations));
  return (
    <View>
      <Text style={styles.sectionTitle}>STATIONS WITHIN 5 KM</Text>
      {nearby.length ? nearby.map((station) => <StationCard key={station.id} station={station} />) : <Text style={styles.empty}>No existing SPKLUs within 5 km.</Text>}
    </View>
  );
}

function StationCard({ station }: { station: NearbyStationBenchmark }) {
  return (
    <View style={styles.card}>
      <Text style={styles.stationName}>{station.name}</Text>
      <View style={styles.distance}><SvgAssetIcon height={14} svg={locationIcon} width={14} /><Text style={styles.distanceText}>{station.distanceKm.toFixed(1)} km away</Text></View>
      <View accessibilityHint="Prototype performance until historical station data is available" style={styles.metrics}>
        <MetricBox
          label="Sessions/day"
          trend={getTrendPresentation(station.dailySessionsTrendPct)}
          value={String(station.averageDailySessions)}
        />
        <MetricBox
          label="Monthly Revenue"
          trend={getTrendPresentation(station.monthlyRevenueTrendPct)}
          value={formatRevenueIdr(station.monthlyRevenueIdr)}
        />
      </View>
    </View>
  );
}

function MetricBox({ label, trend, value }: { label: string; trend: TrendPresentation; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabelText}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={[styles.trend, trendToneStyle(trend.tone)]}>{trend.text}</Text>
    </View>
  );
}

function trendToneStyle(tone: TrendPresentation['tone']) {
  if (tone === 'positive') return styles.trendPositive;
  if (tone === 'negative') return styles.trendNegative;
  return styles.trendNeutral;
}

const styles = StyleSheet.create({
  sectionTitle: { color: '#697586', fontFamily: 'monospace', fontSize: 11, fontWeight: '800', letterSpacing: 1, marginBottom: 10 },
  card: { backgroundColor: '#FFFFFF', borderColor: '#DCE4E8', borderRadius: 14, borderWidth: 1, boxShadow: '0 1px 3px rgba(20,32,45,0.08)', marginBottom: 10, padding: 12 },
  stationName: { color: '#20252B', fontSize: 17, fontWeight: '600' },
  distance: { alignItems: 'center', flexDirection: 'row', gap: 4, marginTop: 5 },
  distanceText: { color: '#52616A', fontSize: 11 },
  metrics: { flexDirection: 'row', gap: 8, marginTop: 14 },
  metric: { alignItems: 'center', borderColor: '#BCE3FA', borderRadius: 10, borderWidth: 1, flex: 1, justifyContent: 'center', minHeight: 104, paddingHorizontal: 4, paddingVertical: 10 },
  metricLabelText: { color: '#53606F', fontSize: 12, textAlign: 'center' },
  metricValue: { color: '#172033', fontSize: 18, fontWeight: '800', marginTop: 10, textAlign: 'center' },
  trend: { fontSize: 11, fontWeight: '600', marginTop: 7, textAlign: 'center' },
  trendPositive: { color: '#059669' },
  trendNegative: { color: '#DC2626' },
  trendNeutral: { color: '#7B8796' },
  empty: { color: '#667386', paddingVertical: 34, textAlign: 'center' }
});
