import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useNavigate } from 'react-router';
import { fetchEvModels, getMe, reverseGeocode, type EVModelApiItem, type UserPublic } from '@evflow/shared';
import { getUserLocation } from '../utils/location';
import { BatteryLevelInput } from './BatteryLevelInput';
import type { LocationState } from './planRouteTypes';

type TripInputScreenProps = {
  origin: LocationState | null;
  destination: LocationState | null;
  currentSocPct: number;
  socInputText: string;
  onSetOrigin: (loc: LocationState) => void;
  onOpenDestinationSearch: () => void;
  onChangeSocText: (text: string) => void;
  onQuickSelectSoc: (val: number) => void;
  onSimulate: () => void;
  isSimulating: boolean;
  error?: string | null;
};

const defaultJakartaPusat: LocationState = {
  latitude: -6.2088,
  longitude: 106.8456,
  label: 'Current Location — Jl. Sudirman, Jakarta Pusat',
};

export function TripInputScreen({
  origin,
  destination,
  currentSocPct,
  socInputText,
  onSetOrigin,
  onOpenDestinationSearch,
  onChangeSocText,
  onQuickSelectSoc,
  onSimulate,
  isSimulating,
  error,
}: TripInputScreenProps) {
  const navigate = useNavigate();

  const [user, setUser] = useState<UserPublic | null>(null);
  const [selectedEvModel, setSelectedEvModel] = useState<EVModelApiItem | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);

  // Auto-fill origin from location helper & reverse geocode to location name
  useEffect(() => {
    let mounted = true;
    getUserLocation({ requestPermission: true }).then((res) => {
      if (!mounted) return;
      if (res.coordinates) {
        const { latitude, longitude } = res.coordinates;
        onSetOrigin({
          latitude,
          longitude,
          label: 'Current Location — Detecting location name...',
        });

        reverseGeocode(latitude, longitude).then((rev) => {
          if (!mounted) return;
          const locationName = rev.label || rev.city || 'Indonesia';
          onSetOrigin({
            latitude,
            longitude,
            label: `Current Location — ${locationName}`,
          });
        });
      } else if (!origin) {
        // Fallback manual default origin when location denied or unavailable
        onSetOrigin(defaultJakartaPusat);
      }
    });

    return () => {
      mounted = false;
    };
  }, []);



  // Load user profile & selected EV model specs
  useEffect(() => {
    let mounted = true;

    async function loadData() {
      try {
        const u = await getMe();
        if (!mounted) return;
        setUser(u);

        if (u.ev_model_id) {
          const res = await fetchEvModels({ limit: 300 });
          if (!mounted) return;
          const found = res.items.find((m) => m.id === u.ev_model_id);
          if (found) {
            setSelectedEvModel(found);
          }
        }
      } catch (e) {
        // Handle unauthenticated or network error
      } finally {
        if (mounted) setLoadingProfile(false);
      }
    }

    loadData();

    return () => {
      mounted = false;
    };
  }, []);

  // Calculate estimated range from selected EV model and current SoC
  const estimatedRangeKm = React.useMemo(() => {
    if (!selectedEvModel || !selectedEvModel.range_km) return null;
    return Math.round(selectedEvModel.range_km * (currentSocPct / 100.0) * 0.85);
  }, [selectedEvModel, currentSocPct]);

  const missingEvModel = !loadingProfile && (!user?.ev_model_id || !selectedEvModel);
  const canSimulate = Boolean(
    origin &&
      destination &&
      selectedEvModel &&
      currentSocPct >= 0 &&
      currentSocPct <= 100 &&
      !isSimulating
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Plan Route</Text>
        <Text style={styles.subtitle}>Simulate energy use for your trip</Text>
      </View>

      {/* Origin and Destination Card */}
      <View style={styles.routeCard}>
        <View style={styles.routeRow}>
          <View style={styles.iconCircleOrigin}>
            <View style={styles.innerDotGreen} />
          </View>
          <View style={styles.routeTextWrap}>
            <Text style={styles.fieldLabel}>FROM</Text>
            <Text style={styles.fieldValue} numberOfLines={1}>
              {origin ? origin.label : 'Detecting current location...'}
            </Text>
          </View>
        </View>

        <View style={styles.divider} />

        <Pressable style={styles.routeRow} onPress={onOpenDestinationSearch}>
          <View style={styles.iconCircleDest}>
            <Text style={styles.destPinSymbol}>📍</Text>
          </View>
          <View style={styles.routeTextWrap}>
            <Text style={styles.fieldLabel}>TO</Text>
            <Text
              style={[styles.fieldValue, !destination && styles.placeholderValue]}
              numberOfLines={1}
            >
              {destination ? destination.label : 'Where are you going?'}
            </Text>
          </View>
        </Pressable>
      </View>

      {/* Vehicle Profile Warning Banner if no EV model selected */}
      {missingEvModel ? (
        <View style={styles.warningBanner}>
          <Text style={styles.warningIcon}>⚠️</Text>
          <View style={styles.warningTextWrap}>
            <Text style={styles.warningTitle}>No EV Model Selected</Text>
            <Text style={styles.warningSub}>
              Select your vehicle model in Profile to calculate battery capacity & range.
            </Text>
            <Pressable
              style={styles.profileLinkButton}
              onPress={() => navigate('/ev-driver/profile')}
            >
              <Text style={styles.profileLinkText}>Select Vehicle Profile →</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {/* Battery Level Input Card */}
      <BatteryLevelInput
        value={currentSocPct}
        inputText={socInputText}
        onChangeText={onChangeSocText}
        onQuickSelect={onQuickSelectSoc}
        estimatedRangeKm={estimatedRangeKm}
      />

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorBoxText}>{error}</Text>
        </View>
      ) : null}

      {/* Simulate Route Action Button */}
      <Pressable
        style={[styles.simulateButton, !canSimulate && styles.simulateButtonDisabled]}
        onPress={onSimulate}
        disabled={!canSimulate}
      >
        {isSimulating ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text style={styles.simulateButtonText}>⚡ Simulate Route</Text>
        )}
      </Pressable>

      <View style={styles.encryptionNoteRow}>
        <Text style={styles.lockIcon}>🔒</Text>
        <Text style={styles.encryptionNoteText}>
          Your route & battery data are encrypted for this trip only
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 24,
  },
  header: {
    marginBottom: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: '#0F172A',
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 15,
    color: '#64748B',
    marginTop: 4,
  },
  routeCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  routeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
  },
  iconCircleOrigin: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: '#00696F',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  innerDotGreen: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#00696F',
  },
  iconCircleDest: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  destPinSymbol: {
    fontSize: 18,
  },
  routeTextWrap: {
    flex: 1,
  },
  fieldLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.8,
  },
  fieldValue: {
    fontSize: 15,
    fontWeight: '600',
    color: '#0F172A',
    marginTop: 2,
  },
  placeholderValue: {
    color: '#94A3B8',
  },
  divider: {
    height: 1,
    backgroundColor: '#F1F5F9',
    marginVertical: 4,
  },
  warningBanner: {
    flexDirection: 'row',
    backgroundColor: '#FFFBEB',
    borderWidth: 1,
    borderColor: '#FCD34D',
    borderRadius: 14,
    padding: 14,
    marginBottom: 16,
  },
  warningIcon: {
    fontSize: 20,
    marginRight: 12,
  },
  warningTextWrap: {
    flex: 1,
  },
  warningTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#B45309',
  },
  warningSub: {
    fontSize: 13,
    color: '#92400E',
    marginTop: 2,
  },
  profileLinkButton: {
    marginTop: 8,
  },
  profileLinkText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#D97706',
  },
  errorBox: {
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorBoxText: {
    fontSize: 13,
    color: '#DC2626',
    fontWeight: '600',
  },
  simulateButton: {
    backgroundColor: '#00696F',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#00696F',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 4,
    marginBottom: 12,
  },
  simulateButtonDisabled: {
    backgroundColor: '#94A3B8',
    shadowOpacity: 0,
    elevation: 0,
  },
  simulateButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  encryptionNoteRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  lockIcon: {
    fontSize: 12,
    marginRight: 6,
  },
  encryptionNoteText: {
    fontSize: 12,
    color: '#64748B',
  },
});
