import { Text, View } from 'react-native';
import { mapViewStyles as styles } from '@evflow/ui';
import type { MapMarker } from './types';

type MapViewProps = {
  markers: MapMarker[];
};

export function MapView({ markers }: MapViewProps) {
  return (
    <View style={styles.nativeContainer}>
      <Text style={styles.nativeTitle}>Native map placeholder</Text>
      <Text style={styles.nativeBody}>{markers.length} chargers ready for native map integration.</Text>
    </View>
  );
}
