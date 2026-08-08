import { StyleSheet, Text, View } from 'react-native';
import { routeColors, routeRadius, routeSpacing } from '../routeTheme';
import { MetricValueText } from './MetricValueText';

export function RouteMetricsGrid({ metrics }: { metrics: Array<{ label: string; value: string; tone?: 'success' | 'warning' }> }) {
  return <View style={styles.grid}>{metrics.map((metric) => <View key={metric.label} style={styles.metric}>
    <Text style={styles.label}>{metric.label}</Text>
    <MetricValueText value={metric.value}
      numberStyle={[styles.value, metric.tone === 'success' && styles.success, metric.tone === 'warning' && styles.warning]}
      unitStyle={[styles.unit, metric.tone === 'success' && styles.success, metric.tone === 'warning' && styles.warning]} />
  </View>)}</View>;
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: routeSpacing.sm },
  metric: { width: '48%', minHeight: 70, backgroundColor: routeColors.surfaceSecondary, borderRadius: routeRadius.md, padding: routeSpacing.md },
  label: { color: routeColors.textSecondary, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8 },
  value: { color: routeColors.textPrimary, fontSize: 22, fontWeight: '900', fontVariant: ['tabular-nums'], marginTop: 4 },
  unit: { color: routeColors.textSecondary, fontSize: 11, fontWeight: '700' },
  success: { color: routeColors.success }, warning: { color: routeColors.warning },
});
