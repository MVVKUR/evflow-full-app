import { useEffect, useRef, type ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { routeColors, routeRadius, routeShadow, routeSpacing } from '../routeTheme';

type RouteBottomSheetProps = {
  children: ReactNode;
  bottom?: number;
  scroll?: boolean;
  scrollToY?: number;
  testID?: string;
  top?: number;
};

export function RouteBottomSheet({ children, bottom = 0, scroll = true, scrollToY, testID, top }: RouteBottomSheetProps) {
  const scrollRef = useRef<ScrollView>(null);
  useEffect(() => { if (scroll && scrollToY != null) requestAnimationFrame(() => scrollRef.current?.scrollTo({ y: scrollToY, animated: true })); }, [scroll, scrollToY]);
  const content = <View style={styles.content}>{children}</View>;
  return <View testID={testID} style={[styles.sheet, { bottom }, top == null ? null : styles.boundedSheet, top == null ? null : { top }]}>
    <View style={styles.handle} />
    {scroll ? <ScrollView ref={scrollRef} style={styles.scroll} contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator>{content}</ScrollView> : content}
  </View>;
}

const styles = StyleSheet.create({
  sheet: { position: 'absolute', left: 0, right: 0, maxHeight: '82%', minHeight: 0, overflow: 'hidden', backgroundColor: routeColors.surface, borderTopLeftRadius: routeRadius.sheet, borderTopRightRadius: routeRadius.sheet, zIndex: 20, ...routeShadow },
  boundedSheet: { maxHeight: undefined },
  handle: { width: 38, height: 4, borderRadius: 2, backgroundColor: routeColors.handle, alignSelf: 'center', marginTop: routeSpacing.sm },
  scroll: { flex: 1, minHeight: 0 },
  scrollContent: { flexGrow: 0 },
  content: { paddingHorizontal: routeSpacing.lg, paddingTop: routeSpacing.md, paddingBottom: routeSpacing.xl },
});
