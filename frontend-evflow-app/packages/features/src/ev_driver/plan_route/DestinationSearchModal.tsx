import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, BackHandler, FlatList, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { RouteApiError, reverseGeocode, searchGeocoding, type GeocodingItem } from '@evflow/shared';
import { formatDistance } from './planRouteUtils';
import { routeColors, routeRadius, routeShadow, routeSpacing } from './routeTheme';
import { LatestRequestGate } from './requestLifecycle';
import type { PickedMapPoint } from './planRouteTypes';

export type LocationSearchMode = 'destination' | 'origin';
export const supportedSuggestionTerms = ['Jakarta', 'Bogor', 'Bandung'];

function droppedPinLabel(point: PickedMapPoint): string {
  return `Dropped pin (${point.latitude.toFixed(4)}, ${point.longitude.toFixed(4)})`;
}

type Props = {
  visible: boolean;
  mode?: LocationSearchMode;
  onClose: () => void;
  onSelect: (item: GeocodingItem) => void;
  onNetworkError?: () => void;
  onConnectionRestored?: () => void;
  originLat?: number;
  originLon?: number;
  /** Point the user tagged on the parent map while this sheet is open. */
  pickedPoint?: PickedMapPoint | null;
  /** Keeps the sheet above surrounding chrome (e.g. tab bar), like the other route sheets. */
  bottomOffset?: number;
};

