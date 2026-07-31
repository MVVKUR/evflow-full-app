import type { ReactNode } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { routeColors, routeRadius, routeShadow, routeSpacing } from '../routeTheme';

export function RouteDialog({ visible, title, children, primaryLabel, onPrimary, secondaryLabel, onSecondary, danger = false, accessibilityLabel }: {
  visible: boolean; title: string; children: ReactNode; primaryLabel: string; onPrimary: () => void; secondaryLabel?: string; onSecondary?: () => void; danger?: boolean; accessibilityLabel?: string;
}) {
  return <Modal transparent visible={visible} animationType="fade" onRequestClose={onSecondary ?? onPrimary}>
    <View style={styles.overlay} accessibilityViewIsModal>
      <View style={styles.dialog} accessibilityRole="alert" accessibilityLabel={accessibilityLabel ?? title}>
        <View style={[styles.hero, danger && styles.heroDanger]} />
        <Text style={styles.title}>{title}</Text>
        <View style={styles.body}>{children}</View>
        <Pressable accessibilityRole="button" style={[styles.primary, danger && styles.danger]} onPress={onPrimary}><Text style={styles.primaryText}>{primaryLabel}</Text></Pressable>
        {secondaryLabel && onSecondary ? <Pressable accessibilityRole="button" style={styles.secondary} onPress={onSecondary}><Text style={styles.secondaryText}>{secondaryLabel}</Text></Pressable> : null}
      </View>
    </View>
  </Modal>;
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: routeColors.overlay, justifyContent: 'center', padding: 24 },
  dialog: { backgroundColor: routeColors.surface, borderRadius: routeRadius.lg, padding: 20, ...routeShadow },
  hero: { width: 52, height: 52, borderRadius: 26, backgroundColor: routeColors.brandSoft, marginBottom: 14 },
  heroDanger: { backgroundColor: routeColors.errorSoft },
  title: { color: routeColors.textPrimary, fontWeight: '800', fontSize: 22, marginBottom: routeSpacing.md },
  body: { gap: routeSpacing.sm, marginBottom: routeSpacing.lg },
  primary: { minHeight: 48, borderRadius: routeRadius.md, backgroundColor: routeColors.brand, alignItems: 'center', justifyContent: 'center' },
  danger: { backgroundColor: routeColors.error },
  primaryText: { color: routeColors.onBrand, fontWeight: '800', fontSize: 15 },
  secondary: { minHeight: 48, marginTop: routeSpacing.md, borderWidth: 1.5, borderColor: routeColors.brand, borderRadius: routeRadius.md, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { color: routeColors.brand, fontWeight: '800', fontSize: 15 },
});
