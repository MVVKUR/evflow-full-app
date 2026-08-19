import { StyleSheet, Text, View } from 'react-native';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import { energyIcon, paybackIcon, revenueIcon, sessionsIcon } from './siteFeasibilityIcons';
import { formatRevenueIdr, getPaybackStatus } from './siteFeasibilityLogic';
import type { FinancialProjection } from './siteFeasibilityTypes';

export function FinancialProjectionsTab({ basis, financial }: { basis?: string; financial: FinancialProjection }) {
  const metrics = [
    { title: 'Sessions/day', value: String(financial.sessionsPerDay), supporting: 'High utilization per port', icon: sessionsIcon },
    { title: 'Energy/day', value: `${financial.energyPerDayKwh} kWh`, supporting: 'Target grid utilization', icon: energyIcon },
    { title: 'Monthly Revenue', value: formatRevenueIdr(financial.monthlyRevenueIdr), supporting: 'Gross top-line projection', icon: revenueIcon },
    { title: 'Payback Period', value: `${financial.paybackYears.toFixed(1)} Yrs`, supporting: getPaybackStatus(financial.paybackYears), icon: paybackIcon }
  ];
  return (
    <View>
      <Text style={styles.sectionTitle}>PROJECTION SUMMARY</Text>
      {basis ? <Text style={styles.basis}>{basis}</Text> : null}
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

const styles = StyleSheet.create({
  sectionTitle: { color: '#697586', fontFamily: 'monospace', fontSize: 11, fontWeight: '800', letterSpacing: 1, marginBottom: 14 },
  basis: { color: '#667386', fontSize: 10, lineHeight: 14, marginBottom: 12, marginTop: -8 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  card: { alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#BCE3FA', borderRadius: 12, borderWidth: 1, justifyContent: 'center', minHeight: 134, padding: 12, width: '48.7%' },
  heading: { alignItems: 'center', alignSelf: 'stretch', flexDirection: 'row', gap: 6 },
  title: { color: '#53606F', fontSize: 12 },
  value: { color: '#172033', fontSize: 21, fontWeight: '800', marginVertical: 14, textAlign: 'center' },
  supporting: { color: '#53617C', fontFamily: 'monospace', fontSize: 10, letterSpacing: 0.7, lineHeight: 14, textAlign: 'center' }
});
