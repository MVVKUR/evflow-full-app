import { useEffect, useMemo, useRef, useState } from 'react';
import * as Location from 'expo-location';
import { escapeHtml } from '@evflow/shared';
import { View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { leafletMapStyles as styles } from '../styles/styles';

type LeafletMapProps = {
  autoFitBounds?: boolean;
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
  polylineColor?: string;
  polylineCoordinates?: [number, number][];
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
};

const defaultCenter = {
  latitude: -6.1754,
  longitude: 106.8272
};

type Coordinates = {
  latitude: number;
  longitude: number;
};

function toInlineScriptJson(value: string): string {
  // JSON.stringify leaves '<' unescaped, so an untrusted value containing
  // '</script>' would terminate the WebView's inline script block. The
  // \\u003c escape parses back to '<' inside the generated string literal.
  return JSON.stringify(value).replace(/</g, '\\u003c');
}

export function LeafletMap({
  autoFitBounds,
  center = defaultCenter,
  currentLocation,
  markerIconSvg,
  markers = [],
  onMarkerPress,
  polylineColor,
  polylineCoordinates,
  radiusKm,
  selectedMarkerIconSvg,
  selectedMarkerId = null,
  showCurrentLocationPinpoint = false,
  zoom = 13
}: LeafletMapProps) {
  const webViewRef = useRef<WebView>(null);
  const selectedMarkerIdRef = useRef<string | null>(selectedMarkerId);
  const [userLocation, setUserLocation] = useState<Coordinates | null>(null);
  const html = useMemo(
    () => `
    <!DOCTYPE html>
    <html>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
          body { padding: 0; margin: 0; background-color: #d7dbdc; }
          html, body, #map { height: 100%; width: 100%; }
          .evflow-station-marker svg { display: block; filter: drop-shadow(0 3px 5px rgba(0, 86, 95, 0.28)); }
        </style>
      </head>
      <body>
        <div id="map"></div>
        <script>
          var map = L.map('map', {
            zoomControl: false,
            attributionControl: true,
            center: [${center.latitude}, ${center.longitude}],
            zoom: ${zoom}
          });
          L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
          }).addTo(map);

          var stationIcon = ${markerIconSvg ? `L.divIcon({ className: 'evflow-station-marker', html: ${JSON.stringify(markerIconSvg)}, iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -20] })` : 'null'};
          var selectedStationIcon = ${
            selectedMarkerIconSvg
              ? `L.divIcon({ className: 'evflow-station-marker evflow-station-marker--selected', html: ${JSON.stringify(selectedMarkerIconSvg)}, iconSize: [44, 44], iconAnchor: [22, 22], popupAnchor: [0, -26] })`
              : 'null'
          };
          var stationMarkers = {};

          ${markers
            .map(
              (marker) => {
                const isOrigin = marker.type === 'origin' || marker.id === 'origin';
                const isDestination = marker.type === 'destination' || marker.id === 'destination';
                const isChargingStop = marker.type === 'charging_stop';
                let customIcon = 'stationIcon';
                if (isOrigin) {
                  customIcon = `L.divIcon({ className: 'evflow-station-marker', html: '<div style="width: 20px; height: 20px; background: #1A73E8; border: 3px solid #FFFFFF; border-radius: 50%; box-shadow: 0 2px 6px rgba(0,0,0,0.35);"></div>', iconSize: [20, 20], iconAnchor: [10, 10], popupAnchor: [0, -12] })`;
                } else if (isDestination) {
                  customIcon = `L.divIcon({ className: 'evflow-station-marker', html: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 3px 5px rgba(0,0,0,0.4));"><path d="M12 2C8.13 2 5 5.13 5 9C5 14.25 12 22 12 22C12 22 19 14.25 19 9C19 5.13 15.87 2 12 2ZM12 11.5C10.62 11.5 9.5 10.38 9.5 9C9.5 7.62 10.62 6.5 12 6.5C13.38 6.5 14.5 7.62 14.5 9C14.5 10.38 13.38 11.5 12 11.5Z" fill="#DC2626"/><circle cx="12" cy="9" r="2.5" fill="#FFFFFF"/></svg>', iconSize: [32, 32], iconAnchor: [16, 32], popupAnchor: [0, -32] })`;
                } else if (isChargingStop) {
                  customIcon = `L.divIcon({ className: 'evflow-station-marker', html: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 3px 5px rgba(0,0,0,0.4));"><path d="M12 2C8.13 2 5 5.13 5 9C5 14.25 12 22 12 22C12 22 19 14.25 19 9C19 5.13 15.87 2 12 2Z" fill="#F59E0B"/><path d="M13 7.5L9.5 11H12V14.5L15.5 11H13V7.5Z" fill="#FFFFFF"/></svg>', iconSize: [32, 32], iconAnchor: [16, 32], popupAnchor: [0, -32] })`;
                }
                const zIndex = isDestination ? 900 : isChargingStop ? 850 : isOrigin ? 800 : 0;
                const safeId = marker.id.replace(/[^a-zA-Z0-9_]/g, '_');
                return `
          var markerIcon_${safeId} = ${customIcon};
          var marker_${safeId} = markerIcon_${safeId}
            ? L.marker([${marker.latitude}, ${marker.longitude}], { icon: markerIcon_${safeId}, zIndexOffset: ${zIndex} }).addTo(map)
            : L.circleMarker([${marker.latitude}, ${marker.longitude}], {
                color: '#ffffff',
                fillColor: '#007a80',
                fillOpacity: 1,
                radius: 10,
                weight: 3
              }).addTo(map);
          stationMarkers[${toInlineScriptJson(marker.id)}] = marker_${safeId};
          marker_${safeId}
            .bindPopup(${JSON.stringify(escapeHtml(marker.label ?? 'Selected station'))})
            .on('click', function() {
              window.ReactNativeWebView && window.ReactNativeWebView.postMessage(${toInlineScriptJson(
                JSON.stringify({ type: 'markerPress', markerId: marker.id })
              )});
            });
          `;
              }
            )
            .join('')}

          window.setSelectedMarker = function(selectedId) {
            Object.keys(stationMarkers).forEach(function(markerId) {
              var stationMarker = stationMarkers[markerId];
              var isSelected = selectedId != null && markerId === selectedId;

              if (stationMarker.setIcon && stationIcon) {
                stationMarker.setIcon(isSelected && selectedStationIcon ? selectedStationIcon : stationIcon);
                stationMarker.setZIndexOffset(isSelected ? 1000 : 0);
              } else if (stationMarker.setStyle) {
                stationMarker.setStyle({ fillColor: isSelected ? '#00E0EB' : '#007a80' });
                stationMarker.setRadius && stationMarker.setRadius(isSelected ? 12 : 10);
              }
            });
          };

          var userMarker = null;
          var radiusCircle = null;
          window.setUserLocation = function(latitude, longitude) {
            var coordinates = [latitude, longitude];

            if (!userMarker) {
              userMarker = L.circleMarker(coordinates, {
                color: '#ffffff',
                fillColor: '#00E0EB',
                fillOpacity: 1,
                radius: 9,
                weight: 3
              }).addTo(map).bindPopup('Your current location');
            } else {
              userMarker.setLatLng(coordinates);
            }

            if (radiusCircle) {
              radiusCircle.setLatLng(coordinates);
            }
          };

          window.setRadius = function(meters, latitude, longitude) {
            if (!meters || meters <= 0 || latitude == null || longitude == null) {
              if (radiusCircle) {
                map.removeLayer(radiusCircle);
                radiusCircle = null;
              }
              return;
            }

            var coordinates = [latitude, longitude];

            if (!radiusCircle) {
              radiusCircle = L.circle(coordinates, {
                color: '#00696F',
                dashArray: '6 6',
                fillColor: '#00C2CB',
                fillOpacity: 0.12,
                interactive: false,
                opacity: 0.8,
                radius: meters,
                weight: 2
              }).addTo(map);
            } else {
              radiusCircle.setLatLng(coordinates);
              radiusCircle.setRadius(meters);
            }
          };

          ${
            currentLocation
              ? `window.setUserLocation(${currentLocation.latitude}, ${currentLocation.longitude});`
              : ''
          }
          ${
            currentLocation && radiusKm
              ? `window.setRadius(${radiusKm * 1000}, ${currentLocation.latitude}, ${currentLocation.longitude});`
              : ''
          }

          var routeLines = [];
          var routeMarkerCoords = ${JSON.stringify(markers.map((marker) => [marker.latitude, marker.longitude]))};
          window.setPolyline = function(coords, color, autoFit) {
            routeLines.forEach(function(line) { map.removeLayer(line); });
            routeLines = [];

            if (coords && coords.length > 1) {
              var casingColor = (color === '#EAB308' || color === '#F59E0B' || color === '#D97706') ? '#854D0E' : '#044E54';

              var casingLine = L.polyline(coords, {
                color: casingColor, weight: 8, opacity: 0.85, lineCap: 'round', lineJoin: 'round'
              }).addTo(map);

              var coreLine = L.polyline(coords, {
                color: color || '#00696F', weight: 5, opacity: 1.0, lineCap: 'round', lineJoin: 'round'
              }).addTo(map);

              routeLines.push(casingLine, coreLine);

              if (autoFit) {
                var bounds = casingLine.getBounds();
                routeMarkerCoords.forEach(function(coord) {
                  bounds.extend(coord);
                });
                map.fitBounds(bounds, { padding: [50, 50] });
              }
            }
          };

          ${
            polylineCoordinates && polylineCoordinates.length > 1
              ? `window.setPolyline(${JSON.stringify(polylineCoordinates)}, ${JSON.stringify(polylineColor || '#00696F')}, ${Boolean(autoFitBounds)});`
              : ''
          }

          // Re-center map when props change via reloading html
        </script>
      </body>
    </html>
  `,
    [autoFitBounds, center.latitude, center.longitude, currentLocation, markerIconSvg, markers, polylineColor, polylineCoordinates, radiusKm, selectedMarkerIconSvg, zoom]
  );

  function injectSelectedMarker() {
    webViewRef.current?.injectJavaScript(`
      window.setSelectedMarker && window.setSelectedMarker(${JSON.stringify(selectedMarkerIdRef.current)});
      true;
    `);
  }

  useEffect(() => {
    if (currentLocation) {
      setUserLocation(currentLocation);
      return;
    }

    if (!showCurrentLocationPinpoint) {
      return;
    }

    let mounted = true;

    async function requestLocation() {
      const permission = await Location.requestForegroundPermissionsAsync();

      if (!mounted || permission.status !== Location.PermissionStatus.GRANTED) {
        return;
      }

      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced
      });

      if (mounted) {
        setUserLocation({
          latitude: location.coords.latitude,
          longitude: location.coords.longitude
        });
      }
    }

    requestLocation();

    return () => {
      mounted = false;
    };
  }, [currentLocation, showCurrentLocationPinpoint]);

  useEffect(() => {
    selectedMarkerIdRef.current = selectedMarkerId ?? null;
    injectSelectedMarker();
  }, [selectedMarkerId]);

  useEffect(() => {
    if (!userLocation) {
      return;
    }

    webViewRef.current?.injectJavaScript(`
      window.setUserLocation(${userLocation.latitude}, ${userLocation.longitude});
      true;
    `);
  }, [userLocation]);

  useEffect(() => {
    const center = userLocation ?? currentLocation ?? null;
    const meters = radiusKm && center ? radiusKm * 1000 : 0;

    webViewRef.current?.injectJavaScript(`
      window.setRadius && window.setRadius(${meters}, ${center ? center.latitude : 'null'}, ${center ? center.longitude : 'null'});
      true;
    `);
  }, [currentLocation, radiusKm, userLocation]);

  useEffect(() => {
    webViewRef.current?.injectJavaScript(`
      window.setPolyline && window.setPolyline(${JSON.stringify(polylineCoordinates || [])}, ${JSON.stringify(polylineColor || '#00696F')}, ${Boolean(autoFitBounds)});
      true;
    `);
  }, [markers, polylineCoordinates, polylineColor, autoFitBounds]);

  function handleMessage(event: WebViewMessageEvent) {
    try {
      const message = JSON.parse(event.nativeEvent.data) as { type?: string; markerId?: string };

      if (message.type === 'markerPress' && message.markerId) {
        onMarkerPress?.(message.markerId);
      }
    } catch {
      // Ignore non-map messages.
    }
  }

  return (
    <View style={styles.container}>
      <WebView
        ref={webViewRef}
        source={{ html }}
        originWhitelist={['*']}
        style={styles.map}
        scrollEnabled={false}
        bounces={false}
        onMessage={handleMessage}
        onLoadEnd={injectSelectedMarker}
      />
    </View>
  );
}
