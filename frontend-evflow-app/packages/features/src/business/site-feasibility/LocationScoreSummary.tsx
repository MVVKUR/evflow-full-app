import { StyleSheet, Text, View } from 'react-native';
import { BookmarkButton } from '../BookmarkButton';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import { buildingIcon, energyIcon, fireIcon } from './siteFeasibilityIcons';
import { getHeatmapSummary, getLocationPriority, getOverlapSummary, getPoiSummary } from './siteFeasibilityLogic';
import type { SiteFeasibilityScores } from './siteFeasibilityTypes';

export function LocationScoreSummary({ embedded = false, isSaved, isSaving, onToggleSaved, scores }: {
  embedded?: boolean;
  isSaved?: boolean;
  isSaving?: boolean;
  onToggleSaved?: () => void;
  scores: SiteFeasibilityScores;
}) {
  const rows = [
    { icon: fireIcon, text: getHeatmapSummary(scores.heatmap) },
    { icon: buildingIcon, text: getPoiSummary(scores.poi) },
    { icon: energyIcon, text: getOverlapSummary(scores.overlap) }
  ];

  return (
    <View style={[styles.card, embedded && styles.cardEmbedded]}>
      {onToggleSaved ? <View style={styles.bookmark}><BookmarkButton disabled={isSaving} isSaved={Boolean(isSaved)} onPress={onToggleSaved} /></View> : null}
      <View accessibilityLabel={`Location score ${scores.location} out of 100`} style={styles.scoreCircle}>
        <Text style={styles.score}>{scores.location}</Text>
        <Text style={styles.outOf}>/100</Text>
      </View>
      <View style={styles.copy}>
        <Text style={styles.eyebrow}>LOCATION SCORE</Text>
        <Text style={styles.priority}>{getLocationPriority(scores.location)}</Text>
        {rows.map((row) => (
          <View key={row.text} style={styles.row}>
            <SvgAssetIcon height={13} svg={row.icon} width={13} />
            <Text style={styles.rowText}>{row.text}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { alignItems: 'center', backgroundColor: '#F8FAFC', borderColor: '#DCE5EA', borderRadius: 16, borderWidth: 1, flexDirection: 'row', minHeight: 164, padding: 20, position: 'relative' },
  cardEmbedded: { backgroundColor: 'transparent', borderRadius: 0, borderWidth: 0, minHeight: 142, paddingBottom: 6, paddingHorizontal: 4, paddingTop: 6 },
  bookmark: { position: 'absolute', right: 16, top: 16, zIndex: 2 },
  scoreCircle: { alignItems: 'center', borderColor: '#0BA4E0', borderRadius: 42, borderWidth: 6, height: 84, justifyContent: 'center', marginHorizontal: 8, width: 84 },
  score: { color: '#2563EB', fontSize: 26, fontWeight: '800', lineHeight: 28 },
  outOf: { color: '#64748B', fontSize: 9 },
  copy: { flex: 1, marginLeft: 20, paddingRight: 32 },
  eyebrow: { color: '#64748B', fontSize: 10, fontWeight: '800', letterSpacing: 0.7 },
  priority: { color: '#172033', fontSize: 15, fontWeight: '800', marginBottom: 9, marginTop: 2 },
  row: { alignItems: 'center', flexDirection: 'row', gap: 5, marginBottom: 7 },
  rowText: { color: '#55637A', flex: 1, fontSize: 11 }
});
