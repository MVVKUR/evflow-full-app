import { createElement, useEffect, useId, useRef, useState } from 'react';
import { escapeHtml } from '@evflow/shared';

type LeafletMapProps = {
  center?: {
    latitude: number;
    longitude: number;
  };
  currentLocation?: {
    latitude: number;
    longitude: number;
  } | null;
  markerIconSvg?: string;
  markers?: LeafletMapMarker[];
  onMapPress?: (latitude: number, longitude: number) => void;
  onMarkerPress?: (markerId: string) => void;
  onPickedPointMoved?: (latitude: number, longitude: number) => void;
  pickedPoint?: {
    latitude: number;
    longitude: number;
  } | null;
  polylineCoordinates?: [number, number][];
  polylineColor?: string;
  autoFitBounds?: boolean;
  radiusKm?: number | null;
  selectedMarkerIconSvg?: string;
  selectedMarkerId?: string | null;
  showCurrentLocationPinpoint?: boolean;
  zoom?: number;
};


export type LeafletMapMarker = {
  id: string;
  label?: string;
  latitude: number;
  longitude: number;
  type?: 'origin' | 'destination' | 'charging_stop' | 'station' | 'default';
  /** Pin fill for an ordinary station. Callers use it to signal live availability. */
  fillColor?: string;
  /** Per-marker artwork, overriding markerIconSvg. Lets one map mix availability variants. */
  iconSvg?: string;
  /** Per-marker artwork while selected, overriding selectedMarkerIconSvg. */
  selectedIconSvg?: string;
};

type LeafletNamespace = typeof import('leaflet');
type LeafletImport = LeafletNamespace & {
  default?: LeafletNamespace;
};

const defaultCenter = {
  latitude: -6.1754,
  longitude: 106.8272
};

// Distinctive droplet pin for the interactive point picker: teal fill with a
// white ring, kept subtly larger than the 32px station pins.
const pickerPinSvg =
  '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 3px 5px rgba(0,0,0,0.4));">' +
  '<path d="M12 2C8.13 2 5 5.13 5 9C5 14.25 12 22 12 22C12 22 19 14.25 19 9C19 5.13 15.87 2 12 2Z" fill="#00696F" stroke="#FFFFFF" stroke-width="1.5"/>' +
  '<circle cx="12" cy="9" r="3.2" fill="none" stroke="#FFFFFF" stroke-width="1.8"/>' +
  '</svg>';

