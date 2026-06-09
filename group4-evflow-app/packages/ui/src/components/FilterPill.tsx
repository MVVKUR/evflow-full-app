import { Pressable, Text } from 'react-native';
import { filterPillStyles as styles } from '../styles/styles';

type FilterPillProps = {
  label: string;
  selected?: boolean;
  onPress?: () => void;
};

export function FilterPill({ label, selected = false, onPress }: FilterPillProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.pill, selected && styles.selected]}
    >
      <Text style={[styles.label, selected && styles.selectedLabel]}>{label}</Text>
    </Pressable>
  );
}
