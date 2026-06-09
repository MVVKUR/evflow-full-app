import { createElement, useEffect, useId, useRef, useState } from 'react';

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
  onMarkerPress?: (markerId: string) => void;
  showCurrentLocationPinpoint?: boolean;
  zoom?: number;
};

type LeafletMapMarker = {
  id: string;
  label?: string;
  latitude: number;
  longitude: number;
};

type LeafletNamespace = typeof import('leaflet');
type LeafletImport = LeafletNamespace & {
  default?: LeafletNamespace;
};

const defaultCenter = {
  latitude: -6.1754,
  longitude: 106.8272
};

export function LeafletMap({
  center = defaultCenter,
  currentLocation,
  markerIconSvg,
  markers = [],
  onMarkerPress,
  showCurrentLocationPinpoint = false,
  zoom = 13
}: LeafletMapProps) {
  const reactId = useId();
  const mapContainerId = `leaflet-map-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const mapRef = useRef<import('leaflet').Map | null>(null);
  const userMarkerRef = useRef<import('leaflet').CircleMarker | null>(null);
  const stationMarkersRef = useRef<import('leaflet').Layer[]>([]);
  const leafletRef = useRef<LeafletNamespace | null>(null);
  const pendingUserLocationRef = useRef<[number, number] | null>(null);
  const [failed, setFailed] = useState(false);

  function renderUserLocation(coordinates: [number, number]) {
    pendingUserLocationRef.current = coordinates;

    if (!mapRef.current || !leafletRef.current) {
      return;
    }

    if (!userMarkerRef.current || !mapRef.current.hasLayer(userMarkerRef.current)) {
      userMarkerRef.current = leafletRef.current
        .circleMarker(coordinates, {
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
  }

  function renderStationMarkers(nextMarkers: LeafletMapMarker[]) {
    if (!mapRef.current || !leafletRef.current) {
      return;
    }

    stationMarkersRef.current.forEach((marker) => marker.remove());
    stationMarkersRef.current = nextMarkers.map((marker) => {
      const stationMarker = markerIconSvg
        ? leafletRef.current!
            .marker([marker.latitude, marker.longitude], {
              icon: leafletRef.current!.divIcon({
                className: 'evflow-station-marker',
                html: markerIconSvg,
                iconAnchor: [15, 34],
                iconSize: [30, 34],
                popupAnchor: [0, -30]
              })
            })
            .addTo(mapRef.current!)
        : leafletRef.current!
            .circleMarker([marker.latitude, marker.longitude], {
              color: '#ffffff',
              fillColor: '#007a80',
              fillOpacity: 1,
              radius: 10,
              weight: 3
            })
            .addTo(mapRef.current!);

      if (marker.label) {
        stationMarker.bindPopup(marker.label);
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

        if (pendingUserLocationRef.current) {
          renderUserLocation(pendingUserLocationRef.current);
        }
        renderStationMarkers(markers);

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
    };
  }, [center.latitude, center.longitude, mapContainerId, zoom]);

  useEffect(() => {
    mapRef.current?.setView([center.latitude, center.longitude], zoom);
  }, [center.latitude, center.longitude, zoom]);

  useEffect(() => {
    renderStationMarkers(markers);

    return () => {
      stationMarkersRef.current.forEach((marker) => marker.remove());
      stationMarkersRef.current = [];
    };
  }, [markerIconSvg, markers, onMarkerPress]);

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
