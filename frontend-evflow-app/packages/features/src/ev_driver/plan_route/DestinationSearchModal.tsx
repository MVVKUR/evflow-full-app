import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Modal, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { RouteApiError, searchGeocoding, type GeocodingItem } from '@evflow/shared';
import { formatDistance } from './planRouteUtils';
import { routeColors, routeRadius, routeSpacing } from './routeTheme';
import { LatestRequestGate } from './requestLifecycle';

export type LocationSearchMode = 'destination' | 'origin';
export const supportedSuggestionTerms = ['Jakarta', 'Bogor', 'Bandung'];

type Props = {
  visible: boolean;
  mode?: LocationSearchMode;
  onClose: () => void;
  onSelect: (item: GeocodingItem) => void;
  onNetworkError?: () => void;
  onConnectionRestored?: () => void;
  originLat?: number;
  originLon?: number;
};

export function DestinationSearchModal({ visible, mode = 'destination', onClose, onSelect, onNetworkError, onConnectionRestored, originLat, originLon }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GeocodingItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  return <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
    <View style={styles.backdrop}>
      <View style={styles.panel} accessibilityViewIsModal>
        <View style={styles.searchRow}>
          <Pressable accessibilityLabel="Close location search" accessibilityRole="button" style={styles.iconButton} onPress={onClose}><Text style={styles.back}>←</Text></Pressable>
          <TextInput accessibilityLabel={mode === 'origin' ? 'Search origin' : 'Search destination'} autoFocus value={query} onChangeText={changeQuery} placeholder={mode === 'origin' ? 'Search starting location' : 'Where are you going?'} placeholderTextColor={routeColors.textSecondary} style={styles.input} returnKeyType="search" onSubmitEditing={() => void runSearch(query)} />
          <Pressable accessibilityLabel="Clear search" accessibilityRole="button" style={styles.iconButton} onPress={() => changeQuery('')}><Text style={styles.close}>×</Text></Pressable>
        </View>
        {!query.trim() ? <><View style={styles.current}><View style={styles.dot} /><Text style={styles.currentText}>{mode === 'origin' ? 'Choose a manual starting point' : 'From current location'}</Text></View><Text style={styles.sectionLabel}>Suggested destinations</Text></> : null}
        {loading ? <View style={styles.center}><ActivityIndicator color={routeColors.brand} /><Text style={styles.helper}>Searching locations and charging stations…</Text></View>
          : error ? <View style={styles.center}><Text style={styles.error}>{error}</Text><Pressable accessibilityRole="button" style={styles.retry} onPress={() => void runSearch(query)}><Text style={styles.retryText}>Retry search</Text></Pressable></View>
          : <FlatList keyboardShouldPersistTaps="handled" data={results} keyExtractor={(item) => item.id} contentContainerStyle={styles.list} ListEmptyComponent={<View style={styles.center}><Text style={styles.helper}>No supported locations found.</Text></View>} renderItem={({ item }) => <Pressable accessibilityRole="button" accessibilityLabel={`${item.label}, ${item.subtitle}`} style={styles.item} onPress={() => onSelect(item)}>
              <View style={[styles.itemDot, item.type === 'station' && styles.stationDot]} />
              <View style={styles.itemCopy}><Text style={styles.itemTitle} numberOfLines={1}>{item.label}</Text><Text style={styles.itemSubtitle} numberOfLines={1}>{item.subtitle}</Text></View>
              {item.distance_km != null ? <Text style={styles.distance}>{formatDistance(item.distance_km)}</Text> : null}
            </Pressable>} />}
        <Text style={styles.footnote}>Only destinations inside the configured route service area can be simulated.</Text>
      </View>
    </View>
  </Modal>;
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(19,37,39,0.25)', paddingTop: 32, paddingHorizontal: 12 },
  panel: { flex: 1, backgroundColor: routeColors.surface, borderTopLeftRadius: routeRadius.lg, borderTopRightRadius: routeRadius.lg, padding: routeSpacing.lg },
  searchRow: { minHeight: 56, borderRadius: routeRadius.md, backgroundColor: routeColors.surfaceSecondary, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 6 },
  iconButton: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' }, back: { fontSize: 24, color: routeColors.textPrimary }, close: { fontSize: 22, color: routeColors.textSecondary },
  input: { flex: 1, minHeight: 48, color: routeColors.textPrimary, fontSize: 15 },
  current: { minHeight: 44, marginTop: routeSpacing.md, paddingHorizontal: routeSpacing.md, borderRadius: routeRadius.sm, backgroundColor: routeColors.brandSoft, flexDirection: 'row', alignItems: 'center', gap: routeSpacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: routeColors.brand }, currentText: { color: routeColors.brandDark, fontWeight: '700', fontSize: 12 },
  sectionLabel: { marginTop: routeSpacing.md, color: routeColors.textSecondary, fontWeight: '700', textTransform: 'uppercase', fontSize: 10 },
  list: { gap: routeSpacing.md, paddingTop: routeSpacing.sm, paddingBottom: routeSpacing.lg },
  item: { minHeight: 66, borderWidth: 1, borderColor: routeColors.border, borderRadius: routeRadius.md, padding: routeSpacing.md, flexDirection: 'row', alignItems: 'center', gap: routeSpacing.md },
  itemDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: '#8BC6CA' }, stationDot: { backgroundColor: routeColors.brand }, itemCopy: { flex: 1 },
  itemTitle: { color: routeColors.textPrimary, fontWeight: '700', fontSize: 13 }, itemSubtitle: { color: routeColors.textSecondary, fontSize: 10, marginTop: 2 }, distance: { color: routeColors.brand, fontWeight: '800', fontSize: 12 },
  center: { minHeight: 180, alignItems: 'center', justifyContent: 'center', padding: routeSpacing.xl, gap: routeSpacing.md }, helper: { color: routeColors.textSecondary, textAlign: 'center' }, error: { color: routeColors.error, textAlign: 'center' },
  retry: { minHeight: 44, paddingHorizontal: routeSpacing.lg, borderRadius: routeRadius.md, borderWidth: 1, borderColor: routeColors.brand, justifyContent: 'center' }, retryText: { color: routeColors.brand, fontWeight: '800' },
  footnote: { color: routeColors.textSecondary, fontSize: 10, paddingBottom: routeSpacing.sm },
});
