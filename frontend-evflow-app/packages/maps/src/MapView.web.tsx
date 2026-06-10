import { Text, View } from 'react-native';
import { mapViewStyles as styles } from '@evflow/ui';
import type { MapMarker } from './types';

type MapViewProps = {
  markers: MapMarker[];
};

export function MapView({ markers }: MapViewProps) {
  return (
    <View style={styles.webContainer}>
      <Text style={styles.webTitle}>Web map placeholder</Text>
      {markers.map((marker) => (
        <Text key={marker.id} style={styles.webMarker}>
          {marker.title} ({marker.latitude.toFixed(4)}, {marker.longitude.toFixed(4)})
        </Text>
      ))}
    </View>
  );
}
