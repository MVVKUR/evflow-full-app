import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions, type GestureResponderHandlers } from 'react-native';
import { deletePlannerSavedSite, fetchPlannerSavedSites, type PlannerSavedSiteApi } from '@evflow/shared';
import { driverMapStyles as mapStyles, LeafletMap } from '@evflow/ui';
import { useNavigate } from 'react-router';
import { SvgAssetIcon } from '../../shared/SvgAssetIcon';
import { searchIcon } from '../../ev_driver/components/driverMapIcons';
import { jakartaViewport, plannerMarkers, type PlannerLayerState } from '../demandHeatmap';
import { getDrawerAwareMapCenter } from '../../ev_driver/station-status/stationDetailState';
import { LocationScoreSummary } from '../site-feasibility/LocationScoreSummary';
import { SiteFeasibilitySheet } from '../site-feasibility/SiteFeasibilitySheet';
import { calculateSiteScores } from '../site-feasibility/siteFeasibilityLogic';
import { useSiteFeasibilityDetail } from '../site-feasibility/useSiteFeasibilityDetail';
import { BookmarkButton } from '../BookmarkButton';
import type { RoadType, SiteFeasibilityData } from '../site-feasibility/siteFeasibilityTypes';

export function SavedSitesScreen({ bottomOffset = 0, topInset = 0 }: { bottomOffset?: number; topInset?: number }) {
  const { height, width } = useWindowDimensions();
  const navigate = useNavigate();
  const [items, setItems] = useState<PlannerSavedSiteApi[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [selectedSite, setSelectedSite] = useState<PlannerSavedSiteApi | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [center, setCenter] = useState(jakartaCenter);
  const [mapZoom, setMapZoom] = useState(jakartaViewport.zoom);
  const syncSelectedSaved = useCallback((saved: boolean) => {
    if (!selectedSite) return;
    setItems((current) => {
      if (!saved) return current.filter((item) => item.cell_id !== selectedSite.cell_id);
      return current.some((item) => item.cell_id === selectedSite.cell_id)
        ? current
        : [selectedSite, ...current];
    });
  }, [selectedSite]);
  const detail = useSiteFeasibilityDetail(selectedSite?.cell_id ?? null, {
    onMessage: setError,
    onSavedChange: syncSelectedSaved
  });

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void fetchPlannerSavedSites().then((result) => {
      if (active) setItems(result.items);
    }).catch(() => {
      if (active) setError('Saved sites could not be loaded.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry]);

  const remove = useCallback((site: PlannerSavedSiteApi) => {
    let removedIndex = -1;
    setItems((current) => {
      removedIndex = current.findIndex((item) => item.cell_id === site.cell_id);
      return current.filter((item) => item.cell_id !== site.cell_id);
    });
    void deletePlannerSavedSite(site.cell_id).catch(() => {
      setItems((current) => {
        if (current.some((item) => item.cell_id === site.cell_id)) return current;
        const restored = [...current];
        restored.splice(Math.max(0, removedIndex), 0, site);
        return restored;
      });
      setError('The site could not be removed. It has been restored.');
    });
  }, []);

  const markers = useMemo(() => plannerMarkers(savedSitesOnlyLayers, items.map((site) => ({
    district: cleanArea(site.kota),
    id: site.cell_id,
    latitude: site.latitude,
    longitude: site.longitude,
    score: Math.round(Math.min(Math.max(site.score ?? 0, 0), 1) * 100)
  }))), [items]);
  const expandedListSheetHeight = getExpandedListSheetHeight(height, topInset, bottomOffset);
  const expandedDetailSheetHeight = getExpandedDetailSheetHeight(height, width, topInset, bottomOffset);
  const sheetHeight = expanded ? expandedListSheetHeight : collapsedListSheetHeight;
  const detailSheetHeight = expanded ? expandedDetailSheetHeight : collapsedDetailSheetHeight;

  const openSite = useCallback((site: PlannerSavedSiteApi) => {
    setExpanded(true);
    setSelectedSite(site);
  }, []);

  useEffect(() => {
    if (!selectedSite) return;
    setCenter(getDrawerAwareMapCenter(selectedSite, siteDetailZoom, bottomOffset + detailSheetHeight));
    setMapZoom(siteDetailZoom);
  }, [bottomOffset, detailSheetHeight, selectedSite]);

  useEffect(() => {
    if (selectedSite || items.length === 0) return;
    const view = getSavedSitesMapView(items);
    setCenter(view.center);
    setMapZoom(view.zoom);
  }, [items, selectedSite]);

  const closeDetail = useCallback(() => {
    setSelectedSite(null);
    setExpanded(true);
    setCenter(jakartaCenter);
    setMapZoom(jakartaViewport.zoom);
  }, []);

  const onMarkerPress = useCallback((markerId: string) => {
    const site = items.find((item) => item.cell_id === markerId);
    if (site) openSite(site);
  }, [items, openSite]);

  return (
    <View style={mapStyles.page}>
      <LeafletMap
        center={center}
        markers={markers}
        onMarkerPress={onMarkerPress}
        polygonLayers={[]}
        selectedMarkerId={selectedSite?.cell_id ?? null}
        zoom={mapZoom}
      />
      <View style={[mapStyles.searchBar, { top: 24 + topInset }]}>
        <View style={mapStyles.searchIcon}><SvgAssetIcon height={18} svg={searchIcon} width={18} /></View>
        <Text style={styles.searchText}>Search saved locations...</Text>
      </View>
      {selectedSite ? (
        <SiteFeasibilitySheet
          activeTab={detail.activeTab}
          bottom={bottomOffset}
          data={detail.data}
          error={detail.error}
          expanded={expanded}
          financial={detail.financial}
          financialError={detail.financialError}
          financialLoading={detail.financialLoading}
          height={detailSheetHeight}
          isSaved={detail.isSaved}
          isSaving={detail.isSaving}
          loading={detail.loading}
          onClose={closeDetail}
          onFinancialRetry={detail.retryFinancial}
          onRetry={detail.retry}
          onScrollTopChange={() => undefined}
          onTabChange={detail.setActiveTab}
          onToggleExpanded={() => setExpanded((value) => !value)}
          onToggleSaved={detail.toggleSaved}
          panHandlers={noPanHandlers}
        />
      ) : <View style={[mapStyles.sheet, styles.sheet, { bottom: bottomOffset, height: sheetHeight }]}>
        <Pressable
          accessibilityLabel={expanded ? 'Collapse Saved Sites' : 'Expand Saved Sites'}
          accessibilityRole="button"
          accessibilityState={{ expanded }}
          onPress={() => setExpanded((value) => !value)}
          style={mapStyles.drawerHandleWrap}
        ><View style={mapStyles.drawerHandle} /></Pressable>
        <Text accessibilityRole="header" style={styles.title}>SAVED SITES</Text>
        {!expanded ? null : loading ? (
          <View accessibilityLiveRegion="polite" style={styles.state}><ActivityIndicator color="#007D8C" /><Text style={styles.stateText}>Loading saved sites...</Text></View>
        ) : error && items.length === 0 ? (
          <View accessibilityLiveRegion="polite" style={styles.state}><Text style={styles.error}>{error}</Text><Pressable accessibilityRole="button" onPress={() => setRetry((value) => value + 1)} style={styles.action}><Text style={styles.actionText}>Retry</Text></Pressable></View>
        ) : items.length === 0 ? (
          <View style={styles.state}><Text style={styles.emptyTitle}>No saved sites yet.</Text><Text style={styles.stateText}>Review Optimal Sites on the Heatmap and bookmark locations you want to compare.</Text><Pressable accessibilityRole="button" onPress={() => navigate('/business-dashboard/demand-heatmap')} style={styles.action}><Text style={styles.actionText}>Go to Heatmap</Text></Pressable></View>
        ) : (
          <ScrollView accessibilityLabel="Saved sites" contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
            {error ? <Text accessibilityLiveRegion="polite" style={styles.error}>{error}</Text> : null}
            {items.map((site) => <SavedSiteCard key={site.cell_id} onOpen={() => openSite(site)} onRemove={() => remove(site)} site={site} />)}
          </ScrollView>
        )}
      </View>}
    </View>
  );
}

function SavedSiteCard({ onOpen, onRemove, site }: { onOpen: () => void; onRemove: () => void; site: PlannerSavedSiteApi }) {
  const data = savedSiteData(site);
  return (
    <View style={styles.card}>
      <Pressable accessibilityLabel={`Open details for ${site.cell_id}`} accessibilityRole="button" onPress={onOpen} style={styles.cardOpen}>
        <Text style={styles.siteTitle}>{site.cell_id} ({cleanArea(site.kota)})</Text>
        <LocationScoreSummary embedded scores={calculateSiteScores(data)} />
      </Pressable>
      <View style={styles.cardBookmark}><BookmarkButton isSaved onPress={onRemove} /></View>
    </View>
  );
}

function savedSiteData(site: PlannerSavedSiteApi): SiteFeasibilityData {
  const score = Math.round(Math.min(Math.max(site.score ?? 0, 0), 1) * 100);
  return {
    optimalSiteId: site.cell_id, locationCode: site.cell_id, locationName: cleanArea(site.kota),
    locationScore: score, heatmapScore: score, commercialPoiCount: site.poi_total,
    nearestSpkluDistanceKm: site.nearest_station_m === null ? 5 : site.nearest_station_m / 1000,
    roadType: roadType(site.road_nodes), residentialPoints: Math.round(Math.min(Math.max(site.lu_residential_share, 0), 1) * 50),
    financial: null, nearbyStations: []
  };
}

function roadType(nodes: number): RoadType { return nodes >= 20 ? 'primary' : nodes >= 8 ? 'secondary' : 'local'; }
function cleanArea(area: string | null) { return area?.replace(/^(Kota|Kabupaten)\s+/i, '').trim() || 'Jabodetabek Opportunity Zone'; }

const noPanHandlers = {} as GestureResponderHandlers;
const jakartaCenter = { latitude: -6.1754, longitude: 106.8272 };
const collapsedListSheetHeight = 76;
const collapsedDetailSheetHeight = 258;
const siteDetailZoom = 15;
const savedSitesOnlyLayers: PlannerLayerState = {
  commercialPois: false,
  demandHeatmap: false,
  existingSpklus: false,
  landUse: false,
  optimalSites: true,
  populationDensity: false
};

function getExpandedListSheetHeight(screenHeight: number, topInset: number, bottomOffset: number) {
  return Math.max(collapsedDetailSheetHeight, Math.floor(screenHeight - bottomOffset - (topInset + 102)));
}

function getExpandedDetailSheetHeight(screenHeight: number, screenWidth: number, topInset: number, bottomOffset: number) {
  const usableHeight = screenHeight - bottomOffset;
  const roomBelowSearch = usableHeight - (topInset + 102);
  const target = screenWidth < 768 ? roomBelowSearch : Math.min(720, usableHeight * 0.8, roomBelowSearch);
  return Math.max(collapsedDetailSheetHeight, Math.floor(target));
}

function getSavedSitesMapView(sites: PlannerSavedSiteApi[]) {
  const latitudes = sites.map((site) => site.latitude);
  const longitudes = sites.map((site) => site.longitude);
  const north = Math.max(...latitudes);
  const south = Math.min(...latitudes);
  const east = Math.max(...longitudes);
  const west = Math.min(...longitudes);
  const span = Math.max(north - south, east - west);
  let zoom = 9;
  if (span <= 0.48) zoom = 10;
  if (span <= 0.24) zoom = 11;
  if (span <= 0.12) zoom = 12;
  if (span <= 0.06) zoom = 13;
  if (span <= 0.03) zoom = 14;
  return {
    center: { latitude: (north + south) / 2, longitude: (east + west) / 2 },
    zoom
  };
}

const styles = StyleSheet.create({
  sheet: { paddingHorizontal: 16, paddingBottom: 0 },
  title: { color: '#172033', fontSize: 17, fontWeight: '900', letterSpacing: 0.8, marginBottom: 12 },
  searchText: { color: '#819097', flex: 1, fontSize: 14 },
  state: { alignItems: 'center', flex: 1, gap: 12, justifyContent: 'center', padding: 24 },
  stateText: { color: '#607077', fontSize: 13, lineHeight: 19, textAlign: 'center' },
  emptyTitle: { color: '#172033', fontSize: 17, fontWeight: '800' },
  error: { color: '#9A3412', fontSize: 12, textAlign: 'center' },
  action: { alignItems: 'center', borderColor: '#00696F', borderRadius: 8, borderWidth: 1, justifyContent: 'center', minHeight: 44, paddingHorizontal: 18 },
  actionText: { color: '#005F64', fontSize: 12, fontWeight: '800' },
  list: { gap: 14, paddingBottom: 28 },
  card: { backgroundColor: '#F8FAFC', borderColor: '#DCE5EA', borderRadius: 16, borderWidth: 1, overflow: 'hidden', position: 'relative' },
  cardOpen: { padding: 16 },
  cardBookmark: { position: 'absolute', right: 16, top: 16, zIndex: 2 },
  siteTitle: { color: '#172033', fontSize: 15, fontWeight: '800', paddingRight: 54 }
});
