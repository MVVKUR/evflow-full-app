import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { createRoutePlan, type GeocodingItem, type RoutePlanResponse } from '@evflow/shared';
import { DestinationSearchModal } from './DestinationSearchModal';
import { TripInputScreen } from './TripInputScreen';
import { TripSimulationScreen } from './TripSimulationScreen';
import { ActiveNavigationScreen } from './ActiveNavigationScreen';
import type { LocationState, PlanRouteViewMode } from './planRouteTypes';

type PlanRouteScreenProps = {
  topInset?: number;
  bottomOffset?: number;
};

export function PlanRouteScreen({ topInset = 0, bottomOffset = 0 }: PlanRouteScreenProps) {
  const [viewMode, setViewMode] = useState<PlanRouteViewMode>('input');

  const [origin, setOrigin] = useState<LocationState | null>(null);
  const [destination, setDestination] = useState<LocationState | null>(null);

  const [currentSocPct, setCurrentSocPct] = useState<number>(72);
  const [socInputText, setSocInputText] = useState<string>('72');

  const [isSimulating, setIsSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [simulationResult, setSimulationResult] = useState<RoutePlanResponse | null>(null);

  const [searchModalVisible, setSearchModalVisible] = useState(false);

  // Sync manual text input with numeric SoC value
  function handleSocTextChange(text: string) {
    setSocInputText(text);
    const cleaned = text.replace(/[^0-9.]/g, '');
    const num = parseFloat(cleaned);
    if (!isNaN(num) && num >= 0 && num <= 100) {
      setCurrentSocPct(num);
    }
  }

  // Sync quick select button with text input
  function handleQuickSelectSoc(val: number) {
    setCurrentSocPct(val);
    setSocInputText(String(val));
  }

  function handleSelectDestination(item: GeocodingItem) {
    setDestination({
      latitude: item.latitude,
      longitude: item.longitude,
      label: item.label,
    });
    setSearchModalVisible(false);

    // If selected destination is a station, set as waypoint or destination
    if (item.type === 'station' && item.station) {
      setDestination({
        latitude: item.station.latitude,
        longitude: item.station.longitude,
        label: item.station.name || item.label,
      });
    }
  }

  async function handleSimulateRoute(waypointStationId?: string) {
    if (!origin || !destination) return;

    setIsSimulating(true);
    setError(null);

    try {
      const res = await createRoutePlan({
        origin: {
          latitude: origin.latitude,
          longitude: origin.longitude,
          label: origin.label,
        },
        destination: {
          latitude: destination.latitude,
          longitude: destination.longitude,
          label: destination.label,
        },
        current_soc_pct: currentSocPct,
        minimum_arrival_soc_pct: 15.0,
        preferences: {
          route_type: 'fastest',
          maximum_detour_km: 15.0,
          prefer_fast_charging: true,
        },
        waypoint_station_id: waypointStationId,
      });

      setSimulationResult(res);
      setViewMode('simulation');
    } catch (err: any) {
      setError(err.message || 'Failed to simulate route');
    } finally {
      setIsSimulating(false);
    }
  }

  function handleAddStopToRoute(stationId: string) {
    handleSimulateRoute(stationId);
  }

  function handleEndNavigation() {
    // Clear trip-only temporary state and return to input state
    setSimulationResult(null);
    setError(null);
    setViewMode('input');
  }

  if (viewMode === 'active_navigation' && simulationResult) {
    return (
      <ActiveNavigationScreen
        result={simulationResult}
        bottomOffset={bottomOffset}
        destination={destination}
        destinationName={destination?.label || 'Destination'}
        topInset={topInset}
        onOverview={() => setViewMode('simulation')}
        onEndNavigation={handleEndNavigation}
      />
    );
  }

  return (
    <View style={[styles.shell, { paddingTop: topInset, paddingBottom: bottomOffset }]}>
      {viewMode === 'simulation' && simulationResult ? (
        <TripSimulationScreen
          result={simulationResult}
          origin={origin}
          destination={destination}
          originLabel={origin?.label.split('—')[0].trim() || 'Origin'}
          destinationLabel={destination?.label || 'Destination'}
          onEditTrip={() => setViewMode('input')}
          onStartNavigation={() => setViewMode('active_navigation')}
          onAddStopToRoute={handleAddStopToRoute}
        />
      ) : (
        <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
          <TripInputScreen
            origin={origin}
            destination={destination}
            currentSocPct={currentSocPct}
            socInputText={socInputText}
            onSetOrigin={setOrigin}
            onOpenDestinationSearch={() => setSearchModalVisible(true)}
            onChangeSocText={handleSocTextChange}
            onQuickSelectSoc={handleQuickSelectSoc}
            onSimulate={() => handleSimulateRoute()}
            isSimulating={isSimulating}
            error={error}
          />
        </ScrollView>
      )}

      <DestinationSearchModal
        visible={searchModalVisible}
        onClose={() => setSearchModalVisible(false)}
        onSelect={handleSelectDestination}
        originLat={origin?.latitude}
        originLon={origin?.longitude}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
  },
});
