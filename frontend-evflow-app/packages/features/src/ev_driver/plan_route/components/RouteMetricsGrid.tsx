import { StyleSheet, Text, View } from 'react-native';
import { routeColors, routeRadius, routeSpacing } from '../routeTheme';

export function RouteMetricsGrid({ metrics }: { metrics: Array<{ label: string; value: string; tone?: 'success' | 'warning' }> }) {
  return <View style={styles.grid}>{metrics.map((metric) => <View key={metric.label} style={styles.metric}><Text style={styles.label}>{metric.label}</Text><Text style={[styles.value, metric.tone === 'success' && styles.success, metric.tone === 'warning' && styles.warning]}>{metric.value}</Text></View>)}</View>;
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: routeSpacing.sm },
  metric: { width: '48%', minHeight: 62, backgroundColor: routeColors.surfaceSecondary, borderRadius: routeRadius.md, padding: routeSpacing.md },
  label: { color: routeColors.textSecondary, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' },
  value: { color: routeColors.textPrimary, fontSize: 17, fontWeight: '800', marginTop: 3 },
  success: { color: routeColors.success }, warning: { color: routeColors.warning },
});
