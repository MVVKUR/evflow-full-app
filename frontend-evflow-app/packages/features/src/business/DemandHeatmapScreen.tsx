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
import { driverMapStyles as mapStyles, LeafletMap, type MapViewport } from '@evflow/ui';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { closeButtonIcon, filterSettingIcon, searchIcon } from '../ev_driver/components/driverMapIcons';
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
  generateMockOptimalSites,
  jakartaViewport,
  plannerMarkers,
  plannerPolygons,
  prioritySemanticCategory,
  type PlannerLayerKey,
  type PlannerLayerState
} from './demandHeatmap';

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

type LayerRow = {
  icon: string;
  key: PlannerLayerKey;
  subtitle: string;
  title: string;
};

const collapsedSheetHeight = 104;
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
  { key: 'commercialPois', icon: commercialPoiIcon, title: 'Commercial POIs', subtitle: 'Activity Hubs' },
  { key: 'populationDensity', icon: populationIcon, title: 'Population Density', subtitle: 'Census Data' },
  { key: 'landUse', icon: landUseIcon, title: 'Land Use', subtitle: 'Grid & Land Use' }
];

export function DemandHeatmapScreen({ bottomOffset = 0, topInset = 0 }: DemandHeatmapScreenProps) {
  const { height } = useWindowDimensions();
  const [layers, setLayers] = useState<PlannerLayerState>(defaultPlannerLayers);
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [viewport, setViewport] = useState<MapViewport>(jakartaViewport);
  const [center, setCenter] = useState<Coordinates>(mockLocations.jakarta);
  const [currentLocation, setCurrentLocation] = useState<Coordinates | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(true);
  const [sites, setSites] = useState(() => generateMockOptimalSites(jakartaViewport));
  const expandedRef = useRef(expanded);
  const sheetScrollAtTopRef = useRef(true);

  useEffect(() => {
    expandedRef.current = expanded;
  }, [expanded]);

  useEffect(() => {
    if (!layers.optimalSites) return;

    setAnalyzing(true);
    const timer = setTimeout(() => {
      setSites(generateMockOptimalSites(viewport));
      setAnalyzing(false);
    }, 420);

    return () => clearTimeout(timer);
  }, [layers.optimalSites, viewport]);

  const animateNext = useCallback(() => {
    LayoutAnimation.configureNext(sheetAnimation);
  }, []);

  const setSheetExpanded = useCallback((nextExpanded: boolean) => {
    animateNext();
    setExpanded(nextExpanded);
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
        if (gestureState.dy > 18 && expandedRef.current) {
          setSheetExpanded(false);
        } else if (gestureState.dy < -18 && !expandedRef.current) {
          setSheetExpanded(true);
        }
      }
    }),
    [setSheetExpanded]
  );

  const onViewportChange = useCallback((next: MapViewport) => setViewport(next), []);

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

  const markers = useMemo(() => plannerMarkers(layers, sites), [layers, sites]);
  const polygons = useMemo(() => plannerPolygons(layers), [layers]);
  const expandedSheetHeight = getExpandedSheetHeight(height, topInset, bottomOffset);
  const sheetHeight = expanded ? expandedSheetHeight : collapsedSheetHeight;

  return (
    <View style={mapStyles.page}>
      <LeafletMap
        center={center}
        currentLocation={currentLocation}
        markers={markers}
        onViewportChange={onViewportChange}
        polygonLayers={polygons}
        zoom={viewport.zoom}
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
          onPress={() => setSheetExpanded(true)}
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
          onPress={() => setSheetExpanded(true)}
          primary
        />
      </View>

      {status ? <Text accessibilityLiveRegion="polite" style={[plannerStyles.status, { top: topInset + 168 }]}>{status}</Text> : null}

      {analyzing && layers.optimalSites ? (
        <View style={[plannerStyles.analysis, { top: topInset + 168 }]}>
          <ActivityIndicator color="#006973" size="small" />
          <Text style={plannerStyles.analysisText}>Analyzing visible area...</Text>
        </View>
      ) : null}

      {layers.demandHeatmap && !expanded ? (
        <DemandHeatmapLegend bottom={bottomOffset + collapsedSheetHeight + 12} />
      ) : null}

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
