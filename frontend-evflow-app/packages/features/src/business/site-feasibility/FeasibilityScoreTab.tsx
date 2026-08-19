import { StyleSheet, Text, View } from 'react-native';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import { buildingIcon, carIcon, fireIcon, shieldIcon } from './siteFeasibilityIcons';
import { getActivityDescription, getHeatmapDescription, getOverlapDescription, getPoiDescription } from './siteFeasibilityLogic';
import type { SiteFeasibilityData, SiteFeasibilityScores } from './siteFeasibilityTypes';

type Metric = { title: string; score: number; description: string; icon: string };

export function FeasibilityScoreTab({ data, scores }: { data: SiteFeasibilityData; scores: SiteFeasibilityScores }) {
  const metrics: Metric[] = [
    { title: 'Heatmap Zone Score', score: scores.heatmap, description: getHeatmapDescription(scores.heatmap), icon: fireIcon },
    { title: 'POI Density Score', score: scores.poi, description: getPoiDescription(scores.poi, data.commercialPoiCount), icon: buildingIcon },
    { title: 'Network Overlap Score', score: scores.overlap, description: getOverlapDescription(scores.overlap, data.nearestSpkluDistanceKm), icon: shieldIcon },
    { title: 'Demand & Activity Score', score: scores.activity, description: getActivityDescription(data.roadType, data.residentialPoints), icon: carIcon }
  ];
  return (
    <View>
      <Text style={styles.sectionTitle}>FEASIBILITY BREAKDOWN</Text>
      {metrics.map((metric) => <MetricCard key={metric.title} metric={metric} />)}
    </View>
  );
}

function MetricCard({ metric }: { metric: Metric }) {
  const displayScore = Math.round(metric.score);
  return (
    <View style={styles.card}>
      <View style={styles.heading}>
        <View style={styles.titleWrap}><SvgAssetIcon height={18} svg={metric.icon} width={18} /><Text style={styles.title}>{metric.title}</Text></View>
        <Text style={styles.value}>{displayScore}<Text style={styles.outOf}>/100</Text></Text>
      </View>
      <View accessibilityLabel={`${metric.title} ${displayScore} out of 100`} style={styles.track}><View style={[styles.progress, { width: `${Math.min(displayScore, 100)}%` }]} /></View>
      <Text style={styles.description}>{metric.description}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  sectionTitle: { color: '#697586', fontFamily: 'monospace', fontSize: 11, fontWeight: '800', letterSpacing: 1, marginBottom: 12 },
  card: { backgroundColor: '#FFFFFF', borderColor: '#E0E6EA', borderRadius: 12, borderWidth: 1, boxShadow: '0 1px 3px rgba(20,32,45,0.08)', marginBottom: 12, padding: 14 },
  heading: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  titleWrap: { alignItems: 'center', flexDirection: 'row', gap: 8 },
  title: { color: '#172033', fontSize: 13, fontWeight: '800' },
  value: { color: '#172033', fontSize: 14, fontWeight: '800' },
  outOf: { color: '#8B96A6', fontSize: 10, fontWeight: '400' },
  track: { backgroundColor: '#EBEEF2', borderRadius: 4, height: 6, marginTop: 11, overflow: 'hidden' },
  progress: { backgroundColor: '#00789C', borderRadius: 4, height: 6 },
  description: { color: '#738094', fontSize: 11, marginTop: 9 }
});
