import { Text, View } from 'react-native';
import { mockDriverScreenStyles as styles } from '@evflow/ui';

type BusinessPlannerEmptyScreenProps = {
  title: string;
  topInset?: number;
};

/** Matches the existing EV Driver in-development screen treatment. */
export function BusinessPlannerEmptyScreen({ title, topInset = 0 }: BusinessPlannerEmptyScreenProps) {
  return (
    <View style={[styles.page, { paddingTop: 24 + topInset }]}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.body}>The feature for this screen is under development.</Text>
    </View>
  );
}
