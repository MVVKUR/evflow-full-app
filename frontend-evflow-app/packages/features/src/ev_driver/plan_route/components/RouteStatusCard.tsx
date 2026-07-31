import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { routeColors, routeRadius, routeSpacing } from '../routeTheme';

export function RouteStatusCard({ tone, title, message, children }: { tone: 'success' | 'warning' | 'error'; title: string; message: string; children?: ReactNode }) {
  const color = tone === 'success' ? routeColors.success : tone === 'warning' ? routeColors.warning : routeColors.error;
  const backgroundColor = tone === 'success' ? routeColors.successSoft : tone === 'warning' ? routeColors.warningSoft : routeColors.errorSoft;
  return <View accessibilityRole="alert" style={[styles.card, { borderColor: color, backgroundColor }]}>
    <View style={[styles.icon, { backgroundColor: color }]} />
    <View style={styles.copy}><Text style={styles.title}>{title}</Text><Text style={styles.message}>{message}</Text>{children}</View>
  </View>;
}

const styles = StyleSheet.create({
  card: { minHeight: 78, borderWidth: 1, borderRadius: routeRadius.md, padding: routeSpacing.md, flexDirection: 'row', alignItems: 'center', gap: routeSpacing.md },
  icon: { width: 38, height: 38, borderRadius: 19 }, copy: { flex: 1 },
  title: { color: routeColors.textPrimary, fontSize: 15, fontWeight: '800' },
  message: { color: routeColors.textSecondary, fontSize: 12, lineHeight: 17, marginTop: 2 },
});

