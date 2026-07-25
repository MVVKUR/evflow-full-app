import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { LeafletMap } from '@evflow/ui';
import type { RoutePlanResponse } from '@evflow/shared';
import { getUserLocation } from '../utils/location';
import { formatDistance, formatDuration, formatEta, formatSoc } from './planRouteUtils';

type ActiveNavigationScreenProps = {
  result: RoutePlanResponse;
  onOverview: () => void;
  onEndNavigation: () => void;
  destinationName?: string;
};

export function ActiveNavigationScreen({
  result,
  onOverview,
  onEndNavigation,
  destinationName = 'Bogor',
}: ActiveNavigationScreenProps) {
  const { summary, route } = result;

  const [currentPos, setCurrentPos] = useState<{ latitude: number; longitude: number } | null>(null);

  // Extract polyline coordinates
  const polylineCoordinates: [number, number][] = React.useMemo(() => {
    if (!route?.geometry?.coordinates) return [];
    return route.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
  }, [route]);

  // Extract top maneuver instruction from OSRM steps
  const currentStep = React.useMemo(() => {
    if (route?.steps && route.steps.length > 0) {
      const step = route.steps[0];
      return {
        instruction: step.instruction || 'Proceed along route',
        name: step.name || 'Tol Jagorawi',
        distanceText: step.distance_m ? `In ${Math.round(step.distance_m)} m` : 'In 400 m',
      };
    }
    return {
      instruction: 'Keep left onto Tol Jagorawi',
      name: 'Tol Jagorawi',
      distanceText: 'In 400 m',
    };
  }, [route]);

  // Track active GPS location
  useEffect(() => {
    let mounted = true;

    getUserLocation({ requestPermission: true }).then((res) => {
      if (mounted && res.coordinates) {
        setCurrentPos(res.coordinates);
      }
    });

    return () => {
      mounted = false;
    };
  }, []);

  const mapCenter = React.useMemo(() => {
    if (currentPos) return currentPos;
    if (polylineCoordinates.length > 0) {
      return {
        latitude: polylineCoordinates[0][0],
        longitude: polylineCoordinates[0][1],
      };
    }
    return { latitude: -6.2088, longitude: 106.8456 };
  }, [currentPos, polylineCoordinates]);

  return (
    <View style={styles.container}>
      {/* Map filling active navigation area */}
      <View style={styles.mapWrap}>
        <LeafletMap
          center={mapCenter}
          currentLocation={currentPos}
          showCurrentLocationPinpoint
          polylineCoordinates={polylineCoordinates}
          polylineColor="#00696F"
          autoFitBounds
        />
      </View>

      {/* Top Turn-by-Turn Maneuver Banner */}
      <View style={styles.topManeuverBanner}>
        <View style={styles.turnIconCircle}>
          <Text style={styles.turnArrow}>⬆</Text>
        </View>
        <View style={styles.maneuverTextWrap}>
          <Text style={styles.maneuverDistance}>{currentStep.distanceText}</Text>
          <Text style={styles.maneuverInstruction}>{currentStep.instruction}</Text>
        </View>
      </View>

      {/* Bottom Sheet */}
      <View style={styles.bottomSheet}>
        <View style={styles.dragHandle} />

        <View style={styles.statsRow}>
          <Text style={styles.durationBig}>{formatDuration(summary.duration_minutes)}</Text>
          <Text style={styles.distanceLeft}>{formatDistance(summary.distance_km)} left</Text>
          <View style={styles.socPill}>
            <Text style={styles.socPillText}>
              • {formatSoc(summary.estimated_arrival_soc_pct)} at arrival
            </Text>
          </View>
        </View>

        <Text style={styles.arrivingSub}>
          Arriving {formatEta(summary.duration_minutes)} · {destinationName} · via {currentStep.name}
        </Text>

        <View style={styles.actionsRow}>
          <Pressable style={styles.overviewButton} onPress={onOverview}>
            <Text style={styles.overviewButtonText}>Overview</Text>
          </Pressable>

          <Pressable style={styles.endNavButton} onPress={onEndNavigation}>
            <Text style={styles.endNavButtonText}>End Navigation</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0F172A',
  },
  mapWrap: {
    ...StyleSheet.absoluteFillObject,
  },
  topManeuverBanner: {
    position: 'absolute',
    top: 16,
    left: 16,
    right: 16,
    backgroundColor: '#00565F',
    borderRadius: 16,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 8,
  },
  turnIconCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  turnArrow: {
    fontSize: 22,
    color: '#FFFFFF',
    fontWeight: '800',
  },
  maneuverTextWrap: {
    flex: 1,
  },
  maneuverDistance: {
    fontSize: 12,
    fontWeight: '600',
    color: 'rgba(255, 255, 255, 0.8)',
  },
  maneuverInstruction: {
    fontSize: 16,
    fontWeight: '800',
    color: '#FFFFFF',
    marginTop: 2,
  },
  bottomSheet: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingTop: 10,
    paddingBottom: 28,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -6 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 10,
  },
  dragHandle: {
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#CBD5E1',
    alignSelf: 'center',
    marginBottom: 16,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  durationBig: {
    fontSize: 26,
    fontWeight: '800',
    color: '#0F172A',
  },
  distanceLeft: {
    fontSize: 14,
    fontWeight: '600',
    color: '#475569',
  },
  socPill: {
    backgroundColor: '#DCFCE7',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  socPillText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#166534',
  },
  arrivingSub: {
    fontSize: 13,
    color: '#64748B',
    marginBottom: 20,
  },
  actionsRow: {
    flexDirection: 'row',
    gap: 12,
  },
  overviewButton: {
    flex: 1,
    borderWidth: 1.5,
    borderColor: '#00696F',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  overviewButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#00696F',
  },
  endNavButton: {
    flex: 1,
    backgroundColor: '#DC2626',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  endNavButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});
