import { StyleSheet, Text, View } from 'react-native';
import type { StationAvailability } from '../station-status/aggregateConnectorStatuses';

type StationAvailabilitySummaryProps = {
  availability: StationAvailability;
};

const colors = {
  available: { accent: '#0B7A41', background: '#EAF8F0', border: '#87D7A8', glyph: '✓', indicator: '#10A957', indicatorText: '#FFFFFF' },
  occupied: { accent: '#C62828', background: '#FBEAEA', border: '#EFB4B4', glyph: '◷', indicator: '#F6D6D6', indicatorText: '#C62828' },
  out_of_service: { accent: '#667176', background: '#F3F5F5', border: '#C9D0D4', glyph: '!', indicator: '#E1E5E6', indicatorText: '#667176' },
  unknown: { accent: '#667176', background: '#F5F6F6', border: '#D4D9DC', glyph: '?', indicator: '#E5E8E9', indicatorText: '#667176' }
} as const;

export function StationAvailabilitySummary({ availability }: StationAvailabilitySummaryProps) {
  const palette = colors[availability.state];
  // "0/0 free", or a fraction built from statuses we never received, would be
  // a claim we cannot make — the hero figure only renders when the counts are real.
  const showHeroCount = availability.state !== 'unknown' && availability.totalCount > 0;
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
        <SummarySubtitle availability={availability} />
      </View>
      {showHeroCount ? (
        <View style={summaryStyles.hero}>
          <Text style={[summaryStyles.heroFigure, { color: palette.accent }]}>
            {availability.availableCount}/{availability.totalCount}
          </Text>
          <Text style={summaryStyles.heroLabel}>FREE</Text>
        </View>
      ) : null}
    </View>
  );
}

/**
 * The visible subtitle. The card's accessibility label keeps the full
 * `availability.subtitle` sentence untouched; visually the numbers are pulled
 * out of the sentence so they read at a glance:
 * - available: the count lives in the hero "N/M" figure, so only the words remain here;
 * - occupied with an estimate: the minutes become a bold amber span, units stay small.
 */
function SummarySubtitle({ availability }: StationAvailabilitySummaryProps) {
  if (availability.state === 'available' && availability.totalCount > 0) {
    return <Text style={summaryStyles.subtitle}>connectors available right now</Text>;
  }
  const estimate = availability.earliestEstimate;
  if (availability.state === 'occupied' && estimate) {
    return (
      <Text style={summaryStyles.subtitleLoose}>
        {'Est. '}
        <Text style={summaryStyles.subtitleNumber}>~{estimate.minutes}</Text>
        {` ${estimate.minutes === 1 ? 'min' : 'mins'} left`}
      </Text>
    );
  }
  return <Text style={summaryStyles.subtitle}>{availability.subtitle}</Text>;
}

const summaryStyles = StyleSheet.create({
  card: { alignItems: 'center', borderRadius: 14, borderWidth: 1, flexDirection: 'row', gap: 12, minHeight: 68, paddingHorizontal: 15, paddingVertical: 12 },
  indicator: { alignItems: 'center', borderRadius: 18, height: 36, justifyContent: 'center', width: 36 },
  indicatorText: { fontSize: 19, fontWeight: '900', lineHeight: 22 },
  copy: { flex: 1, gap: 3 },
  title: { color: '#20272A', fontSize: 15, fontWeight: '900', lineHeight: 19 },
  subtitle: { color: '#5E696E', fontSize: 11, lineHeight: 15 },
  // Same voice as `subtitle`, minus the tight lineHeight so the inline number span is not clipped.
  subtitleLoose: { color: '#5E696E', fontSize: 11 },
  subtitleNumber: { color: '#C62828', fontSize: 16, fontVariant: ['tabular-nums'], fontWeight: '900' },
  hero: { alignItems: 'center', paddingLeft: 2 },
  heroFigure: { fontSize: 22, fontVariant: ['tabular-nums'], fontWeight: '900', lineHeight: 26 },
  heroLabel: { color: '#687378', fontSize: 10, fontWeight: '900', letterSpacing: 0.8 }
});
