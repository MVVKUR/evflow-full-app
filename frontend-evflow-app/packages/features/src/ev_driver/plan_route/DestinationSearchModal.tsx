import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { searchGeocoding, type GeocodingItem } from '@evflow/shared';
import { formatDistance } from './planRouteUtils';

type DestinationSearchModalProps = {
  visible: boolean;
  onClose: () => void;
  onSelect: (item: GeocodingItem) => void;
  originLat?: number;
  originLon?: number;
};

export function DestinationSearchModal({
  visible,
  onClose,
  onSelect,
  originLat,
  originLon,
}: DestinationSearchModalProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<GeocodingItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const timerRef = useRef<any>(null);
  const abortCtrlRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!visible) {
      setQuery('');
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }

    // Load initial default suggestions (e.g. Bandung, Bogor, Airport)
    handleSearch('');
  }, [visible]);

  function handleQueryChange(text: string) {
    setQuery(text);
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      handleSearch(text);
    }, 300);
  }

  async function handleSearch(q: string) {
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
    }
    abortCtrlRef.current = new AbortController();

    const searchTerm = q.trim() || 'Bandung';
    setLoading(true);
    setError(null);

    try {
      const res = await searchGeocoding(
        searchTerm,
        originLat,
        originLon,
        5,
        abortCtrlRef.current.signal
      );
      setResults(res.items);
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError(err.message || 'Failed to search places');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal visible={visible} animationType="slide" transparent={false} onRequestClose={onClose}>
      <View style={styles.container}>
        <View style={styles.header}>
          <Pressable style={styles.backButton} onPress={onClose}>
            <Text style={styles.backText}>✕</Text>
          </Pressable>
          <View style={styles.inputContainer}>
            <TextInput
              style={styles.searchInput}
              placeholder="Where are you going?"
              placeholderTextColor="#94A3B8"
              value={query}
              onChangeText={handleQueryChange}
              autoFocus
            />
            {query.length > 0 ? (
              <Pressable onPress={() => handleQueryChange('')}>
                <Text style={styles.clearText}>✕</Text>
              </Pressable>
            ) : null}
          </View>
        </View>

        {loading ? (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color="#00696F" />
            <Text style={styles.loadingText}>Searching locations & stations...</Text>
          </View>
        ) : error ? (
          <View style={styles.centerContainer}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : (
          <FlatList
            data={results}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.listContent}
            renderItem={({ item }) => (
              <Pressable style={styles.itemRow} onPress={() => onSelect(item)}>
                <View style={styles.itemIconCol}>
                  <View
                    style={[
                      styles.iconCircle,
                      item.type === 'station' ? styles.stationIconBg : styles.placeIconBg,
                    ]}
                  >
                    <Text style={styles.iconSymbol}>
                      {item.type === 'station' ? '⚡' : '📍'}
                    </Text>
                  </View>
                </View>

                <View style={styles.itemTextCol}>
                  <View style={styles.titleRow}>
                    <Text style={styles.itemTitle} numberOfLines={1}>
                      {item.label}
                    </Text>
                  </View>
                  <Text style={styles.itemSubtitle} numberOfLines={1}>
                    {item.subtitle}
                  </Text>
                </View>

                {item.distance_km != null ? (
                  <View style={styles.itemDistCol}>
                    <Text style={styles.distText}>{formatDistance(item.distance_km)}</Text>
                  </View>
                ) : null}
              </Pressable>
            )}
            ListEmptyComponent={
              <View style={styles.emptyContainer}>
                <Text style={styles.emptyText}>No locations or stations found</Text>
              </View>
            }
          />
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: 56,
    paddingBottom: 16,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  backButton: {
    padding: 8,
    marginRight: 8,
  },
  backText: {
    fontSize: 20,
    fontWeight: '600',
    color: '#334155',
  },
  inputContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F1F5F9',
    borderRadius: 12,
    paddingHorizontal: 12,
    height: 44,
  },
  searchInput: {
    flex: 1,
    fontSize: 15,
    color: '#0F172A',
    fontWeight: '500',
  },
  clearText: {
    fontSize: 14,
    color: '#94A3B8',
    padding: 4,
  },
  listContent: {
    paddingVertical: 8,
  },
  itemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: 16,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  itemIconCol: {
    marginRight: 14,
  },
  iconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeIconBg: {
    backgroundColor: '#E0F2FE',
  },
  stationIconBg: {
    backgroundColor: '#CCFBF1',
  },
  iconSymbol: {
    fontSize: 16,
  },
  itemTextCol: {
    flex: 1,
    marginRight: 8,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  itemTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#0F172A',
  },
  itemSubtitle: {
    fontSize: 13,
    color: '#64748B',
    marginTop: 2,
  },
  itemDistCol: {
    alignItems: 'flex-end',
  },
  distText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#00696F',
  },
  centerContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: '#64748B',
  },
  errorText: {
    fontSize: 14,
    color: '#EF4444',
    textAlign: 'center',
  },
  emptyContainer: {
    padding: 32,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 14,
    color: '#94A3B8',
  },
});
