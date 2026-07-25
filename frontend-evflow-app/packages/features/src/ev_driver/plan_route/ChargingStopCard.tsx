import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { RecommendedStop } from '@evflow/shared';

type ChargingStopCardProps = {
  stop: RecommendedStop;
  onAddStop: () => void;
  isAdded?: boolean;
};

export function ChargingStopCard({ stop, onAddStop, isAdded = false }: ChargingStopCardProps) {
  const station = stop.station;
  const connectorType = station.connector_types?.[0] || 'CCS2';
  const speedTier = station.speed_tier === 'ultra_fast' ? 'Ultra-Fast' : 'Fast';

  return (
    <View style={styles.card}>
      <Text style={styles.sectionHeader}>SUGGESTED CHARGING STOP</Text>

      <View style={styles.headerRow}>
        <Text style={styles.stationName} numberOfLines={1}>
          {station.name || 'SPKLU Rest Area KM72'}
        </Text>
        <View style={styles.distPill}>
          <Text style={styles.distPillText}>{Math.round(stop.distance_from_origin_km)} km in</Text>
        </View>
      </View>

      <Text style={styles.addressText} numberOfLines={1}>
        {station.address || station.city || 'Rest Area Tol Cipularang'}
      </Text>

      <View style={styles.specsRow}>
        <Text style={styles.specsText}>
          {connectorType} · {speedTier}
        </Text>
        <Text style={styles.dotSeparator}>·</Text>
        <Text style={styles.statusText}>
          {stop.availability === 'available_now' ? 'Available now' : 'Known status'}
        </Text>
      </View>

      <View style={styles.recChargeBox}>
        <Text style={styles.recLabel}>Recommended charge</Text>
        <Text style={styles.recVal}>
          To {stop.recommended_target_soc_pct}% (~{Math.round(stop.estimated_charging_minutes)} min)
        </Text>
      </View>

      {!isAdded ? (
        <Pressable style={styles.addButton} onPress={onAddStop}>
          <Text style={styles.addButtonText}>+ Add Stop to Route</Text>
        </Pressable>
      ) : (
        <View style={styles.addedBadge}>
          <Text style={styles.addedBadgeText}>✓ Stop Added to Route</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  sectionHeader: {
    fontSize: 11,
    fontWeight: '700',
    color: '#64748B',
    letterSpacing: 0.8,
    marginBottom: 12,
    textTransform: 'uppercase',
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  stationName: {
    flex: 1,
    fontSize: 17,
    fontWeight: '800',
    color: '#0F172A',
    marginRight: 8,
  },
  distPill: {
    backgroundColor: '#E0F2FE',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  distPillText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0369A1',
  },
  addressText: {
    fontSize: 13,
    color: '#64748B',
    marginBottom: 10,
  },
  specsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 14,
  },
  specsText: {
    fontSize: 13,
    color: '#475569',
    fontWeight: '600',
  },
  dotSeparator: {
    fontSize: 13,
    color: '#CBD5E1',
    marginHorizontal: 6,
  },
  statusText: {
    fontSize: 13,
    color: '#10B981',
    fontWeight: '600',
  },
  recChargeBox: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    padding: 12,
    borderRadius: 10,
    marginBottom: 14,
  },
  recLabel: {
    fontSize: 13,
    color: '#64748B',
  },
  recVal: {
    fontSize: 13,
    fontWeight: '700',
    color: '#00696F',
  },
  addButton: {
    borderWidth: 1.5,
    borderColor: '#00696F',
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#00696F',
  },
  addedBadge: {
    backgroundColor: '#ECFDF5',
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addedBadgeText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#047857',
  },
});
