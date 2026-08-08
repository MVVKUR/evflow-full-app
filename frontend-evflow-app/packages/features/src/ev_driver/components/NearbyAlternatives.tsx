import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { getStationAvailabilityBand, stationBandColors } from '../station-area/stationAvailabilityBand';
import { ALTERNATIVES_RADIUS_KM, ALTERNATIVES_WAIT_THRESHOLD_MINUTES } from '../station-area/nearbyAlternatives';

/**
 * The slice of the map screen's Station this section needs. Structural on
 * purpose: the full Station type is local to DriverMapScreen, and the generic
 * hands the caller's own type back through `onSelect` unchanged.
 */
export type AlternativeStation = {
  id: string;
  name: string;
  distanceKm?: number;
  availableConnectors?: number | null;
  totalConnectors?: number | null;
};

type NearbyAlternativesProps<StationT extends AlternativeStation> = {
  alternatives: StationT[] | null;
  error: string | null;
  loading: boolean;
  onRetry: () => void;
  onSelect: (station: StationT) => void;
  /** Why the section is being shown, so the intro sentence matches the situation. */
  reason: 'full' | 'long_wait';
};

/**
 * Text colours for the free-count numbers, keyed by the same band as the row
 * dot. `stationBandColors.limited` (#F0B429) is a pin colour that does not
 * survive as small text on a white card, so those numbers use the app's amber
 * instead; an unknown band never has numbers to colour.
 */
const bandTextColors = {
  free: '#10A957',
  limited: '#E87500',
  full: '#D64545',
  unknown: '#687378'
} as const;

/**
 * AC 3.4.1: rendered on the SAME station-detail screen when the opened station
 * is fully occupied (or its wait estimate exceeds the threshold). Tapping an
 * entry switches the detail drawer to that station without leaving the map.
 */
export function NearbyAlternatives<StationT extends AlternativeStation>({ alternatives, error, loading, onRetry, onSelect, reason }: NearbyAlternativesProps<StationT>) {
  const intro = reason === 'full'
    ? `All connectors here are taken. Nearby stations within ${ALTERNATIVES_RADIUS_KM} km with a free connector:`
    : `The wait here is estimated over ${ALTERNATIVES_WAIT_THRESHOLD_MINUTES} minutes. Nearby stations within ${ALTERNATIVES_RADIUS_KM} km with a free connector:`;

  return (
    <View style={altStyles.section}>
      <Text style={altStyles.title}>Nearby Alternatives</Text>
      <View style={altStyles.card}>
        <Text style={altStyles.intro}>{intro}</Text>

        {loading ? (
          <View accessibilityLabel="Loading nearby alternatives" accessibilityLiveRegion="polite" style={altStyles.loadingRow}>
            <ActivityIndicator color="#00696F" />
            <Text style={altStyles.mutedText}>Checking nearby stations...</Text>
          </View>
        ) : null}

        {!loading && error ? (
          <View accessibilityLiveRegion="polite" style={altStyles.errorBox}>
            <Text style={altStyles.errorText}>{error}</Text>
            <Pressable accessibilityLabel="Retry loading nearby alternatives" accessibilityRole="button" onPress={onRetry} style={altStyles.retryButton}>
              <Text style={altStyles.retryText}>Retry</Text>
            </Pressable>
          </View>
        ) : null}

        {!loading && !error && alternatives && alternatives.length === 0 ? (
          <Text style={altStyles.mutedText}>
            No station with a free connector within {ALTERNATIVES_RADIUS_KM} km right now.
          </Text>
        ) : null}

        {!loading && !error && alternatives ? alternatives.map((station) => {
          const band = getStationAvailabilityBand(station.availableConnectors, station.totalConnectors);
          const hasCounts = typeof station.availableConnectors === 'number' && typeof station.totalConnectors === 'number';
          // Plain-string twins of the styled spans below, for the accessibility label.
          const plugsLine = hasCounts
            ? `${station.availableConnectors} of ${station.totalConnectors} connectors free`
            : 'Availability unknown';
          const distanceLine = typeof station.distanceKm === 'number' ? `${station.distanceKm.toFixed(1)} km from here` : null;
          return (
            <Pressable
              accessibilityLabel={`Open ${station.name}, ${distanceLine ?? 'distance unknown'}, ${plugsLine}`}
              accessibilityRole="button"
              key={station.id}
              onPress={() => onSelect(station)}
              style={altStyles.row}
            >
              <View style={[altStyles.bandDot, { backgroundColor: stationBandColors[band] }]} />
              <View style={altStyles.rowCopy}>
                <Text numberOfLines={1} style={altStyles.rowName}>{station.name}</Text>
                <Text numberOfLines={1} style={altStyles.rowMeta}>
                  {typeof station.distanceKm === 'number' ? (
                    <>
                      <Text style={altStyles.rowMetaNumber}>{station.distanceKm.toFixed(1)} km</Text>
                      {' from here · '}
                    </>
                  ) : null}
                  {hasCounts ? (
                    <>
                      <Text style={[altStyles.rowMetaNumber, { color: bandTextColors[band] }]}>{station.availableConnectors}</Text>
                      {' of '}
                      <Text style={[altStyles.rowMetaNumber, { color: bandTextColors[band] }]}>{station.totalConnectors}</Text>
                      {' connectors free'}
                    </>
                  ) : (
                    'Availability unknown'
                  )}
                </Text>
              </View>
              <Text style={altStyles.chevron}>›</Text>
            </Pressable>
          );
        }) : null}
      </View>
    </View>
  );
}

const altStyles = StyleSheet.create({
  section: { gap: 8, marginTop: 16 },
  title: { color: '#687378', fontSize: 10, fontWeight: '900', letterSpacing: 0.8, textTransform: 'uppercase' },
  card: { backgroundColor: '#FFFFFF', borderColor: '#E3E8E9', borderRadius: 14, borderWidth: 1, boxShadow: '0 4px 10px rgba(29, 46, 50, 0.08)', gap: 10, padding: 14 },
  intro: { color: '#465257', fontSize: 12, lineHeight: 17 },
  loadingRow: { alignItems: 'center', flexDirection: 'row', gap: 10, minHeight: 44 },
  mutedText: { color: '#687378', fontSize: 12, lineHeight: 17 },
  errorBox: { backgroundColor: '#FFF7ED', borderColor: '#F4C384', borderRadius: 10, borderWidth: 1, gap: 8, padding: 10 },
  errorText: { color: '#7A4410', fontSize: 12, lineHeight: 17 },
  retryButton: { alignItems: 'center', alignSelf: 'flex-start', borderColor: '#00696F', borderRadius: 8, borderWidth: 1, justifyContent: 'center', minHeight: 44, paddingHorizontal: 16 },
  retryText: { color: '#005F64', fontSize: 13, fontWeight: '900' },
  row: { alignItems: 'center', flexDirection: 'row', gap: 10, minHeight: 48 },
  bandDot: { borderColor: '#FFFFFF', borderRadius: 7, borderWidth: 2, elevation: 1, height: 14, width: 14 },
  rowCopy: { flex: 1, gap: 1 },
  rowName: { color: '#20272A', fontSize: 13, fontWeight: '700' },
  rowMeta: { color: '#687378', fontSize: 11.5 },
  rowMetaNumber: { color: '#20272A', fontSize: 13, fontVariant: ['tabular-nums'], fontWeight: '900' },
  chevron: { color: '#9AA7AB', fontSize: 18, fontWeight: '600' }
});
