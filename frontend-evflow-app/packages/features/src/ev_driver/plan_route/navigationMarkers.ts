import type { LeafletMapMarker } from '@evflow/ui';
import type { RoutePlanResponse } from '@evflow/shared';

type Destination = { latitude: number; longitude: number };

/**
 * Markers to draw while navigating.
 *
 * The charging stop used to be dropped here: the map was handed a hardcoded
 * one-element array holding only the destination, so a driver following a route
 * that was planned around an SPKLU could not see where that stop was. The pin
 * exists in both map implementations and the plan-route screen already draws it;
 * only this screen omitted it.
 *
 * A driver-forced waypoint wins over the recommended stop, matching how
 * PlanRouteScreen picks which one to show, so the two screens never disagree.
 */
export function buildNavigationMarkers(
  routeResult: RoutePlanResponse,
  destination: Destination,
  destinationName: string
): LeafletMapMarker[] {
  const markers: LeafletMapMarker[] = [{
    id: 'destination',
    label: destinationName,
    latitude: destination.latitude,
    longitude: destination.longitude,
    type: 'destination'
  }];

  const stop = routeResult.user_requested_stop ?? routeResult.recommended_stop;
  if (stop) {
    markers.push({
      id: stop.station.id,
      label: stop.station.name ?? 'Charging stop',
      latitude: stop.station.latitude,
      longitude: stop.station.longitude,
      type: 'charging_stop'
    });
  }

  return markers;
}
