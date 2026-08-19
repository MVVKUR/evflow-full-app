import { StyleSheet, Text, View } from 'react-native';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import { locationIcon, sessionsIcon } from './siteFeasibilityIcons';
import { getNearbyStationsWithinRadius, sortStationsByDistance } from './siteFeasibilityLogic';
import type { NearbyStationBenchmark } from './siteFeasibilityTypes';

export function NearbyStationsTab({ basis, stations }: { basis?: string; stations: NearbyStationBenchmark[] }) {
  const nearby = sortStationsByDistance(getNearbyStationsWithinRadius(stations));
  return (
    <View>
      <Text style={styles.sectionTitle}>NEARBY SPKLU BENCHMARK</Text>
      <Text style={styles.helper}>{basis
        ? 'Compare this proposed site with operating SPKLUs within 5 km.'
        : 'Compare this proposed site against historical utilization of operating SPKLUs within 5 km.'}</Text>
      {basis ? <Text style={styles.basis}>{basis}</Text> : null}
      {nearby.length ? nearby.map((station) => <StationCard key={station.id} station={station} />) : <Text style={styles.empty}>No existing SPKLUs within 5 km.</Text>}
    </View>
  );
}

function StationCard({ station }: { station: NearbyStationBenchmark }) {
  const metrics = [
    { label: 'Daily', value: station.averageDailySessions },
    { label: 'Weekly', value: station.averageWeeklySessions },
    { label: 'Monthly', value: station.averageMonthlySessions }
  ];
  return (
    <View style={styles.card}>
      <Text style={styles.stationName}>{station.name}</Text>
      <View style={styles.distance}><SvgAssetIcon height={14} svg={locationIcon} width={14} /><Text style={styles.distanceText}>{station.distanceKm.toFixed(1)} km away</Text></View>
      {station.totalConnectors !== undefined ? (
        <Text style={styles.availability}>{station.availableConnectors ?? 0} of {station.totalConnectors} connectors available</Text>
      ) : null}
      <View style={styles.metrics}>
        {metrics.map((metric) => (
          <View key={metric.label} style={styles.metric}>
            <View style={styles.metricLabel}><SvgAssetIcon height={13} svg={sessionsIcon} width={13} /><Text style={styles.metricLabelText}>{metric.label}</Text></View>
            <Text style={styles.metricValue}>{metric.value}</Text>
            <Text style={styles.sessions}>sessions</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sectionTitle: { color: '#697586', fontFamily: 'monospace', fontSize: 11, fontWeight: '800', letterSpacing: 1 },
  helper: { color: '#667386', fontSize: 11, lineHeight: 16, marginBottom: 12, marginTop: 5 },
  basis: { backgroundColor: '#F3F8FA', borderRadius: 8, color: '#53617A', fontSize: 10, lineHeight: 14, marginBottom: 12, padding: 8 },
  card: { backgroundColor: '#FFFFFF', borderColor: '#DCE4E8', borderRadius: 14, borderWidth: 1, boxShadow: '0 1px 3px rgba(20,32,45,0.08)', marginBottom: 10, padding: 12 },
  stationName: { color: '#20252B', fontSize: 17, fontWeight: '600' },
  distance: { alignItems: 'center', flexDirection: 'row', gap: 4, marginTop: 5 },
  distanceText: { color: '#52616A', fontSize: 11 },
  availability: { color: '#007D6B', fontSize: 10, fontWeight: '700', marginTop: 5 },
  metrics: { flexDirection: 'row', gap: 7, marginTop: 14 },
  metric: { alignItems: 'center', borderColor: '#BCE3FA', borderRadius: 10, borderWidth: 1, flex: 1, paddingHorizontal: 3, paddingVertical: 9 },
  metricLabel: { alignItems: 'center', flexDirection: 'row', gap: 3 },
  metricLabelText: { color: '#66717E', fontSize: 10 },
  metricValue: { color: '#172033', fontSize: 17, fontWeight: '800', marginTop: 5 },
  sessions: { color: '#7B8796', fontSize: 9 },
  empty: { color: '#667386', paddingVertical: 34, textAlign: 'center' }
});
