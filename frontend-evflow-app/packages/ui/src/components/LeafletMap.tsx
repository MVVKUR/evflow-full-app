import { useEffect, useMemo, useRef, useState } from 'react';
import * as Location from 'expo-location';
import { View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { leafletMapStyles as styles } from '../styles/styles';

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
  radiusKm?: number | null;
  showCurrentLocationPinpoint?: boolean;
  zoom?: number;
};

type LeafletMapMarker = {
  id: string;
  label?: string;
  latitude: number;
  longitude: number;
};

const defaultCenter = {
  latitude: -6.1754,
  longitude: 106.8272
};

type Coordinates = {
  latitude: number;
  longitude: number;
};

export function LeafletMap({
  center = defaultCenter,
  currentLocation,
  markerIconSvg,
  markers = [],
  onMarkerPress,
  radiusKm,
  showCurrentLocationPinpoint = false,
  zoom = 13
}: LeafletMapProps) {
  const webViewRef = useRef<WebView>(null);
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

          var stationIcon = ${markerIconSvg ? `L.divIcon({ className: 'evflow-station-marker', html: ${JSON.stringify(markerIconSvg)}, iconSize: [30, 34], iconAnchor: [15, 34], popupAnchor: [0, -30] })` : 'null'};

          ${markers
            .map(
              (marker) => `
          var marker_${marker.id.replace(/[^a-zA-Z0-9_]/g, '_')} = stationIcon
            ? L.marker([${marker.latitude}, ${marker.longitude}], { icon: stationIcon }).addTo(map)
            : L.circleMarker([${marker.latitude}, ${marker.longitude}], {
                color: '#ffffff',
                fillColor: '#007a80',
                fillOpacity: 1,
                radius: 10,
                weight: 3
              }).addTo(map);
          marker_${marker.id.replace(/[^a-zA-Z0-9_]/g, '_')}
            .bindPopup(${JSON.stringify(marker.label ?? 'Selected station')})
            .on('click', function() {
              window.ReactNativeWebView && window.ReactNativeWebView.postMessage(${JSON.stringify(
                JSON.stringify({ type: 'markerPress', markerId: marker.id })
              )});
            });
          `
            )
            .join('')}
          
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

          // Re-center map when props change via reloading html
        </script>
      </body>
    </html>
  `,
    [center.latitude, center.longitude, currentLocation, markerIconSvg, markers, radiusKm, zoom]
  );

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
      />
    </View>
  );
}
