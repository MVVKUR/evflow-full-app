import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { LeafletMap, type LeafletMapMarker } from '@evflow/ui';
import type { RoutePlanResponse } from '@evflow/shared';
import { ChargingStopCard } from './ChargingStopCard';
import { formatDistance, formatDuration, formatEnergy, formatSoc } from './planRouteUtils';
import type { LocationState } from './planRouteTypes';

type TripSimulationScreenProps = {
  result: RoutePlanResponse;
  onEditTrip: () => void;
  onStartNavigation: () => void;
  onAddStopToRoute: (stationId: string) => void;
  origin?: LocationState | null;
  destination?: LocationState | null;
  originLabel?: string;
  destinationLabel?: string;
};

export function TripSimulationScreen({
  result,
  onEditTrip,
  onStartNavigation,
  onAddStopToRoute,
  origin,
  destination,
  originLabel = 'Jakarta Pusat',
  destinationLabel = 'Bandung',
}: TripSimulationScreenProps) {
  const [stopAdded, setStopAdded] = useState(false);

  const { summary, route, recommended_stop, directly_reachable } = result;

  // Convert GeoJSON LineString [lon, lat] coordinates to Leaflet [lat, lon]
  const polylineCoordinates: [number, number][] = React.useMemo(() => {
    if (!route?.geometry?.coordinates) return [];
    return route.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
  }, [route]);

  const mapCenter = React.useMemo(() => {
    if (polylineCoordinates.length > 0) {
      return {
        latitude: polylineCoordinates[Math.floor(polylineCoordinates.length / 2)][0],
        longitude: polylineCoordinates[Math.floor(polylineCoordinates.length / 2)][1],
      };
    }
    return { latitude: -6.2088, longitude: 106.8456 };
  }, [polylineCoordinates]);

  const mapMarkers = React.useMemo(() => {
    const markers: LeafletMapMarker[] = [];
    const routeStart = polylineCoordinates[0];
    const routeEnd = polylineCoordinates[polylineCoordinates.length - 1];
    const originPoint = origin
      ? [origin.latitude, origin.longitude]
      : routeStart;
    const destinationPoint = destination
      ? [destination.latitude, destination.longitude]
      : routeEnd;

    if (originPoint) {
      markers.push({
        id: 'origin',
        label: originLabel,
        latitude: originPoint[0],
        longitude: originPoint[1],
        type: 'origin',
      });
    }

    if (destinationPoint) {
      markers.push({
        id: 'destination',
        label: destinationLabel,
        latitude: destinationPoint[0],
        longitude: destinationPoint[1],
        type: 'destination',
      });
    }

    if (recommended_stop) {
      markers.push({
        id: recommended_stop.station.id,
        label: recommended_stop.station.name,
        latitude: recommended_stop.station.latitude,
        longitude: recommended_stop.station.longitude,
        type: 'charging_stop',
      });
    }

    return markers;
  }, [destination, destinationLabel, origin, originLabel, polylineCoordinates, recommended_stop]);

  function handleAddStop() {
    if (recommended_stop) {
      setStopAdded(true);
      onAddStopToRoute(recommended_stop.station.id);
    }
  }

  function handleStartNavPress() {
    if (recommended_stop && !stopAdded && !directly_reachable) {
      // Confirmation flow: Add recommended stop before starting navigation
      handleAddStop();
    }
    onStartNavigation();
  }

  const isWarning = !directly_reachable || (recommended_stop != null && !stopAdded);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.headerRow}>
        <View>
          <Text style={styles.title}>Trip Simulation</Text>
          <Text style={styles.routeSubtitle}>
            {originLabel} ➔ {destinationLabel}
          </Text>
        </View>
        <Pressable onPress={onEditTrip} style={styles.editButton}>
          <Text style={styles.editButtonText}>Edit Trip</Text>
        </Pressable>
      </View>

      {/* Map View */}
      <View style={styles.mapContainer}>
        <LeafletMap
          center={mapCenter}
          markers={mapMarkers}
          polylineCoordinates={polylineCoordinates}
          polylineColor={isWarning ? '#EAB308' : '#10B981'}
          autoFitBounds
        />
      </View>

      {/* Status Banner */}
      {isWarning ? (
        <View style={styles.warningCard}>
          <View style={styles.warningIconBg}>
            <Text style={styles.warningIconText}>⚡</Text>
          </View>
          <View style={styles.bannerTextWrap}>
            <Text style={styles.warningTitle}>Charging Stop Recommended</Text>
            <Text style={styles.warningSub}>
              Your battery won't safely cover the full distance. We found a stop along the way.
            </Text>
          </View>
        </View>
      ) : (
        <View style={styles.successCard}>
          <View style={styles.successIconBg}>
            <Text style={styles.successIconText}>🟢</Text>
          </View>
          <View style={styles.bannerTextWrap}>
            <Text style={styles.successTitle}>You'll Arrive Comfortably</Text>
            <Text style={styles.successSub}>
              Your battery covers the full distance — no charging stop needed.
            </Text>
          </View>
        </View>
      )}

      {/* 2x2 Metric Cards Grid */}
      <View style={styles.metricsGrid}>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>TOTAL DISTANCE</Text>
          <Text style={styles.metricVal}>{formatDistance(summary.distance_km)}</Text>
        </View>

        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>ENERGY USE</Text>
          <Text style={styles.metricVal}>{formatEnergy(summary.estimated_energy_kwh)}</Text>
        </View>

        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>ARRIVAL BATTERY</Text>
          <Text style={[styles.metricVal, isWarning ? styles.orangeText : styles.greenText]}>
            {formatSoc(summary.estimated_arrival_soc_pct)}
          </Text>
        </View>

        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>EST. DURATION</Text>
          <Text style={styles.metricVal}>{formatDuration(summary.duration_minutes)}</Text>
        </View>
      </View>

      {/* Suggested Charging Stop Card if applicable */}
      {recommended_stop ? (
        <ChargingStopCard
          stop={recommended_stop}
          onAddStop={handleAddStop}
          isAdded={stopAdded}
        />
      ) : null}

      {/* Start Navigation Action Button */}
      <Pressable style={styles.startNavButton} onPress={handleStartNavPress}>
        <Text style={styles.startNavButtonText}>Start Navigation</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: '800',
    color: '#0F172A',
  },
  routeSubtitle: {
    fontSize: 14,
    color: '#64748B',
    marginTop: 2,
    fontWeight: '500',
  },
  editButton: {
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  editButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#00696F',
  },
  mapContainer: {
    height: 200,
    borderRadius: 16,
    overflow: 'hidden',
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  warningCard: {
    flexDirection: 'row',
    backgroundColor: '#FFFBEB',
    borderWidth: 1,
    borderColor: '#FDE68A',
    borderRadius: 16,
    padding: 14,
    marginBottom: 16,
    alignItems: 'center',
  },
  warningIconBg: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#FEF3C7',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  warningIconText: {
    fontSize: 18,
  },
  successCard: {
    flexDirection: 'row',
    backgroundColor: '#ECFDF5',
    borderWidth: 1,
    borderColor: '#A7F3D0',
    borderRadius: 16,
    padding: 14,
    marginBottom: 16,
    alignItems: 'center',
  },
  successIconBg: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#D1FAE5',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  successIconText: {
    fontSize: 18,
  },
  bannerTextWrap: {
    flex: 1,
  },
  warningTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#92400E',
  },
  warningSub: {
    fontSize: 13,
    color: '#B45309',
    marginTop: 2,
  },
  successTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#065F46',
  },
  successSub: {
    fontSize: 13,
    color: '#047857',
    marginTop: 2,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 16,
  },
  metricCard: {
    width: '48%',
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  metricLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.8,
  },
  metricVal: {
    fontSize: 22,
    fontWeight: '800',
    color: '#0F172A',
    marginTop: 4,
  },
  orangeText: {
    color: '#D97706',
  },
  greenText: {
    color: '#10B981',
  },
  startNavButton: {
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
    marginTop: 8,
  },
  startNavButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});
