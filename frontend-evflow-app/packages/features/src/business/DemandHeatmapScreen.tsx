import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  LayoutAnimation,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  UIManager,
  View,
  useWindowDimensions,
  type ViewStyle
} from 'react-native';
import {
  driverMapStyles as mapStyles,
  LeafletMap,
  type LeafletMapMarker,
  type LeafletPolygonLayer,
  type MapViewport
} from '@evflow/ui';
import { fetchPlannerCandidates, fetchPlannerCells, fetchStations, PlannerApiError } from '@evflow/shared';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { closeButtonIcon, filterSettingIcon, searchIcon } from '../ev_driver/components/driverMapIcons';
import { getDrawerAwareMapCenter } from '../ev_driver/station-status/stationDetailState';
import { getUserLocation } from '../ev_driver/utils/location';
import {
  commercialPoiIcon,
  currentLocationIcon,
  heatmapLayerIcon,
  landUseIcon,
  layersIcon,
  optimalSiteIcon,
  populationIcon,
  spkluLayerIcon
} from './demandHeatmapIcons';
import {
  defaultPlannerLayers,
  demandHeatmapPolygons,
  generateMockOptimalSites,
  jakartaViewport,
  plannerMarkers,
  plannerPolygons,
  prioritySemanticCategory,
  type OptimalSite,
  type PlannerLayerKey,
  type PlannerLayerState
} from './demandHeatmap';
import {
  plannerCandidateToOptimalSite,
  plannerCellsToMetricPolygons,
  plannerCellsToPolygons,
  plannerLandUseToPolygons,
  plannerStationsToMarkers,
  plannerViewportBbox,
  type PlannerLandUseMetric
} from './plannerApiAdapters';
import { SiteFeasibilitySheet } from './site-feasibility/SiteFeasibilitySheet';
import { resolveOptimalSite } from './site-feasibility/siteFeasibilityLogic';
import { getSiteFeasibility } from './site-feasibility/siteFeasibilityData';
import { getSiteFinancialLifecycleKey, getSiteFinancialProjection, isMockOptimalSiteId } from './site-feasibility/siteFeasibilityFinancial';
import { getMockSiteFeasibility } from './site-feasibility/siteFeasibilityMockData';
import type { FinancialProjection, SiteFeasibilityData, SiteFeasibilityTab } from './site-feasibility/siteFeasibilityTypes';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

type DemandHeatmapScreenProps = {
  bottomOffset?: number;
  topInset?: number;
};

type Coordinates = {
  latitude: number;
  longitude: number;
};

type PlannerSheetMode = 'layers' | 'site-feasibility';

type LayerRow = {
  icon: string;
  key: PlannerLayerKey;
  subtitle: string;
  title: string;
};

const collapsedSheetHeight = 104;
const collapsedSiteSheetHeight = 258;
const siteDetailZoom = 15;
const sheetAnimation = LayoutAnimation.Presets.easeInEaseOut;

const mockLocations: Record<string, Coordinates> = {
  jakarta: { latitude: -6.1754, longitude: 106.8272 },
  'south jakarta': { latitude: -6.2615, longitude: 106.8106 },
  'central jakarta': { latitude: -6.1865, longitude: 106.8341 },
  'west jakarta': { latitude: -6.1683, longitude: 106.7588 }
};

const layerRows: LayerRow[] = [
  { key: 'optimalSites', icon: optimalSiteIcon, title: 'Optimal Sites', subtitle: 'AI Recommended' },
  { key: 'demandHeatmap', icon: heatmapLayerIcon, title: 'Demand Heatmap', subtitle: 'AI Gap Analysis' },
  { key: 'existingSpklus', icon: spkluLayerIcon, title: 'Existing SPKLUs', subtitle: 'Active Network' },
  { key: 'commercialPois', icon: commercialPoiIcon, title: 'Commercial POIs', subtitle: 'Activity Density' },
  { key: 'populationDensity', icon: populationIcon, title: 'Population Density', subtitle: 'Census Data' },
  { key: 'landUse', icon: landUseIcon, title: 'Land Use', subtitle: 'Grid & Land Use' }
];