export function DestinationSearchModal({ visible, mode = 'destination', onClose, onSelect, onNetworkError, onConnectionRestored, originLat, originLon, pickedPoint = null, bottomOffset = 0 }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GeocodingItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickedLabel, setPickedLabel] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const gateRef = useRef(new LatestRequestGate());

  useEffect(() => {
    if (!visible) {
      timerRef.current && clearTimeout(timerRef.current);
      gateRef.current.cancel();
      setQuery(''); setResults([]); setError(null); setLoading(false);
      return;
    }
    void runSearch('');
    return () => { timerRef.current && clearTimeout(timerRef.current); gateRef.current.cancel(); };
  }, [visible]);

  // The sheet is no longer a native Modal, so Android's hardware back button is
  // wired up manually to keep the old onRequestClose behaviour.
  useEffect(() => {
    if (!visible || Platform.OS !== 'android') return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => { onClose(); return true; });
    return () => subscription.remove();
  }, [visible, onClose]);

  // Names the tagged point. While the lookup runs the row shows a placeholder;
  // on failure the label falls back to raw coordinates instead of surfacing an
  // error, so the point stays usable offline.
  useEffect(() => {
    setPickedLabel(null);
    if (!visible || pickedPoint == null) return;
    const point = { latitude: pickedPoint.latitude, longitude: pickedPoint.longitude };
    const controller = new AbortController();
    void reverseGeocode(point.latitude, point.longitude, controller.signal)
      .then((place) => { if (!controller.signal.aborted) setPickedLabel(place.label || place.city || droppedPinLabel(point)); })
      .catch((cause) => {
        if (controller.signal.aborted || (cause as { name?: string })?.name === 'AbortError') return;
        setPickedLabel(droppedPinLabel(point));
      });
    return () => controller.abort();
  }, [visible, pickedPoint?.latitude, pickedPoint?.longitude]);

  function changeQuery(text: string) {
    setQuery(text);
    setError(null);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => void runSearch(text), 350);
  }

  async function runSearch(raw: string) {
    const request = gateRef.current.begin();
    const sequence = request.sequence;
    setLoading(true); setError(null);
    try {
      const term = raw.trim();
      const responses = term.length >= 2
        ? [await searchGeocoding(term, originLat, originLon, 8, request.signal)]
        : await Promise.all(supportedSuggestionTerms.map((suggestion) => searchGeocoding(suggestion, originLat, originLon, 2, request.signal)));
      if (!gateRef.current.isCurrent(sequence)) return;
      const seen = new Set<string>();
      setResults(responses.flatMap((response) => response.items).filter((item) => !seen.has(item.id) && Boolean(seen.add(item.id))));
      onConnectionRestored?.();
    } catch (cause) {
      if ((cause as { name?: string })?.name === 'AbortError' || !gateRef.current.isCurrent(sequence)) return;
      const apiError = cause as RouteApiError;
      setError(apiError.message || 'Unable to search locations.');
      if (apiError.isNetworkError) onNetworkError?.();
    } finally {
      if (gateRef.current.isCurrent(sequence)) setLoading(false);
    }
  }

  // Commits the tagged point through the exact same path a suggestion tap
  // uses: a GeocodingItem handed to onSelect.
  function commitPickedPoint() {
    if (!pickedPoint) return;
    onSelect({
      id: `picked-point:${pickedPoint.latitude.toFixed(6)},${pickedPoint.longitude.toFixed(6)}`,
      label: pickedLabel ?? droppedPinLabel(pickedPoint),
      subtitle: `${pickedPoint.latitude.toFixed(4)}, ${pickedPoint.longitude.toFixed(4)}`,
      latitude: pickedPoint.latitude,
      longitude: pickedPoint.longitude,
      type: 'place',
      station: null,
      attribution: 'Dropped pin',
    });
  }

  if (!visible) return null;

  return <View style={[styles.sheet, { bottom: bottomOffset }]} accessibilityViewIsModal>
    <View style={styles.handle} />
    {pickedPoint ? <View style={styles.pickedRow}>
      <View style={styles.pickedDot} />
      <View style={styles.pickedCopy}>
        <Text style={styles.pickedTitle} numberOfLines={1}>{pickedLabel ?? 'Titik di peta…'}</Text>
        <Text style={styles.pickedCoords}>{pickedPoint.latitude.toFixed(4)}, {pickedPoint.longitude.toFixed(4)}</Text>
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel="Use this point" style={styles.useButton} onPress={commitPickedPoint}><Text style={styles.useButtonText}>Use this point</Text></Pressable>
    </View> : null}
    <View style={styles.searchRow}>
      <Pressable accessibilityLabel="Close location search" accessibilityRole="button" style={styles.iconButton} onPress={onClose}><Text style={styles.back}>←</Text></Pressable>
      <TextInput accessibilityLabel={mode === 'origin' ? 'Search origin' : 'Search destination'} value={query} onChangeText={changeQuery} placeholder={mode === 'origin' ? 'Search starting location' : 'Where are you going?'} placeholderTextColor={routeColors.textSecondary} style={styles.input} returnKeyType="search" onSubmitEditing={() => void runSearch(query)} />
      <Pressable accessibilityLabel="Clear search" accessibilityRole="button" style={styles.iconButton} onPress={() => changeQuery('')}><Text style={styles.close}>×</Text></Pressable>
    </View>
    {!query.trim() ? <><View style={styles.current}><View style={styles.dot} /><Text style={styles.currentText}>{mode === 'origin' ? 'Choose a manual starting point' : 'From current location'}</Text></View><Text style={styles.hint}>Tap the map to drop a pin, drag it to adjust.</Text><Text style={styles.sectionLabel}>Suggested destinations</Text></> : null}
    {loading ? <View style={styles.center}><ActivityIndicator color={routeColors.brand} /><Text style={styles.helper}>Searching locations and charging stations…</Text></View>
      : error ? <View style={styles.center}><Text style={styles.error}>{error}</Text><Pressable accessibilityRole="button" style={styles.retry} onPress={() => void runSearch(query)}><Text style={styles.retryText}>Retry search</Text></Pressable></View>
      : <FlatList style={styles.listBox} keyboardShouldPersistTaps="handled" data={results} keyExtractor={(item) => item.id} contentContainerStyle={styles.list} ListEmptyComponent={<View style={styles.center}><Text style={styles.helper}>No supported locations found.</Text></View>} renderItem={({ item }) => <Pressable accessibilityRole="button" accessibilityLabel={`${item.label}, ${item.subtitle}`} style={styles.item} onPress={() => onSelect(item)}>
          <View style={[styles.itemDot, item.type === 'station' && styles.stationDot]} />
          <View style={styles.itemCopy}><Text style={styles.itemTitle} numberOfLines={1}>{item.label}</Text><Text style={styles.itemSubtitle} numberOfLines={1}>{item.subtitle}</Text></View>
          {item.distance_km != null ? <Text style={styles.distance}>{formatDistance(item.distance_km)}</Text> : null}
        </Pressable>} />}
    <Text style={styles.footnote}>Only destinations inside the configured route service area can be simulated.</Text>
  </View>;
}

