import type { ReactNode } from 'react';
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View, type GestureResponderHandlers, type ViewStyle } from 'react-native';
import { driverMapStyles as mapStyles } from '@evflow/ui';
import { closeButtonIcon } from '../../ev_driver/components/driverMapIcons';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import { FeasibilityScoreTab } from './FeasibilityScoreTab';
import { FinancialProjectionsTab } from './FinancialProjectionsTab';
import { LocationScoreSummary } from './LocationScoreSummary';
import { NearbyStationsTab } from './NearbyStationsTab';
import { calculateSiteScores } from './siteFeasibilityLogic';
import type { SiteFeasibilityData, SiteFeasibilityTab } from './siteFeasibilityTypes';

const tabs: Array<{ key: SiteFeasibilityTab; label: string }> = [
  { key: 'feasibility', label: 'Feasibility Score' },
  { key: 'financial', label: 'Financial Projections' },
  { key: 'nearby', label: 'Nearby Stations' }
];

export function SiteFeasibilitySheet({ activeTab, bottom, data, error, expanded, financial, financialError, financialLoading, height, loading, onClose, onFinancialRetry, onRetry, onScrollTopChange, onTabChange, onToggleExpanded, panHandlers }: {
  activeTab: SiteFeasibilityTab;
  bottom: number;
  data: SiteFeasibilityData | null;
  error: string | null;
  expanded: boolean;
  financial: SiteFeasibilityData['financial'];
  financialError: string | null;
  financialLoading: boolean;
  height: number;
  loading: boolean;
  onClose: () => void;
  onFinancialRetry: () => void;
  onRetry: () => void;
  onScrollTopChange: (atTop: boolean) => void;
  onTabChange: (tab: SiteFeasibilityTab) => void;
  onToggleExpanded: () => void;
  panHandlers: GestureResponderHandlers;
}) {
  const scores = data ? calculateSiteScores(data) : null;
  let content: ReactNode = null;
  if (data && scores) {
    content = activeTab === 'feasibility'
      ? <FeasibilityScoreTab data={data} scores={scores} />
      : activeTab === 'financial'
        ? <FinancialProjectionsTab error={financialError} financial={financial} loading={financialLoading} onRetry={onFinancialRetry} />
        : <NearbyStationsTab basis={data.nearbyBenchmarkBasis} stations={data.nearbyStations} />;
  }

  return (
    <View style={[mapStyles.sheet, styles.sheet, getSheetTransitionStyle(height), { bottom }]} {...panHandlers}>
      <Pressable
        accessibilityLabel={expanded ? 'Collapse site feasibility' : 'Expand site feasibility'}
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={onToggleExpanded}
        style={mapStyles.drawerHandleWrap}
      >
        <View style={mapStyles.drawerHandle} />
      </Pressable>
      <View style={styles.header}>
        <Text numberOfLines={1} style={styles.title}>{data ? `${data.locationCode} (${data.locationName})` : 'Site Feasibility'}</Text>
        <Pressable accessibilityLabel="Close site feasibility" accessibilityRole="button" onPress={onClose} style={mapStyles.closeButton}>
          <SvgAssetIcon color="#191C1D" height={14} name="close" svg={closeButtonIcon} width={14} />
        </Pressable>
      </View>
      {error ? (
        <View accessibilityLiveRegion="polite" style={styles.errorCard}>
          <Text style={styles.errorText}>{error}</Text>
          <Pressable accessibilityLabel="Retry site analysis" accessibilityRole="button" onPress={onRetry} style={styles.retryButton}>
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </View>
      ) : loading || !data || !scores ? (
        <View style={styles.loading}><ActivityIndicator color="#007D8C" /><Text style={styles.loadingText}>Loading site analysis...</Text></View>
      ) : (
        <>
          <View style={styles.summary}><LocationScoreSummary scores={scores} /></View>
          <View
            accessibilityElementsHidden={!expanded}
            importantForAccessibility={expanded ? 'auto' : 'no-hide-descendants'}
            style={[styles.detailContent, getDetailTransitionStyle(expanded)]}
          >
            <View accessibilityRole="tablist" style={styles.tabs}>
              {tabs.map((tab) => (
                <Pressable key={tab.key} accessibilityRole="tab" accessibilityState={{ selected: activeTab === tab.key }} onPress={() => onTabChange(tab.key)} style={[styles.tab, activeTab === tab.key && styles.tabActive]}>
                  <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>{tab.label}</Text>
                </Pressable>
              ))}
            </View>
            <ScrollView contentContainerStyle={styles.content} onScroll={(event) => onScrollTopChange(event.nativeEvent.contentOffset.y <= 0)} scrollEnabled={expanded} scrollEventThrottle={16} showsVerticalScrollIndicator={false}>
              {content}
            </ScrollView>
          </View>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { paddingBottom: 0, paddingHorizontal: 0 },
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', paddingBottom: 12, paddingHorizontal: 16 },
  title: { color: '#172033', flex: 1, fontSize: 18, fontWeight: '800' },
  summary: { paddingHorizontal: 16 },
  tabs: { backgroundColor: '#E2E5FF', borderRadius: 8, flexDirection: 'row', marginHorizontal: 16, marginTop: 16, padding: 3 },
  tab: { alignItems: 'center', borderRadius: 5, flex: 1, justifyContent: 'center', minHeight: 54, paddingHorizontal: 4 },
  tabActive: { backgroundColor: '#FFFFFF', boxShadow: '0 1px 3px rgba(30,41,59,0.08)' },
  tabText: { color: '#3F4859', fontSize: 12, lineHeight: 18, textAlign: 'center' },
  tabTextActive: { color: '#172033', fontWeight: '600' },
  detailContent: { flex: 1 },
  content: { padding: 16, paddingBottom: 30 },
  loading: { alignItems: 'center', flex: 1, gap: 10, justifyContent: 'center' },
  loadingText: { color: '#607077', fontSize: 12 },
  errorCard: { backgroundColor: '#FFF7ED', borderColor: '#F4C384', borderRadius: 12, borderWidth: 1, gap: 12, margin: 16, padding: 14 },
  errorText: { color: '#7A4410', fontSize: 12, lineHeight: 17 },
  retryButton: { alignItems: 'center', alignSelf: 'flex-start', borderColor: '#00696F', borderRadius: 8, borderWidth: 1, justifyContent: 'center', minHeight: 44, paddingHorizontal: 16 },
  retryText: { color: '#005F64', fontSize: 12, fontWeight: '800' }
});

type WebTransitionStyle = ViewStyle & {
  transitionDuration?: string;
  transitionProperty?: string;
  transitionTimingFunction?: string;
};

function getSheetTransitionStyle(height: number): WebTransitionStyle {
  return {
    height,
    ...(Platform.OS === 'web' ? {
      transitionDuration: '240ms',
      transitionProperty: 'height',
      transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)'
    } : {})
  };
}

function getDetailTransitionStyle(expanded: boolean): WebTransitionStyle {
  return {
    opacity: expanded ? 1 : 0,
    pointerEvents: expanded ? 'auto' : 'none',
    transform: [{ translateY: expanded ? 0 : 16 }],
    ...(Platform.OS === 'web' ? {
      transitionDuration: '180ms',
      transitionProperty: 'opacity, transform',
      transitionTimingFunction: 'ease-out'
    } : {})
  };
}