export function DemandHeatmapScreen({ bottomOffset = 0, topInset = 0 }: DemandHeatmapScreenProps) {
  const { height, width } = useWindowDimensions();
  const [layers, setLayers] = useState<PlannerLayerState>(defaultPlannerLayers);
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [viewport, setViewport] = useState<MapViewport>(jakartaViewport);
  const [center, setCenter] = useState<Coordinates>(mockLocations.jakarta);
  const [mapZoom, setMapZoom] = useState(jakartaViewport.zoom);
  const [currentLocation, setCurrentLocation] = useState<Coordinates | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(true);
  const [heatmapUpdating, setHeatmapUpdating] = useState(true);
  const [sites, setSites] = useState(() => generateMockOptimalSites(jakartaViewport));
  const [demandPolygons, setDemandPolygons] = useState(demandHeatmapPolygons);
  const [existingSpkluMarkers, setExistingSpkluMarkers] = useState<LeafletMapMarker[]>([]);
  const [commercialPoiPolygons, setCommercialPoiPolygons] = useState<LeafletPolygonLayer[]>([]);
  const [populationPolygons, setPopulationPolygons] = useState<LeafletPolygonLayer[]>([]);
  const [landUsePolygons, setLandUsePolygons] = useState<LeafletPolygonLayer[]>([]);
  const [layerStatus, setLayerStatus] = useState<string | null>(null);
  const [sheetMode, setSheetMode] = useState<PlannerSheetMode>('layers');
  const [selectedSite, setSelectedSite] = useState<OptimalSite | null>(null);
  const [siteData, setSiteData] = useState<SiteFeasibilityData | null>(null);
  const [siteLoading, setSiteLoading] = useState(false);
  const [siteError, setSiteError] = useState<string | null>(null);
  const [siteRetry, setSiteRetry] = useState(0);
  const [siteTab, setSiteTab] = useState<SiteFeasibilityTab>('feasibility');
  const [financial, setFinancial] = useState<FinancialProjection | null>(null);
  const [financialLoading, setFinancialLoading] = useState(false);
  const [financialError, setFinancialError] = useState<string | null>(null);
  const [financialRetry, setFinancialRetry] = useState(0);
  const selectedSiteId = selectedSite?.id ?? null;
  const financialRequestKey = getSiteFinancialLifecycleKey(selectedSiteId, financialRetry);
  const expandedRef = useRef(expanded);
  const sheetModeRef = useRef(sheetMode);
  const sheetScrollAtTopRef = useRef(true);
  const candidatesRequestRef = useRef<ReturnType<typeof fetchPlannerCandidates> | null>(null);
  const lastMapViewRef = useRef({
    center: mockLocations.jakarta,
    viewport: jakartaViewport,
    zoom: jakartaViewport.zoom
  });

  useEffect(() => {
    expandedRef.current = expanded;
  }, [expanded]);

  useEffect(() => {
    sheetModeRef.current = sheetMode;
  }, [sheetMode]);

  useEffect(() => {
    if (!selectedSiteId) {
      setSiteData(null);
      setSiteLoading(false);
      setSiteError(null);
      return;
    }

    let active = true;
    setSiteLoading(true);
    setSiteError(null);
    void getSiteFeasibility(selectedSiteId).then((data) => {
      if (active) {
        setSiteData(data);
        setSiteLoading(false);
      }
    }).catch((error: unknown) => {
      if (active) {
        setSiteError(plannerErrorCopy(error));
        setSiteLoading(false);
      }
    });
    return () => { active = false; };
  }, [selectedSiteId, siteRetry]);

  useEffect(() => {
    if (!selectedSiteId) {
      setFinancial(null);
      setFinancialError(null);
      setFinancialLoading(false);
      return;
    }

    setFinancial(null);
    setFinancialError(null);

    if (isMockOptimalSiteId(selectedSiteId)) {
      setFinancial(getMockSiteFeasibility(selectedSiteId).financial);
      setFinancialLoading(false);
      return;
    }

    let active = true;
    setFinancial(null);
    setFinancialLoading(true);
    setFinancialError(null);
    void getSiteFinancialProjection(selectedSiteId).then((projection) => {
      if (active) {
        setFinancial(projection);
        setFinancialLoading(false);
      }
    }).catch((error: unknown) => {
      if (active) {
        setFinancialError(plannerRoiErrorCopy(error));
        setFinancialLoading(false);
      }
    });
    return () => { active = false; };
  }, [financialRequestKey]);

  useEffect(() => {
    if (!layers.optimalSites || selectedSite) return;

    let active = true;
    setAnalyzing(true);
    candidatesRequestRef.current ??= fetchPlannerCandidates({ clusters: 15, quantile: 0.9 });
    void candidatesRequestRef.current
      .then((response) => {
        if (!active) return;
        setSites(response.candidates.map(plannerCandidateToOptimalSite));
        setStatus((current) => current?.startsWith('Planning API:') ? null : current);
      })
      .catch((error: unknown) => {
        if (!active) return;
        candidatesRequestRef.current = null;
        setStatus(`Planning API: ${plannerErrorCopy(error)} Showing fallback recommendations.`);
      })
      .finally(() => {
        if (active) setAnalyzing(false);
      });

    return () => { active = false; };
  }, [layers.optimalSites, selectedSite]);

  useEffect(() => {
    if (!layers.demandHeatmap || selectedSite) return;

    const controller = new AbortController();
    setHeatmapUpdating(true);
    const timer = setTimeout(() => {
      void fetchPlannerCells({ ...viewport, limit: 10_000, metric: 'score', signal: controller.signal })
        .then((response) => {
          setDemandPolygons(plannerCellsToPolygons(response));
          setStatus(response.truncated
            ? `Planning API: Showing ${response.cells_returned.toLocaleString()} highest-scoring of ${response.cells_in_viewport.toLocaleString()} cells. Zoom in for full coverage.`
            : null);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setStatus(`Planning API: ${plannerErrorCopy(error)} Keeping the previous heatmap.`);
        })
        .finally(() => {
          if (!controller.signal.aborted) setHeatmapUpdating(false);
        });
    }, 280);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [layers.demandHeatmap, selectedSite, viewport]);

  useEffect(() => {
    if (!layers.existingSpklus || selectedSite) return;

    let active = true;
    const timer = setTimeout(() => {
      void fetchStations({ bbox: plannerViewportBbox(viewport), limit: 1000 })
        .then((response) => {
          if (!active) return;
          setExistingSpkluMarkers(plannerStationsToMarkers(response.items));
          setLayerStatus(response.total > response.items.length
            ? `Existing SPKLUs: showing ${response.items.length.toLocaleString()} of ${response.total.toLocaleString()} stations in view.`
            : null);
        })
        .catch(() => {
          if (active) setLayerStatus('Existing SPKLUs could not be loaded for this area.');
        });
    }, 280);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [layers.existingSpklus, selectedSite, viewport]);

  useEffect(() => {
    if (!layers.commercialPois || selectedSite) return;
    return loadMetricLayer({
      color: '#0891B2',
      idPrefix: 'commercial-poi',
      metric: 'poi_total',
      onError: () => setLayerStatus('Commercial POI density could not be loaded for this area.'),
      onLoad: (polygons) => {
        setCommercialPoiPolygons(polygons);
        setLayerStatus(null);
      },
      viewport
    });
  }, [layers.commercialPois, selectedSite, viewport]);

  useEffect(() => {
    if (!layers.populationDensity || selectedSite) return;
    return loadMetricLayer({
      color: '#7C3AED',
      idPrefix: 'population',
      metric: 'population',
      onError: () => setLayerStatus('Population density could not be loaded for this area.'),
      onLoad: (polygons) => {
        setPopulationPolygons(polygons);
        setLayerStatus(null);
      },
      viewport
    });
  }, [layers.populationDensity, selectedSite, viewport]);

  useEffect(() => {
    if (!layers.landUse || selectedSite) return;

    const controller = new AbortController();
    const timer = setTimeout(() => {
      const metrics: PlannerLandUseMetric[] = ['residential', 'commercial', 'retail', 'industrial'];
      void Promise.all(metrics.map(async (metric) => [
        metric,
        await fetchPlannerCells({ ...viewport, limit: 10_000, metric, signal: controller.signal })
      ] as const))
        .then((responses) => {
          setLandUsePolygons(plannerLandUseToPolygons(Object.fromEntries(responses)));
          setLayerStatus(null);
        })
        .catch(() => {
          if (!controller.signal.aborted) setLayerStatus('Land-use coverage could not be loaded for this area.');
        });
    }, 280);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [layers.landUse, selectedSite, viewport]);

  const animateNext = useCallback(() => {
    LayoutAnimation.configureNext(sheetAnimation);
  }, []);

  const setSheetExpanded = useCallback((nextExpanded: boolean) => {
    animateNext();
    setExpanded(nextExpanded);
  }, [animateNext]);

  const closeSiteFeasibility = useCallback(() => {
    const previousMapView = lastMapViewRef.current;
    sheetModeRef.current = 'layers';
    animateNext();
    setSelectedSite(null);
    setSiteData(null);
    setSiteError(null);
    setSiteTab('feasibility');
    setFinancial(null);
    setFinancialError(null);
    setFinancialLoading(false);
    setSheetMode('layers');
    setExpanded(false);
    setCenter(previousMapView.center);
    setMapZoom(previousMapView.zoom);
    setViewport(previousMapView.viewport);
  }, [animateNext]);

  const openLayers = useCallback(() => {
    sheetModeRef.current = 'layers';
    animateNext();
    setSelectedSite(null);
    setSiteData(null);
    setSiteError(null);
    setFinancial(null);
    setFinancialError(null);
    setFinancialLoading(false);
    setSheetMode('layers');
    setExpanded(true);
  }, [animateNext]);

  const drawerPanResponder = useMemo(
    () => PanResponder.create({
      onMoveShouldSetPanResponder: (_, gestureState) => {
        const isSwipingDown = gestureState.dy > 8;
        const isSwipingUp = gestureState.dy < -8;

        if (expandedRef.current) {
          return isSwipingDown && sheetScrollAtTopRef.current;
        }

        return isSwipingDown || isSwipingUp;
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > 18 && sheetModeRef.current === 'site-feasibility') {
          setSheetExpanded(false);
        } else if (gestureState.dy > 18 && expandedRef.current) {
          setSheetExpanded(false);
        } else if (gestureState.dy < -18 && !expandedRef.current) {
          setSheetExpanded(true);
        }
      }
    }),
    [setSheetExpanded]
  );

  const onViewportChange = useCallback((next: MapViewport) => {
    setViewport(next);
    if (sheetModeRef.current === 'layers') {
      lastMapViewRef.current = {
        center: next.center ?? {
          latitude: (next.north + next.south) / 2,
          longitude: (next.east + next.west) / 2
        },
        viewport: next,
        zoom: next.zoom
      };
    }
  }, []);

  const onMarkerPress = useCallback((markerId: string) => {
    const site = resolveOptimalSite(sites, markerId);
    if (!site) return;

    // Freeze the return viewport synchronously. Leaflet may auto-pan an open
    // marker popup before React commits the sheet-mode state; waiting for the
    // effect would accidentally save that detail movement as the user's view.
    sheetModeRef.current = 'site-feasibility';
    animateNext();
    setSelectedSite(site);
    setSiteError(null);
    setSiteTab('feasibility');
    setFinancial(null);
    setFinancialError(null);
    setFinancialLoading(false);
    setSheetMode('site-feasibility');
    setExpanded(true);
  }, [animateNext, sites]);

  const submitSearch = () => {
    const match = mockLocations[query.trim().toLowerCase()];

    if (match) {
      setCenter(match);
      setStatus(null);
    } else if (query.trim()) {
      setStatus('No mock location found. Map unchanged.');
    }
  };

  const locate = async () => {
    setStatus(null);
    const result = await getUserLocation({ requestPermission: true });

    if (result.coordinates) {
      setCurrentLocation(result.coordinates);
      setCenter(result.coordinates);
    } else {
      setStatus('Location unavailable. Staying in Jakarta.');
    }
  };

  const markers = useMemo(
    () => plannerMarkers(layers, sites, existingSpkluMarkers),
    [existingSpkluMarkers, layers, sites]
  );
  const polygons = useMemo(() => plannerPolygons(layers, {
    commercialPois: commercialPoiPolygons,
    demandHeatmap: demandPolygons,
    landUse: landUsePolygons,
    populationDensity: populationPolygons
  }), [commercialPoiPolygons, demandPolygons, landUsePolygons, layers, populationPolygons]);
  const expandedSheetHeight = getExpandedSheetHeight(height, topInset, bottomOffset);
  const sheetHeight = expanded ? expandedSheetHeight : collapsedSheetHeight;
  const expandedSiteSheetHeight = getSiteExpandedSheetHeight(height, width, topInset, bottomOffset);
  const siteSheetHeight = expanded ? expandedSiteSheetHeight : collapsedSiteSheetHeight;

  useEffect(() => {
    if (sheetMode !== 'site-feasibility' || !selectedSite) return;

    setCenter(getDrawerAwareMapCenter(
      selectedSite,
      siteDetailZoom,
      bottomOffset + siteSheetHeight
    ));
    setMapZoom(siteDetailZoom);
  }, [bottomOffset, selectedSite, sheetMode, siteSheetHeight]);

  return (
    <View style={mapStyles.page}>
      <LeafletMap
        center={center}
        currentLocation={currentLocation}
        markers={markers}
        onMarkerPress={onMarkerPress}
        onViewportChange={onViewportChange}
        polygonLayers={polygons}
        selectedMarkerId={selectedSite?.id ?? null}
        zoom={mapZoom}
      />

      <View style={[mapStyles.searchBar, { top: 24 + topInset }]}>
        <View style={mapStyles.searchIcon}>
          <SvgAssetIcon color="#6B7A7B" height={18} name="search" svg={searchIcon} width={18} />
        </View>
        <TextInput
          accessibilityLabel="Search location"
          onChangeText={setQuery}
          onSubmitEditing={submitSearch}
          placeholder="Search location..."
          placeholderTextColor="#819097"
          returnKeyType="search"
          style={mapStyles.searchInput}
          value={query}
        />
        <Pressable
          accessibilityLabel="Open map layers"
          accessibilityRole="button"
          onPress={openLayers}
          style={mapStyles.filterIcon}
        >
          <SvgAssetIcon color="#005F64" height={18} name="filter" svg={filterSettingIcon} width={18} />
        </Pressable>
      </View>

      <View style={[plannerStyles.mapControls, { top: topInset + 104 }]}>
        <MapControlButton
          accessibilityLabel="Use current location"
          icon={currentLocationIcon}
          onPress={() => void locate()}
        />
        <MapControlButton
          accessibilityLabel="Open map layers"
          icon={layersIcon}
          onPress={openLayers}
          primary
        />
      </View>

      {status || layerStatus ? (
        <Text accessibilityLiveRegion="polite" style={[plannerStyles.status, { top: topInset + 168 }]}>
          {layerStatus ?? status}
        </Text>
      ) : null}

      {analyzing && layers.optimalSites ? (
        <View style={[plannerStyles.analysis, { top: topInset + 168 }]}>
          <ActivityIndicator color="#006973" size="small" />
          <Text style={plannerStyles.analysisText}>Analyzing visible area...</Text>
        </View>
      ) : null}

      {heatmapUpdating && layers.demandHeatmap && !analyzing ? (
        <View style={[plannerStyles.analysis, { top: topInset + 168 }]}>
          <ActivityIndicator color="#006973" size="small" />
          <Text style={plannerStyles.analysisText}>Updating analysis...</Text>
        </View>
      ) : null}

      {layers.demandHeatmap && sheetMode === 'layers' && !expanded ? (
        <DemandHeatmapLegend bottom={bottomOffset + collapsedSheetHeight + 12} />
      ) : null}

      {sheetMode === 'layers' ? (
        <View
          style={[
            mapStyles.sheet,
            plannerStyles.sheet,
            getSheetStateStyle(sheetHeight),
            { bottom: bottomOffset }
          ]}
          {...drawerPanResponder.panHandlers}
        >
        <Pressable
          accessibilityLabel={expanded ? 'Collapse Map Layers' : 'Expand Map Layers'}
          accessibilityRole="button"
          accessibilityState={{ expanded }}
          onPress={() => setSheetExpanded(!expanded)}
          style={mapStyles.drawerHandleWrap}
        >
          <View style={mapStyles.drawerHandle} />
        </Pressable>

        <View style={mapStyles.drawerBody}>
          <View style={[mapStyles.sheetHeader, plannerStyles.sheetHeader]}>
            <View>
              <Text style={mapStyles.sheetTitle}>Map Layers</Text>
              <Text style={plannerStyles.sheetSubtitle}>Customize map views</Text>
            </View>

            {expanded ? (
              <Pressable
                accessibilityLabel="Collapse map layers"
                accessibilityRole="button"
                onPress={() => setSheetExpanded(false)}
                style={mapStyles.closeButton}
              >
                <SvgAssetIcon color="#191C1D" height={14} name="close" svg={closeButtonIcon} width={14} />
              </Pressable>
            ) : (
              <Pressable
                accessibilityLabel="Expand map layers"
                accessibilityRole="button"
                onPress={() => setSheetExpanded(true)}
                style={mapStyles.filterButton}
              >
                <SvgAssetIcon color="#4C5960" height={16} name="filter" svg={filterSettingIcon} width={16} />
                <Text style={mapStyles.filterButtonText}>Layers</Text>
              </Pressable>
            )}
          </View>

          <ScrollView
            contentContainerStyle={plannerStyles.layerList}
            onScroll={(event) => {
              sheetScrollAtTopRef.current = event.nativeEvent.contentOffset.y <= 0;
            }}
            scrollEnabled={expanded}
            scrollEventThrottle={16}
            showsVerticalScrollIndicator={false}
            style={[mapStyles.expandedContent, getExpandedContentStateStyle(expanded)]}
          >
            {layerRows.map((row) => (
              <LayerToggleRow
                key={row.key}
                enabled={layers[row.key]}
                row={row}
                onToggle={() => setLayers((current) => ({ ...current, [row.key]: !current[row.key] }))}
              />
            ))}
          </ScrollView>
        </View>
        </View>
      ) : (
        <SiteFeasibilitySheet
          activeTab={siteTab}
          bottom={bottomOffset}
          data={siteData}
          error={siteError}
          expanded={expanded}
          financial={financial}
          financialError={financialError}
          financialLoading={financialLoading}
          height={siteSheetHeight}
          loading={siteLoading}
          onClose={closeSiteFeasibility}
          onFinancialRetry={() => setFinancialRetry((current) => current + 1)}
          onScrollTopChange={(atTop) => { sheetScrollAtTopRef.current = atTop; }}
          onTabChange={setSiteTab}
          onToggleExpanded={() => setSheetExpanded(!expanded)}
          onRetry={() => setSiteRetry((current) => current + 1)}
          panHandlers={drawerPanResponder.panHandlers}
        />
      )}
    </View>
  );
}

function MapControlButton({
  accessibilityLabel,
  icon,
  onPress,
  primary = false
}: {
  accessibilityLabel: string;
  icon: string;
  onPress: () => void;
  primary?: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      onPress={onPress}
      style={[plannerStyles.mapControlButton, primary && plannerStyles.mapControlButtonPrimary]}
    >
      <SvgAssetIcon height={22} svg={icon} width={22} />
    </Pressable>
  );
}

function DemandHeatmapLegend({ bottom }: { bottom: number }) {
  return (
    <View style={[plannerStyles.legend, { bottom }]}>
      {(['high', 'moderate', 'low'] as const).map((priority) => (
        <View key={priority} style={plannerStyles.legendRow}>
          <View
            style={[
              plannerStyles.legendDot,
              { backgroundColor: priority === 'high' ? '#EF4444' : priority === 'moderate' ? '#F59E0B' : '#10B981' }
            ]}
          />
          <Text style={plannerStyles.legendText}>{prioritySemanticCategory(priority)}</Text>
        </View>
      ))}
    </View>
  );
}

function LayerToggleRow({ enabled, onToggle, row }: { enabled: boolean; onToggle: () => void; row: LayerRow }) {
  return (
    <View style={plannerStyles.layerRow}>
      <View style={[plannerStyles.layerIcon, enabled && plannerStyles.layerIconEnabled]}>
        <SvgAssetIcon height={20} svg={row.icon} width={20} />
      </View>
      <View style={plannerStyles.layerCopy}>
        <Text style={plannerStyles.layerTitle}>{row.title}</Text>
        <Text style={[plannerStyles.layerSubtitle, enabled && plannerStyles.layerSubtitleEnabled]}>{row.subtitle}</Text>
        {row.key === 'optimalSites' ? (
          <Text style={plannerStyles.helperText}>
            Recommended candidate locations based on demand, infrastructure gaps, population, POIs, and land use.
          </Text>
        ) : null}
      </View>
      <Pressable
        accessibilityLabel={`Toggle ${row.title}`}
        accessibilityRole="switch"
        accessibilityState={{ checked: enabled }}
        onPress={onToggle}
        style={[plannerStyles.toggle, enabled && plannerStyles.toggleEnabled]}
      >
        <View style={[plannerStyles.toggleKnob, enabled && plannerStyles.toggleKnobEnabled]} />
      </Pressable>
    </View>
  );
}

function getExpandedSheetHeight(screenHeight: number, topInset: number, bottomOffset: number) {
  const searchBarBottom = topInset + 24 + 66 + 12;
  const availableHeight = screenHeight - bottomOffset - searchBarBottom;
  const viewportProportion = (screenHeight - bottomOffset) * 0.68;
  return Math.max(360, Math.floor(Math.min(600, availableHeight, viewportProportion)));
}

function getSiteExpandedSheetHeight(screenHeight: number, screenWidth: number, topInset: number, bottomOffset: number) {
  const usableHeight = screenHeight - bottomOffset;
  const roomBelowSearch = usableHeight - (topInset + 102);
  const targetHeight = screenWidth < 768 ? roomBelowSearch : Math.min(720, usableHeight * 0.8, roomBelowSearch);
  return Math.max(collapsedSiteSheetHeight, Math.floor(targetHeight));
}

function plannerErrorCopy(error: unknown) {
  if (error instanceof PlannerApiError) return error.message;
  if (error instanceof TypeError) return 'Unable to reach the backend.';
  return 'Planning data could not be loaded.';
}

function plannerRoiErrorCopy(error: unknown) {
  if (error instanceof PlannerApiError) {
    if (error.status === 401) return 'Session expired. Sign in again.';
    if (error.status === 403) return 'Business Planner access is required.';
    if (error.status === 404) return 'This planning cell is no longer available.';
    if (error.status === 422) return error.message;
    return error.message;
  }
  if (error instanceof TypeError) return 'Unable to reach the backend.';
  return 'Financial projection could not be calculated.';
}

function loadMetricLayer({
  color,
  idPrefix,
  metric,
  onError,
  onLoad,
  viewport
}: {
  color: string;
  idPrefix: string;
  metric: string;
  onError: () => void;
  onLoad: (polygons: LeafletPolygonLayer[]) => void;
  viewport: MapViewport;
}) {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    void fetchPlannerCells({ ...viewport, limit: 10_000, metric, signal: controller.signal })
      .then((response) => onLoad(plannerCellsToMetricPolygons(response, color, idPrefix)))
      .catch(() => {
        if (!controller.signal.aborted) onError();
      });
  }, 280);

  return () => {
    clearTimeout(timer);
    controller.abort();
  };
}

