import { StyleSheet, Text, View } from 'react-native';
import type { StationAvailability } from '../station-status/aggregateConnectorStatuses';

type StationAvailabilitySummaryProps = {
  availability: StationAvailability;
};

const colors = {
  available: { accent: '#10A957', background: '#EAF8F0', border: '#87D7A8', glyph: '✓', indicator: '#10A957', indicatorText: '#FFFFFF' },
  occupied: { accent: '#E87500', background: '#FFF7ED', border: '#F5BD82', glyph: '◷', indicator: '#FFE7CC', indicatorText: '#E87500' },
  out_of_service: { accent: '#667176', background: '#F3F5F5', border: '#C9D0D4', glyph: '!', indicator: '#E1E5E6', indicatorText: '#667176' },
  unknown: { accent: '#667176', background: '#F5F6F6', border: '#D4D9DC', glyph: '?', indicator: '#E5E8E9', indicatorText: '#667176' }
} as const;

export function StationAvailabilitySummary({ availability }: StationAvailabilitySummaryProps) {
  const palette = colors[availability.state];
  return (
    <View
      accessibilityLabel={`${availability.title}. ${availability.subtitle}`}
      accessible
      style={[summaryStyles.card, { backgroundColor: palette.background, borderColor: palette.border }]}
    >
      <View
        accessibilityLabel={`${availability.title} status indicator`}
        accessible
        style={[summaryStyles.indicator, { backgroundColor: palette.indicator }]}
      >
        <Text style={[summaryStyles.indicatorText, { color: palette.indicatorText }]}>{palette.glyph}</Text>
      </View>
      <View style={summaryStyles.copy}>
        <Text style={summaryStyles.title}>{availability.title}</Text>
        <Text style={summaryStyles.subtitle}>{availability.subtitle}</Text>
      </View>
    </View>
  );
}

const summaryStyles = StyleSheet.create({
  card: { alignItems: 'center', borderRadius: 14, borderWidth: 1, flexDirection: 'row', gap: 12, minHeight: 68, paddingHorizontal: 15, paddingVertical: 12 },
  indicator: { alignItems: 'center', borderRadius: 18, height: 36, justifyContent: 'center', width: 36 },
  indicatorText: { fontSize: 19, fontWeight: '900', lineHeight: 22 },
  copy: { flex: 1, gap: 3 },
  title: { color: '#20272A', fontSize: 15, fontWeight: '900', lineHeight: 19 },
  subtitle: { color: '#5E696E', fontSize: 11, lineHeight: 15 }
});
