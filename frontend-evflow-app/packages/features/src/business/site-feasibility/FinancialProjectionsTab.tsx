import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import { energyIcon, paybackIcon, revenueIcon, sessionsIcon } from './siteFeasibilityIcons';
import { formatRevenueIdr } from './siteFeasibilityLogic';
import { getPaybackProjectionCopy } from './siteFeasibilityFinancial';
import type { FinancialProjection } from './siteFeasibilityTypes';

export function FinancialProjectionsTab({ error, financial, loading, onRetry }: {
  error: string | null;
  financial: FinancialProjection | null;
  loading: boolean;
  onRetry: () => void;
}) {
  if (loading) return <FinancialLoadingState />;
  if (error) {
    return (
      <View>
        <Text style={styles.sectionTitle}>PROJECTION SUMMARY</Text>
        <View accessibilityLiveRegion="polite" style={styles.errorCard}>
          <Text style={styles.errorText}>{error}</Text>
          <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retryButton}>
            <Text style={styles.retryText}>Retry projection</Text>
          </Pressable>
        </View>
      </View>
    );
  }
  if (!financial) return null;

  const isMock = financial.projectionKind === 'mock';
  const payback = getPaybackProjectionCopy(financial);
  const utilisation = financial.utilisation === undefined
    ? 'Mock utilization estimate'
    : `${Math.round(financial.utilisation * 100)}% utilisation of ${formatSessions(financial.capacitySessionsPerDay ?? 0)} capacity`;
  const metrics = [
    { title: 'Sessions/day', value: formatSessions(financial.sessionsPerDay), supporting: utilisation, icon: sessionsIcon },
    { title: 'Energy/day', value: `${formatSessions(financial.energyPerDayKwh)} kWh`, supporting: isMock ? 'Mock daily energy estimate' : 'From backend projection inputs', icon: energyIcon },
    { title: 'Monthly Revenue', value: formatRevenueIdr(financial.monthlyRevenueIdr), supporting: 'Gross top-line projection', icon: revenueIcon },
    { title: 'Payback Period', value: payback.value, supporting: payback.supporting, icon: paybackIcon }
  ];
  return (
    <View>
      <Text style={styles.sectionTitle}>PROJECTION SUMMARY</Text>
      <View style={styles.grid}>
        {metrics.map((metric) => (
          <View key={metric.title} style={styles.card}>
            <View style={styles.heading}><SvgAssetIcon height={17} svg={metric.icon} width={17} /><Text style={styles.title}>{metric.title}</Text></View>
            <Text style={styles.value}>{metric.value}</Text>
            <Text style={styles.supporting}>{metric.supporting}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function FinancialLoadingState() {
  return (
    <View accessibilityLiveRegion="polite">
      <Text style={styles.sectionTitle}>PROJECTION SUMMARY</Text>
      <View style={styles.loadingCard}>
        <ActivityIndicator color="#007D8C" />
        <Text style={styles.loadingText}>Calculating financial projection...</Text>
      </View>
    </View>
  );
}

function formatSessions(value: number) {
  return new Intl.NumberFormat('id-ID', { maximumFractionDigits: 1 }).format(value);
}

const styles = StyleSheet.create({
  sectionTitle: { color: '#697586', fontFamily: 'monospace', fontSize: 11, fontWeight: '800', letterSpacing: 1, marginBottom: 14 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  card: { alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#BCE3FA', borderRadius: 12, borderWidth: 1, justifyContent: 'center', minHeight: 134, padding: 12, width: '48.7%' },
  heading: { alignItems: 'center', alignSelf: 'stretch', flexDirection: 'row', gap: 6 },
  title: { color: '#53606F', fontSize: 12 },
  value: { color: '#172033', fontSize: 21, fontWeight: '800', marginVertical: 14, textAlign: 'center' },
  supporting: { color: '#53617C', fontFamily: 'monospace', fontSize: 10, letterSpacing: 0.7, lineHeight: 14, textAlign: 'center' },
  loadingCard: { alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#BCE3FA', borderRadius: 12, borderWidth: 1, gap: 10, justifyContent: 'center', minHeight: 160 },
  loadingText: { color: '#607077', fontSize: 12 },
  errorCard: { backgroundColor: '#FFF7ED', borderColor: '#F4C384', borderRadius: 12, borderWidth: 1, gap: 12, padding: 14 },
  errorText: { color: '#7A4410', fontSize: 12, lineHeight: 17 },
  retryButton: { alignItems: 'center', alignSelf: 'flex-start', borderColor: '#00696F', borderRadius: 8, borderWidth: 1, minHeight: 42, paddingHorizontal: 14 },
  retryText: { color: '#005F64', fontSize: 12, fontWeight: '800', lineHeight: 40 }
});