type WebTransitionStyle = ViewStyle & {
  transitionDuration?: string;
  transitionProperty?: string;
  transitionTimingFunction?: string;
};

function getSheetStateStyle(height: number): WebTransitionStyle {
  return {
    height,
    ...(Platform.OS === 'web'
      ? {
          transitionDuration: '240ms',
          transitionProperty: 'height',
          transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)'
        }
      : {})
  };
}

function getExpandedContentStateStyle(expanded: boolean): WebTransitionStyle {
  return {
    opacity: expanded ? 1 : 0,
    pointerEvents: expanded ? 'auto' : 'none',
    transform: [{ translateY: expanded ? 0 : 16 }],
    ...(Platform.OS === 'web'
      ? {
          transitionDuration: '180ms',
          transitionProperty: 'opacity, transform',
          transitionTimingFunction: 'ease-out'
        }
      : {})
  };
}

const plannerStyles = StyleSheet.create({
  mapControls: {
    gap: 12,
    position: 'absolute',
    right: 22,
    zIndex: 9999
  },
  mapControlButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 24,
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.14)',
    height: 48,
    justifyContent: 'center',
    width: 48
  },
  mapControlButtonPrimary: {
    backgroundColor: '#007D8C'
  },
  status: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 8,
    color: '#4B5563',
    left: 22,
    padding: 8,
    position: 'absolute',
    right: 82,
    textAlign: 'center',
    zIndex: 9999
  },
  analysis: {
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 16,
    flexDirection: 'row',
    gap: 8,
    left: 22,
    paddingHorizontal: 12,
    paddingVertical: 8,
    position: 'absolute',
    zIndex: 9999
  },
  analysisText: {
    color: '#355055',
    fontSize: 12,
    fontWeight: '700'
  },
  legend: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 10,
    boxShadow: '0 3px 10px rgba(21,35,38,0.14)',
    gap: 7,
    left: 14,
    padding: 10,
    position: 'absolute',
    zIndex: 9999
  },
  legendRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8
  },
  legendDot: {
    borderRadius: 5,
    height: 10,
    width: 10
  },
  legendText: {
    color: '#364246',
    fontSize: 12,
    fontWeight: '600'
  },
  sheet: {
    paddingBottom: 20
  },
  sheetHeader: {
    marginBottom: 0
  },
  sheetSubtitle: {
    color: '#5A6870',
    fontSize: 14,
    marginTop: 2
  },
  layerList: {
    paddingBottom: 10,
    paddingTop: 12
  },
  layerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    minHeight: 62,
    paddingVertical: 6
  },
  layerIcon: {
    alignItems: 'center',
    backgroundColor: '#EEF1FF',
    borderRadius: 20,
    height: 40,
    justifyContent: 'center',
    marginRight: 12,
    width: 40
  },
  layerIconEnabled: {
    backgroundColor: '#D5F3FA'
  },
  layerCopy: {
    flex: 1,
    paddingRight: 10
  },
  layerTitle: {
    color: '#1F2937',
    fontSize: 14,
    fontWeight: '800'
  },
  layerSubtitle: {
    color: '#71808A',
    fontFamily: 'monospace',
    fontSize: 11,
    marginTop: 2
  },
  layerSubtitleEnabled: {
    color: '#0077A7'
  },
  helperText: {
    color: '#607077',
    fontSize: 10,
    lineHeight: 13,
    marginTop: 3
  },
  toggle: {
    backgroundColor: '#DBE4FA',
    borderColor: '#B5C1D8',
    borderRadius: 12,
    borderWidth: 1,
    height: 24,
    justifyContent: 'center',
    paddingHorizontal: 2,
    width: 42
  },
  toggleEnabled: {
    backgroundColor: '#007D8C',
    borderColor: '#007D8C'
  },
  toggleKnob: {
    backgroundColor: '#718096',
    borderRadius: 9,
    height: 18,
    width: 18
  },
  toggleKnobEnabled: {
    alignSelf: 'flex-end',
    backgroundColor: '#FFFFFF'
  }
});
