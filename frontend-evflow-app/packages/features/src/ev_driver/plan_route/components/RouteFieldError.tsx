import { StyleSheet, Text } from 'react-native';
import { routeColors } from '../routeTheme';

export function RouteFieldError({ message }: { message?: string }) {
  return message ? <Text accessibilityRole="alert" style={styles.error}>{message}</Text> : null;
}
const styles = StyleSheet.create({ error: { color: routeColors.error, fontSize: 11, marginTop: 4 } });