const styles = StyleSheet.create({
  sheet: { position: 'absolute', left: 0, right: 0, maxHeight: '55%', backgroundColor: routeColors.surface, borderTopLeftRadius: routeRadius.sheet, borderTopRightRadius: routeRadius.sheet, paddingHorizontal: routeSpacing.lg, paddingBottom: routeSpacing.sm, zIndex: 30, ...routeShadow },
  handle: { width: 38, height: 4, borderRadius: 2, backgroundColor: routeColors.handle, alignSelf: 'center', marginTop: routeSpacing.sm, marginBottom: routeSpacing.sm },
  pickedRow: { flexDirection: 'row', alignItems: 'center', gap: routeSpacing.sm, backgroundColor: routeColors.brandSoft, borderRadius: routeRadius.md, padding: routeSpacing.sm, marginBottom: routeSpacing.sm },
  pickedDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: routeColors.brandDark },
  pickedCopy: { flex: 1 }, pickedTitle: { color: routeColors.textPrimary, fontWeight: '800', fontSize: 12 }, pickedCoords: { color: routeColors.textSecondary, fontSize: 10, marginTop: 1, fontVariant: ['tabular-nums'] },
  useButton: { minHeight: 44, paddingHorizontal: routeSpacing.md, borderRadius: routeRadius.md, backgroundColor: routeColors.brand, alignItems: 'center', justifyContent: 'center' }, useButtonText: { color: routeColors.onBrand, fontWeight: '800', fontSize: 12 },
  searchRow: { minHeight: 56, borderRadius: routeRadius.md, backgroundColor: routeColors.surfaceSecondary, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 6 },
  iconButton: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' }, back: { fontSize: 24, color: routeColors.textPrimary }, close: { fontSize: 22, color: routeColors.textSecondary },
  input: { flex: 1, minHeight: 48, color: routeColors.textPrimary, fontSize: 15 },
  current: { minHeight: 44, marginTop: routeSpacing.md, paddingHorizontal: routeSpacing.md, borderRadius: routeRadius.sm, backgroundColor: routeColors.brandSoft, flexDirection: 'row', alignItems: 'center', gap: routeSpacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: routeColors.brand }, currentText: { color: routeColors.brandDark, fontWeight: '700', fontSize: 12 },
  hint: { marginTop: routeSpacing.xs, color: routeColors.textSecondary, fontSize: 10 },
  sectionLabel: { marginTop: routeSpacing.md, color: routeColors.textSecondary, fontWeight: '700', textTransform: 'uppercase', fontSize: 10 },
  listBox: { flexGrow: 0, flexShrink: 1, minHeight: 0 },
  list: { gap: routeSpacing.md, paddingTop: routeSpacing.sm, paddingBottom: routeSpacing.lg },
  item: { minHeight: 66, borderWidth: 1, borderColor: routeColors.border, borderRadius: routeRadius.md, padding: routeSpacing.md, flexDirection: 'row', alignItems: 'center', gap: routeSpacing.md },
  itemDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: '#8BC6CA' }, stationDot: { backgroundColor: routeColors.brand }, itemCopy: { flex: 1 },
  itemTitle: { color: routeColors.textPrimary, fontWeight: '700', fontSize: 13 }, itemSubtitle: { color: routeColors.textSecondary, fontSize: 10, marginTop: 2 }, distance: { color: routeColors.brand, fontWeight: '800', fontSize: 12 },
  center: { minHeight: 180, alignItems: 'center', justifyContent: 'center', padding: routeSpacing.xl, gap: routeSpacing.md }, helper: { color: routeColors.textSecondary, textAlign: 'center' }, error: { color: routeColors.error, textAlign: 'center' },
  retry: { minHeight: 44, paddingHorizontal: routeSpacing.lg, borderRadius: routeRadius.md, borderWidth: 1, borderColor: routeColors.brand, justifyContent: 'center' }, retryText: { color: routeColors.brand, fontWeight: '800' },
  footnote: { color: routeColors.textSecondary, fontSize: 10, paddingBottom: routeSpacing.sm, paddingTop: routeSpacing.xs },
});