export function LeafletMap({
  autoFitBounds,
  center = defaultCenter,
  currentLocation,
  markerIconSvg,
  markers = [],
  onMapPress,
  onMarkerPress,
  onPickedPointMoved,
  pickedPoint,
  polylineColor,
  polylineCoordinates,
  radiusKm,
  selectedMarkerIconSvg,
  selectedMarkerId = null,
  showCurrentLocationPinpoint = false,
  zoom = 13
}: LeafletMapProps) {
  const reactId = useId();
  const mapContainerId = `leaflet-map-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const mapRef = useRef<import('leaflet').Map | null>(null);
  const userMarkerRef = useRef<import('leaflet').CircleMarker | null>(null);
  const stationMarkersRef = useRef<import('leaflet').Layer[]>([]);
  const radiusCircleRef = useRef<import('leaflet').Circle | null>(null);
  const radiusKmRef = useRef<number | null>(radiusKm ?? null);
  const pickerMarkerRef = useRef<import('leaflet').Marker | null>(null);
  // Mirrors of the interaction callbacks: the map instance and the picker
  // marker outlive any single render, so their Leaflet handlers must read the
  // latest props through refs (same pattern as radiusKmRef below).
  const onMapPressRef = useRef<((latitude: number, longitude: number) => void) | null>(
    onMapPress ?? null
  );
  const onPickedPointMovedRef = useRef<((latitude: number, longitude: number) => void) | null>(
    onPickedPointMoved ?? null
  );
  const leafletRef = useRef<LeafletNamespace | null>(null);
  const pendingUserLocationRef = useRef<[number, number] | null>(null);
  const [failed, setFailed] = useState(false);
  // Bumped when the Leaflet map instance is (re)created so the markers effect
  // repaints with the freshest props instead of loadMap's stale closure.
  const [mapRevision, setMapRevision] = useState(0);
  const pickerDraggable = Boolean(onPickedPointMoved);

  function renderRadiusCircle() {
    if (!mapRef.current || !leafletRef.current) {
      return;
    }

    const center = pendingUserLocationRef.current;
    const km = radiusKmRef.current;

    if (!center || !km || km <= 0) {
      if (radiusCircleRef.current) {
        radiusCircleRef.current.remove();
        radiusCircleRef.current = null;
      }
      return;
    }

    const meters = km * 1000;

    if (!radiusCircleRef.current || !mapRef.current.hasLayer(radiusCircleRef.current)) {
      radiusCircleRef.current = leafletRef.current
        .circle(center, {
          color: '#00696F',
          dashArray: '6 6',
          fillColor: '#00C2CB',
          fillOpacity: 0.12,
          interactive: false,
          opacity: 0.8,
          radius: meters,
          weight: 2
        })
        .addTo(mapRef.current);
    } else {
      radiusCircleRef.current.setLatLng(center);
      radiusCircleRef.current.setRadius(meters);
    }
  }

  function renderUserLocation(coordinates: [number, number]) {
    pendingUserLocationRef.current = coordinates;

    if (!mapRef.current || !leafletRef.current) {
      return;
    }

    if (!userMarkerRef.current || !mapRef.current.hasLayer(userMarkerRef.current)) {
      userMarkerRef.current = leafletRef.current
        .circleMarker(coordinates, {
          bubblingMouseEvents: false,
          color: '#ffffff',
          fillColor: '#00E0EB',
          fillOpacity: 1,
          radius: 9,
          weight: 3
        })
        .addTo(mapRef.current)
        .bindPopup('Your current location');
    } else {
      userMarkerRef.current.setLatLng(coordinates);
    }

    renderRadiusCircle();
  }

  function renderStationMarkers(nextMarkers: LeafletMapMarker[]) {
    if (!mapRef.current || !leafletRef.current) {
      return;
    }

    stationMarkersRef.current.forEach((marker) => marker.remove());
    stationMarkersRef.current = nextMarkers.map((marker) => {
      const isSelected = selectedMarkerId != null && marker.id === selectedMarkerId;
      // Per-marker artwork wins over the map-wide default, so stations can carry
      // their own availability colour while everything else stays untouched.
      const iconSvg = isSelected
        ? marker.selectedIconSvg ?? selectedMarkerIconSvg ?? marker.iconSvg ?? markerIconSvg
        : marker.iconSvg ?? markerIconSvg;

      let markerIconHtml: string | undefined = iconSvg;
      let iconAnchor: [number, number] = isSelected ? [22, 22] : [16, 16];
      let iconSize: [number, number] = isSelected ? [44, 44] : [32, 32];
      let popupAnchor: [number, number] = isSelected ? [0, -26] : [0, -20];
      let zIndex = isSelected ? 1000 : 0;

      if (marker.type === 'origin' || marker.id === 'origin') {
        markerIconHtml = `<div style="width: 20px; height: 20px; background: #1A73E8; border: 3px solid #FFFFFF; border-radius: 50%; box-shadow: 0 2px 6px rgba(0,0,0,0.35);"></div>`;
        iconAnchor = [10, 10];
        iconSize = [20, 20];
        popupAnchor = [0, -12];
        zIndex = 800;
      } else if (marker.type === 'destination' || marker.id === 'destination') {
        markerIconHtml = `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 3px 5px rgba(0,0,0,0.4));"><path d="M12 2C8.13 2 5 5.13 5 9C5 14.25 12 22 12 22C12 22 19 14.25 19 9C19 5.13 15.87 2 12 2ZM12 11.5C10.62 11.5 9.5 10.38 9.5 9C9.5 7.62 10.62 6.5 12 6.5C13.38 6.5 14.5 7.62 14.5 9C14.5 10.38 13.38 11.5 12 11.5Z" fill="#DC2626"/><circle cx="12" cy="9" r="2.5" fill="#FFFFFF"/></svg>`;
        iconAnchor = [16, 32];
        iconSize = [32, 32];
        popupAnchor = [0, -32];
        zIndex = 900;
      } else if (marker.type === 'charging_stop') {
        markerIconHtml = `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 3px 5px rgba(0,0,0,0.4));"><path d="M12 2C8.13 2 5 5.13 5 9C5 14.25 12 22 12 22C12 22 19 14.25 19 9C19 5.13 15.87 2 12 2Z" fill="#F59E0B"/><path d="M13 7.5L9.5 11H12V14.5L15.5 11H13V7.5Z" fill="#FFFFFF"/></svg>`;
        iconAnchor = [16, 32];
        iconSize = [32, 32];
        popupAnchor = [0, -32];
        zIndex = 850;
      }

      const stationMarker = markerIconHtml
        ? leafletRef.current!
            .marker([marker.latitude, marker.longitude], {
              icon: leafletRef.current!.divIcon({
                className: isSelected
                  ? 'evflow-station-marker evflow-station-marker--selected'
                  : 'evflow-station-marker',
                html: markerIconHtml,
                iconAnchor,
                iconSize,
                popupAnchor
              }),
              zIndexOffset: zIndex
            })
            .addTo(mapRef.current!)
        : leafletRef.current!
            .circleMarker([marker.latitude, marker.longitude], {
              // Circle markers bubble clicks to the map by default; opt out so
              // tapping a station never doubles as a map press.
              bubblingMouseEvents: false,
              color: '#ffffff',
              // Selection still wins: the driver must be able to see which pin
              // they tapped, whatever its availability colour is.
              fillColor: isSelected ? '#00E0EB' : (marker.fillColor ?? '#007a80'),
              fillOpacity: 1,
              radius: isSelected ? 12 : 10,
              weight: 3
            })
            .addTo(mapRef.current!);

      if (marker.label) {
        // bindPopup renders HTML, so escape the station-provided label.
        stationMarker.bindPopup(escapeHtml(marker.label));
      }

      stationMarker.on('click', () => {
        onMarkerPress?.(marker.id);
      });

      return stationMarker;
    });
  }

  useEffect(() => {
    if (mapRef.current) {
      return;
    }

    let cancelled = false;
    let map: import('leaflet').Map | null = null;

    async function loadMap() {
      try {
        await import('leaflet/dist/leaflet.css');
        const leafletImport = (await import('leaflet')) as LeafletImport;
        const leaflet = leafletImport.default ?? leafletImport;
        leafletRef.current = leaflet;
        const mapContainer = document.getElementById(mapContainerId);

        if (!mapContainer || cancelled || mapRef.current) {
          return;
        }

        map = leaflet.map(mapContainerId, {
          attributionControl: true,
          center: [center.latitude, center.longitude],
          zoom,
          zoomControl: false
        });

        leaflet
          .tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution:
              '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            maxZoom: 19
          })
          .addTo(map);

        mapRef.current = map;

        map.on('click', (event: import('leaflet').LeafletMouseEvent) => {
          // Only plain map taps land here: L.Marker never bubbles mouse events
          // and the circle markers opt out via bubblingMouseEvents. Read the
          // callback through a ref because this closure survives re-renders.
          onMapPressRef.current?.(event.latlng.lat, event.latlng.lng);
        });

        if (pendingUserLocationRef.current) {
          renderUserLocation(pendingUserLocationRef.current);
        }
        setMapRevision((revision) => revision + 1);
        renderRadiusCircle();

        window.setTimeout(() => {
          map?.invalidateSize();
        }, 0);
      } catch {
        setFailed(true);
      }
    }

    loadMap();

    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
      userMarkerRef.current = null;
      stationMarkersRef.current = [];
      radiusCircleRef.current = null;
      pickerMarkerRef.current = null;
      polylineLayersRef.current = [];
    };
  }, [center.latitude, center.longitude, mapContainerId, zoom]);

  useEffect(() => {
    radiusKmRef.current = radiusKm ?? null;
    renderRadiusCircle();
  }, [radiusKm]);

  useEffect(() => {
    onMapPressRef.current = onMapPress ?? null;
  }, [onMapPress]);

  useEffect(() => {
    onPickedPointMovedRef.current = onPickedPointMoved ?? null;
  }, [onPickedPointMoved]);

  useEffect(() => {
    mapRef.current?.setView([center.latitude, center.longitude], zoom);
  }, [center.latitude, center.longitude, zoom]);

  const polylineLayersRef = useRef<import('leaflet').Layer[]>([]);

  useEffect(() => {
    renderStationMarkers(markers);

    return () => {
      stationMarkersRef.current.forEach((marker) => marker.remove());
      stationMarkersRef.current = [];
    };
  }, [mapRevision, markerIconSvg, markers, onMarkerPress, selectedMarkerIconSvg, selectedMarkerId]);

  useEffect(() => {
    if (!mapRef.current || !leafletRef.current) {
      return;
    }

    if (!pickedPoint) {
      if (pickerMarkerRef.current) {
        pickerMarkerRef.current.remove();
        pickerMarkerRef.current = null;
      }
      return;
    }

    const coordinates: [number, number] = [pickedPoint.latitude, pickedPoint.longitude];

    // The picker pin lives outside the station-markers effect on purpose: a
    // markers refresh must neither remove nor duplicate it, and a coordinate
    // change only moves the existing layer instead of recreating it.
    if (!pickerMarkerRef.current || !mapRef.current.hasLayer(pickerMarkerRef.current)) {
      const pickerMarker = leafletRef.current
        .marker(coordinates, {
          draggable: pickerDraggable,
          icon: leafletRef.current.divIcon({
            className: 'evflow-station-marker evflow-picker-marker',
            html: pickerPinSvg,
            iconAnchor: [18, 36],
            iconSize: [36, 36]
          }),
          zIndexOffset: 1200
        })
        .addTo(mapRef.current);

      pickerMarker.on('dragend', () => {
        const position = pickerMarker.getLatLng();
        onPickedPointMovedRef.current?.(position.lat, position.lng);
      });

      pickerMarkerRef.current = pickerMarker;
    } else {
      pickerMarkerRef.current.setLatLng(coordinates);
    }

    if (pickerDraggable) {
      pickerMarkerRef.current?.dragging?.enable();
    } else {
      pickerMarkerRef.current?.dragging?.disable();
    }
  }, [mapRevision, pickedPoint?.latitude, pickedPoint?.longitude, pickerDraggable]);

  useEffect(() => {
    if (!mapRef.current || !leafletRef.current) {
      return;
    }

    polylineLayersRef.current.forEach((layer) => layer.remove());
    polylineLayersRef.current = [];

    if (polylineCoordinates && polylineCoordinates.length > 1) {
      const coreColor = polylineColor || '#00696F';
      const casingColor = coreColor === '#EAB308' || coreColor === '#F59E0B' || coreColor === '#D97706' ? '#854D0E' : '#044E54';

      const casingPolyline = leafletRef.current.polyline(polylineCoordinates, {
        color: casingColor,
        weight: 8,
        opacity: 0.85,
        lineCap: 'round',
        lineJoin: 'round',
      }).addTo(mapRef.current);

      const corePolyline = leafletRef.current.polyline(polylineCoordinates, {
        color: coreColor,
        weight: 5,
        opacity: 1.0,
        lineCap: 'round',
        lineJoin: 'round',
      }).addTo(mapRef.current);

      polylineLayersRef.current = [casingPolyline, corePolyline];

      if (autoFitBounds) {
        const bounds = casingPolyline.getBounds();
        markers.forEach((marker) => {
          bounds.extend([marker.latitude, marker.longitude]);
        });
        mapRef.current.fitBounds(bounds, { padding: [50, 50] });
      }
    }

    return () => {
      polylineLayersRef.current.forEach((layer) => layer.remove());
      polylineLayersRef.current = [];
    };
  }, [mapRevision, markers, polylineCoordinates, polylineColor, autoFitBounds]);


  useEffect(() => {
    if (currentLocation) {
      renderUserLocation([currentLocation.latitude, currentLocation.longitude]);
      return;
    }

    if (!showCurrentLocationPinpoint || !navigator.geolocation) {
      return;
    }

    let cancelled = false;

    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (cancelled) {
          return;
        }

        const coordinates: [number, number] = [position.coords.latitude, position.coords.longitude];
        renderUserLocation(coordinates);
      },
      () => {
        // Browser permission denial should not block map rendering.
      },
      {
        enableHighAccuracy: true,
        maximumAge: 60_000,
        timeout: 10_000
      }
    );

    return () => {
      cancelled = true;
    };
  }, [currentLocation, showCurrentLocationPinpoint]);

  if (failed) {
    return createElement(
      'div',
      {
        style: {
          alignItems: 'center',
          background: '#d7dbdc',
          color: '#00565F',
          display: 'flex',
          fontFamily: 'system-ui, sans-serif',
          fontWeight: 800,
          height: '100%',
          justifyContent: 'center',
          textAlign: 'center',
          width: '100%'
        }
      },
      'Leaflet map failed to load'
    );
  }

  return createElement('div', {
    id: mapContainerId,
    style: {
      background: '#d7dbdc',
      height: '100%',
      minHeight: '100%',
      width: '100%',
      flex: 1
    }
  });
}
