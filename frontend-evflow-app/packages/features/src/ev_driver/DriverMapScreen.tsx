import { useEffect, useMemo, useRef, useState } from 'react';
import { LayoutAnimation, PanResponder, Platform, Pressable, ScrollView, Text, TextInput, UIManager, View, useWindowDimensions, type ViewStyle } from 'react-native';
import { colors, driverMapStyles as styles, LeafletMap } from '@evflow/ui';
import { fetchConnectorTypes, fetchNearbyStations, fetchSpeedTiers, fetchStations, type ConnectorTypeApiItem, type SpeedTierApiItem, type StationApiItem, type StationConnectorApiItem, type StationConnectorTypeApiItem } from '@evflow/shared';
import { getUserLocation, type LocationPermissionStatus } from './utils/location';
import { FilterCategory, type FilterOption } from './components/FilterCategory';
import { locationPinSvg } from './components/locationPinSvg';
import { PlatformSlider } from '../shared/PlatformSlider';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { closeButtonIcon, filterSettingIcon, lightningIcon, searchIcon } from './components/driverMapIcons';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

type DriverMapScreenProps = {
  bottomOffset?: number;
  topInset?: number;
};

type DrawerMode = 'filter' | 'results' | 'detail';

type ConnectorInfo = {
  count: number;
  powerKw: number | null;
  speedTier: string | null;
  type: string;
};

type Station = {
  id: string;
  address: string;
  connectors: ConnectorInfo[];
  city: string | null;
  distanceKm?: number;
  latitude: number;
  longitude: number;
  name: string;
  province: string | null;
};

type Coordinates = {
  latitude: number;
  longitude: number;
};

type MapViewState = {
  center: Coordinates;
  zoom: number;
};

const defaultStationLimit = 1000;
const defaultDistanceKm = 8;
const distanceOptions = [3, 5, 8, 10] as const;
const defaultMapView: MapViewState = {
  center: {
    latitude: -6.1754,
    longitude: 106.8272
  },
  zoom: 13
};
export function DriverMapScreen({ bottomOffset = 0, topInset = 0 }: DriverMapScreenProps) {
  const { height, width } = useWindowDimensions();
  const [expanded, setExpanded] = useState(false);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('results');
  const [selectedStation, setSelectedStation] = useState<Station | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [connectorTypes, setConnectorTypes] = useState<string[]>([]);
  const [chargingSpeeds, setChargingSpeeds] = useState<string[]>([]);
  const [appliedConnectorTypes, setAppliedConnectorTypes] = useState<ConnectorTypeApiItem[]>([]);
  const [appliedChargingSpeeds, setAppliedChargingSpeeds] = useState<SpeedTierApiItem[]>([]);
  const [distanceKm, setDistanceKm] = useState(defaultDistanceKm);
  const [appliedDistanceKm, setAppliedDistanceKm] = useState(defaultDistanceKm);
  const [connectorTypeOptions, setConnectorTypeOptions] = useState<ConnectorTypeApiItem[]>([]);
  const [speedTierOptions, setSpeedTierOptions] = useState<SpeedTierApiItem[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [stationsError, setStationsError] = useState<string | null>(null);
  const [stationsLoading, setStationsLoading] = useState(true);
  const [userLocation, setUserLocation] = useState<Coordinates | null>(null);
  const [locationPermissionStatus, setLocationPermissionStatus] = useState<LocationPermissionStatus>('undetermined');
  const [locationPermissionLoading, setLocationPermissionLoading] = useState(false);
  const [locationResolved, setLocationResolved] = useState(false);
  const [mapView, setMapView] = useState<MapViewState>(defaultMapView);
  const previousMapViewRef = useRef<MapViewState>(defaultMapView);
  const previousResultsExpandedRef = useRef(false);
  const requestedLocationPermissionRef = useRef(false);
  const selectedStationRef = useRef<Station | null>(selectedStation);
  const expandedRef = useRef(expanded);
  const searchQueryRef = useRef(searchQuery);
  const searchRestoreStateRef = useRef<{ drawerMode: DrawerMode; expanded: boolean; selectedStation: Station | null } | null>(null);
  const searchActive = searchFocused || searchQuery.trim().length > 0;
  useEffect(() => {
    selectedStationRef.current = selectedStation;
  }, [selectedStation]);

  useEffect(() => {
    expandedRef.current = expanded;
  }, [expanded]);

  const isScrolledToTopRef = useRef(true);

  const handleScroll = (e: any) => {
    isScrolledToTopRef.current = e.nativeEvent.contentOffset.y <= 0;
  };

  const drawerPanResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gestureState) => {
          if (searchActive) {
            return false;
          }

          const isSwipingDown = gestureState.dy > 8;
          const isSwipingUp = gestureState.dy < -8;

          if (expandedRef.current) {
            if (isSwipingDown && isScrolledToTopRef.current) {
              return true;
            }
            return false;
          }

          return isSwipingDown || isSwipingUp;
        },
        onPanResponderRelease: (_, gestureState) => {
          if (searchActive) {
            return;
          }

          updateSheetSizeFromDelta(gestureState.dy, setExpanded);
        }
      }),
    [searchActive]
  );

  const animateNext = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
  };

  const resolveUserLocation = async (requestPermission = false) => {
    if (requestPermission) {
      requestedLocationPermissionRef.current = true;
    }

    setLocationPermissionLoading(true);

    const locationResult = await getUserLocation({ requestPermission });

    setLocationPermissionStatus(locationResult.status);
    setUserLocation(locationResult.coordinates);

    if (locationResult.coordinates && !selectedStationRef.current) {
      const userMapView = {
        center: locationResult.coordinates,
        zoom: 14
      };
      setMapView(userMapView);
      previousMapViewRef.current = userMapView;
      setAppliedDistanceKm(distanceKm);
    }

    setLocationResolved(true);
    setLocationPermissionLoading(false);
  };

  useEffect(() => {
    let mounted = true;

    (async () => {
      const locationResult = await getUserLocation();

      if (!mounted) {
        return;
      }

      setLocationPermissionStatus(locationResult.status);
      setUserLocation(locationResult.coordinates);

      if (locationResult.coordinates && !selectedStationRef.current) {
        const userMapView = {
          center: locationResult.coordinates,
          zoom: 14
        };
        setMapView(userMapView);
        previousMapViewRef.current = userMapView;
      }

      if (
        Platform.OS !== 'web' &&
        !locationResult.coordinates &&
        locationResult.status === 'undetermined' &&
        !requestedLocationPermissionRef.current
      ) {
        await resolveUserLocation(true);
        return;
      }

      setLocationResolved(true);
    })();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadFilters() {
      try {
        const [nextConnectorTypes, nextSpeedTiers] = await Promise.all([
          fetchConnectorTypes(),
          fetchSpeedTiers()
        ]);
        if (mounted) {
          setConnectorTypeOptions(nextConnectorTypes);
          setSpeedTierOptions(nextSpeedTiers);
        }
      } catch (error) {
        // ignore filter errors or handle if needed
      }
    }

    loadFilters();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!locationResolved) {
      return;
    }

    let mounted = true;

    async function loadStations() {
      setStationsLoading(true);
      setStationsError(null);

      try {
        const nextStations = await loadSpkluStations({
          chargingSpeeds: appliedChargingSpeeds,
          connectorTypes: appliedConnectorTypes,
          distanceKm: appliedDistanceKm,
          userLocation
        });

        if (mounted) {
          setStations(nextStations);
        }
      } catch (error) {
        if (mounted) {
          setStationsError(error instanceof Error ? error.message : 'Unable to load nearby SPKLU stations.');
        }
      } finally {
        if (mounted) {
          setStationsLoading(false);
        }
      }
    }

    loadStations();

    return () => {
      mounted = false;
    };
  }, [appliedChargingSpeeds, appliedConnectorTypes, appliedDistanceKm, locationResolved, userLocation]);

  const connectorFilterOptions = useMemo<FilterOption[]>(
    () =>
      connectorTypeOptions.map((connector) => ({
        key: connector.name,
        label: connector.name
      })),
    [connectorTypeOptions]
  );
  const speedFilterOptions = useMemo<FilterOption[]>(
    () =>
      speedTierOptions.map((speedTier) => ({
        key: speedTier.id,
        label: speedTier.label,
        description: formatPowerRange(speedTier)
      })),
    [speedTierOptions]
  );

  const filteredStations = useMemo(() => filterStationsByKeyword(stations, searchQuery), [searchQuery, stations]);
  const visibleStations = searchQuery.trim() ? filteredStations : stations;
  const stationMarkers = useMemo(
    () =>
      visibleStations.map((station) => ({
        id: station.id,
        label: station.name,
        latitude: station.latitude,
        longitude: station.longitude
      })),
    [visibleStations]
  );
  const stationMarkerIcon = useMemo(() => colorSvg(locationPinSvg, colors.text), []);
  const detailSheetHeight = width < 768 ? Math.floor((height - bottomOffset) / 2) : undefined;
  const filterSheetHeight = width < 768 ? getMobileFilterSheetHeight(height, topInset, bottomOffset) : undefined;
  const searchSheetHeight = getSearchResultsSheetHeight(height, topInset, bottomOffset);

  const activateSearchResults = () => {
    if (!searchRestoreStateRef.current) {
      searchRestoreStateRef.current = { drawerMode, expanded, selectedStation };
    }

    animateNext();
    setSearchFocused(true);
    setSelectedStation(null);
    setDrawerMode('results');
    setExpanded(true);
  };

  const restoreAfterSearchIfEmpty = () => {
    setSearchFocused(false);

    if (searchQueryRef.current.trim()) {
      return;
    }

    const restoreState = searchRestoreStateRef.current;
    searchRestoreStateRef.current = null;

    if (!restoreState) {
      return;
    }

    animateNext();
    setSelectedStation(restoreState.selectedStation);
    setDrawerMode(restoreState.drawerMode);
    setExpanded(restoreState.expanded);
  };

  const handleSearchChange = (value: string) => {
    searchQueryRef.current = value;
    setSearchQuery(value);

    if (value.trim()) {
      activateSearchResults();
      return;
    }

    if (!searchFocused) {
      restoreAfterSearchIfEmpty();
    }
  };

  const openStationDetail = (station: Station) => {
    searchRestoreStateRef.current = null;
    setSearchFocused(false);
    if (!selectedStation) {
      previousMapViewRef.current = mapView;
      previousResultsExpandedRef.current = expanded;
    }

    animateNext();
    setSelectedStation(station);
    const latOffset = width < 768 ? 0.008 : 0;

    setMapView({
      center: {
        latitude: station.latitude - latOffset,
        longitude: station.longitude
      },
      zoom: 15
    });
    setDrawerMode('detail');
    setExpanded(true);
  };
  const closeStationDetail = () => {
    animateNext();
    setSelectedStation(null);
    setMapView(previousMapViewRef.current);
    setDrawerMode('results');
    setExpanded(previousResultsExpandedRef.current);
  };

  return (
    <View style={styles.page}>
      <LeafletMap
        center={mapView.center}
        currentLocation={userLocation}
        markerIconSvg={stationMarkerIcon}
        markers={stationMarkers}
        radiusKm={userLocation ? (drawerMode === 'filter' ? distanceKm : appliedDistanceKm) : null}
        onMarkerPress={(stationId) => {
          const station = stations.find((currentStation) => currentStation.id === stationId);

          if (!station) {
            return;
          }

          openStationDetail(station);
        }}
        showCurrentLocationPinpoint={Boolean(userLocation)}
        zoom={mapView.zoom}
      />

      <View style={[styles.searchBar, { top: 24 + topInset }]}>
        <View style={styles.searchIcon}>
          <SvgAssetIcon color="#6B7A7B" height={18} name="search" svg={searchIcon} width={18} />
        </View>
        <TextInput
          accessibilityLabel="Search location"
          onBlur={restoreAfterSearchIfEmpty}
          onChangeText={handleSearchChange}
          onFocus={activateSearchResults}
          placeholder="Search location..."
          placeholderTextColor="#819097"
          style={styles.searchInput}
          value={searchQuery}
        />
        <Pressable
          accessibilityLabel="Open filters"
          accessibilityRole="button"
          onPress={() => {
            animateNext();
            setDrawerMode('filter');
            setExpanded(true);
          }}
          style={styles.filterIcon}
        >
          <SvgAssetIcon color="#005F64" height={18} name="filter" svg={filterSettingIcon} width={18} />
        </Pressable>
      </View>

        <View style={[styles.sheet, getSheetStateStyle(drawerMode, expanded, detailSheetHeight, filterSheetHeight, searchSheetHeight), { bottom: bottomOffset }]} {...drawerPanResponder.panHandlers}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ expanded }}
            onPress={() => {
              if (searchActive) {
                setExpanded(true);
                return;
              }

              animateNext();
              setExpanded((current) => !current);
            }}
            style={styles.drawerHandleWrap}
          >
            <View style={styles.drawerHandle} />
          </Pressable>

          {drawerMode === 'filter' ? (
            <FilterDrawer
              chargingSpeeds={chargingSpeeds}
              chargingSpeedOptions={speedFilterOptions}
              connectorTypes={connectorTypes}
              connectorTypeOptions={connectorFilterOptions}
              distanceKm={distanceKm}
              expanded={expanded}
              onApply={() => {
                animateNext();
                setAppliedChargingSpeeds(getSelectedSpeedTiers(chargingSpeeds, speedTierOptions));
                setAppliedConnectorTypes(getSelectedConnectorTypes(connectorTypes, connectorTypeOptions));
                setAppliedDistanceKm(distanceKm);
                setDrawerMode('results');
                setSelectedStation(null);
                setExpanded(true);
              }}
              onClose={() => {
                animateNext();
                setDrawerMode('results');
                setExpanded(false);
              }}
              onReset={() => {
                resetFilters(setConnectorTypes, setChargingSpeeds, setDistanceKm);
                animateNext();
                setAppliedChargingSpeeds([]);
                setAppliedConnectorTypes([]);
                setAppliedDistanceKm(defaultDistanceKm);
                setDrawerMode('results');
                setSelectedStation(null);
                setExpanded(true);
              }}
              onSelectDistance={setDistanceKm}
              onToggleChargingSpeed={(key) => toggleSelected(key, chargingSpeeds, setChargingSpeeds)}
              onToggleConnectorType={(key) => toggleSelected(key, connectorTypes, setConnectorTypes)}
              onScroll={handleScroll}
            />
          ) : null}

          {drawerMode === 'results' ? (
            <ResultsDrawer
              expanded={expanded}
              filteredBySearch={searchQuery.trim().length > 0}
              loading={stationsLoading}
              onFilter={() => {
                animateNext();
                setDrawerMode('filter');
                setExpanded(true);
              }}
              onSelectStation={(station) => {
                openStationDetail(station);
              }}
              onScroll={handleScroll}
              stations={filteredStations}
              stationsError={stationsError}
              locationPermissionStatus={locationPermissionStatus}
              locationPermissionLoading={locationPermissionLoading}
              hasUserLocation={Boolean(userLocation)}
              onRequestLocation={() => resolveUserLocation(true)}
            />
          ) : null}

          {drawerMode === 'detail' && selectedStation ? (
            <StationDetailDrawer
              expanded={expanded}
              onScroll={handleScroll}
              station={selectedStation}
              onClose={closeStationDetail}
            />
          ) : null}
        </View>
    </View>
  );
}

type FilterDrawerProps = {
  chargingSpeeds: string[];
  chargingSpeedOptions: FilterOption[];
  connectorTypes: string[];
  connectorTypeOptions: FilterOption[];
  distanceKm: number;
  expanded: boolean;
  onApply: () => void;
  onClose: () => void;
  onReset: () => void;
  onSelectDistance: (distanceKm: number) => void;
  onToggleChargingSpeed: (key: string) => void;
  onToggleConnectorType: (key: string) => void;
  onScroll?: (e: any) => void;
};

function FilterDrawer({
  chargingSpeeds,
  chargingSpeedOptions,
  connectorTypes,
  connectorTypeOptions,
  distanceKm,
  expanded,
  onApply,
  onClose,
  onReset,
  onSelectDistance,
  onToggleChargingSpeed,
  onToggleConnectorType,
  onScroll
}: FilterDrawerProps) {
  return (
    <View style={styles.drawerBody}>
      <View style={styles.sheetHeader}>
        <Text style={styles.sheetTitle}>Filter</Text>
        <Pressable accessibilityLabel="Close filter" accessibilityRole="button" onPress={onClose} style={styles.closeButton}>
          <SvgAssetIcon color="#191C1D" height={14} name="close" svg={closeButtonIcon} width={14} />
        </Pressable>
      </View>

      <View style={[styles.expandedContent, getExpandedContentStateStyle(expanded)]}>
        <ScrollView
          contentContainerStyle={styles.filterContent}
          showsVerticalScrollIndicator={false}
          onScroll={onScroll}
          scrollEventThrottle={16}
        >
          <FilterCategory
            title="Connector Type"
            options={connectorTypeOptions}
            selectedKeys={connectorTypes}
            onToggle={onToggleConnectorType}
          />

          <FilterCategory
            title="Charging Speed"
            variant="card"
            options={chargingSpeedOptions}
            selectedKeys={chargingSpeeds}
            onToggle={onToggleChargingSpeed}
          />

          <View style={styles.distanceSection}>
            <View style={styles.distanceHeader}>
              <Text style={styles.categoryTitle}>Distance</Text>
              <Text style={styles.distanceValue}>{distanceKm} km</Text>
            </View>
            <PlatformSlider
              style={{ width: '100%', height: 40, marginTop: 8 }}
              minimumValue={0}
              maximumValue={distanceOptions.length - 1}
              step={1}
              value={distanceOptions.indexOf(distanceKm as any) >= 0 ? distanceOptions.indexOf(distanceKm as any) : 0}
              onValueChange={(value) => onSelectDistance(distanceOptions[value])}
              minimumTrackTintColor="#0bb2b2"
              maximumTrackTintColor="#dde5e8"
              thumbTintColor="#0bb2b2"
            />
            <View style={styles.sliderLabels}>
              {distanceOptions.map((option) => (
                <Pressable accessibilityRole="button" key={option} onPress={() => onSelectDistance(option)}>
                  <Text style={[styles.sliderLabel, option === distanceKm && styles.sliderLabelSelected]}>{option} km</Text>
                </Pressable>
              ))}
            </View>
          </View>
        </ScrollView>

        <View style={styles.actionRow}>
          <Pressable accessibilityRole="button" onPress={onReset} style={styles.resetButton}>
            <Text style={styles.resetButtonText}>Reset</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={onApply} style={styles.applyButton}>
            <Text style={styles.applyButtonText}>Apply</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

type ResultsDrawerProps = {
  filteredBySearch: boolean;
  hasUserLocation: boolean;
  expanded: boolean;
  locationPermissionLoading: boolean;
  locationPermissionStatus: LocationPermissionStatus;
  loading: boolean;
  onFilter: () => void;
  onRequestLocation: () => void;
  onSelectStation: (station: Station) => void;
  onScroll?: (e: any) => void;
  stations: Station[];
  stationsError: string | null;
};

function ResultsDrawer({
  expanded,
  filteredBySearch,
  hasUserLocation,
  loading,
  locationPermissionLoading,
  locationPermissionStatus,
  onFilter,
  onRequestLocation,
  onSelectStation,
  onScroll,
  stations,
  stationsError
}: ResultsDrawerProps) {
  const shouldShowLocationPrompt = !hasUserLocation;

  return (
    <View style={styles.drawerBody}>
      <View style={styles.resultsHeader}>
        <Text style={styles.resultsTitle}>{filteredBySearch ? 'Search Results' : 'Nearby SPKLU Stations'}</Text>
        <Pressable accessibilityRole="button" onPress={onFilter} style={styles.filterButton}>
          <SvgAssetIcon color="#4c5960" height={14} name="filter" svg={filterSettingIcon} width={14} />
          <Text style={styles.filterButtonText}>Filter</Text>
        </Pressable>
      </View>

      <View style={[styles.expandedContent, getExpandedContentStateStyle(expanded)]}>
        {shouldShowLocationPrompt ? (
          <View style={styles.locationPermissionCard}>
            <View style={styles.locationPermissionTextWrap}>
              <Text style={styles.locationPermissionTitle}>Use your current location</Text>
              <Text style={styles.locationPermissionBody}>{getLocationPermissionMessage(locationPermissionStatus)}</Text>
            </View>
            <Pressable
              accessibilityRole="button"
              disabled={locationPermissionLoading || locationPermissionStatus === 'denied' || locationPermissionStatus === 'unavailable'}
              onPress={onRequestLocation}
              style={[
                styles.locationPermissionButton,
                (locationPermissionLoading || locationPermissionStatus === 'denied' || locationPermissionStatus === 'unavailable') &&
                  styles.locationPermissionButtonDisabled
              ]}
            >
              <Text style={styles.locationPermissionButtonText}>
                {locationPermissionLoading ? 'Checking...' : getLocationPermissionButtonLabel(locationPermissionStatus)}
              </Text>
            </Pressable>
          </View>
        ) : null}

        <ScrollView
          contentContainerStyle={styles.stationList}
          showsVerticalScrollIndicator={false}
          onScroll={onScroll}
          scrollEventThrottle={16}
        >
          {loading ? <Text style={styles.stationAddress}>Loading nearby SPKLU stations...</Text> : null}
          {!loading && stationsError ? <Text style={styles.stationAddress}>{stationsError}</Text> : null}
          {!loading && !stationsError && stations.length === 0 ? (
            <Text style={styles.stationAddress}>{filteredBySearch ? 'No SPKLU stations match your search.' : 'No nearby SPKLU stations found.'}</Text>
          ) : null}
          {!loading && !stationsError
            ? stations.map((station) => <StationCard key={station.id} station={station} onPress={() => onSelectStation(station)} />)
            : null}
        </ScrollView>
      </View>
    </View>
  );
}

function getLocationPermissionMessage(status: LocationPermissionStatus) {
  if (status === 'denied') {
    return 'Location permission is blocked. Enable location access in your browser settings, then reload this page.';
  }

  if (status === 'unavailable') {
    return 'Location permission requires HTTPS or localhost and a browser with geolocation support.';
  }

  return 'Allow location access to reload nearby stations around your current position.';
}

function getLocationPermissionButtonLabel(status: LocationPermissionStatus) {
  if (status === 'denied') {
    return 'Location Blocked';
  }

  if (status === 'unavailable') {
    return 'Location Unavailable';
  }

  return 'Use Current Location';
}

type StationDetailDrawerProps = {
  expanded: boolean;
  station: Station;
  onClose: () => void;
  onScroll?: (e: any) => void;
};

function StationDetailDrawer({ expanded, station, onClose, onScroll }: StationDetailDrawerProps) {
  return (
    <View style={styles.drawerBody}>
      <View style={styles.sheetHeader}>
        <Text numberOfLines={1} style={styles.detailTitle}>
          {station.name.replace(' Hub', '')}
        </Text>
        <Pressable accessibilityLabel="Close station detail" accessibilityRole="button" onPress={onClose} style={styles.closeButton}>
          <SvgAssetIcon color="#191C1D" height={14} name="close" svg={closeButtonIcon} width={14} />
        </Pressable>
      </View>

      <View style={[styles.expandedContent, getExpandedContentStateStyle(expanded)]}>
        <ScrollView
          contentContainerStyle={styles.stationDetailContent}
          showsVerticalScrollIndicator={false}
          onScroll={onScroll}
          scrollEventThrottle={16}
        >
          <Text style={styles.stationAddress}>{station.address}</Text>
          <View style={styles.connectorList}>
            {station.connectors.map((connector, index) => (
              <ConnectorRow connector={connector} key={`${connector.type}-${connector.speedTier ?? 'unknown'}-${connector.powerKw ?? 'unknown'}-${index}`} />
            ))}
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

type StationCardProps = {
  station: Station;
  onPress: () => void;
};

function StationCard({ station, onPress }: StationCardProps) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.stationCard}>
      <Text style={styles.stationName}>{station.name}</Text>
      <Text style={styles.stationAddress}>{station.address}</Text>
      {station.distanceKm !== undefined ? <Text style={styles.connectorSpeed}>{station.distanceKm.toFixed(1)} km away</Text> : null}
      <View style={styles.connectorList}>
        {station.connectors.map((connector, index) => (
          <ConnectorRow connector={connector} key={`${connector.type}-${connector.speedTier ?? 'unknown'}-${connector.powerKw ?? 'unknown'}-${index}`} />
        ))}
      </View>
    </Pressable>
  );
}

type ConnectorRowProps = {
  connector: ConnectorInfo;
};

function ConnectorRow({ connector }: ConnectorRowProps) {
  const type = connector.type || 'Unknown connector';
  const speedTier = formatSpeedTier(connector.speedTier);

  return (
    <View style={styles.connectorRow}>
      <View style={styles.connectorLeft}>
        <View style={styles.connectorIcon}>
          <SvgAssetIcon color="#00696F" height={17} name="lightning" svg={lightningIcon} width={15} />
        </View>
        <Text style={styles.connectorName}>{type}</Text>
      </View>
      <View style={styles.connectorMeta}>
        <Text style={styles.connectorSpeed}>{speedTier}</Text>
        <View style={styles.connectorDivider} />
        <Text style={styles.connectorTotal}>Total {connector.count}</Text>
      </View>
    </View>
  );
}

type LoadSpkluStationsOptions = {
  chargingSpeeds?: SpeedTierApiItem[];
  connectorTypes?: ConnectorTypeApiItem[];
  distanceKm?: number;
  userLocation?: Coordinates | null;
};

async function loadSpkluStations({
  chargingSpeeds = [],
  connectorTypes = [],
  distanceKm,
  userLocation
}: LoadSpkluStationsOptions = {}) {
  const connectorFilters = connectorTypes.filter((connector) => connector.name);
  const speedFilters = chargingSpeeds.filter((speedTier) => speedTier.id);
  const isReset = connectorFilters.length === 0 && speedFilters.length === 0 && distanceKm === defaultDistanceKm;

  if (isReset || !userLocation) {
    const response = await fetchStations({
      connectorType: connectorFilters,
      limit: defaultStationLimit,
      speedTier: speedFilters
    });
    const stationsById = new Map<string, Station>();
    response.items.forEach((item) => {
      const station = toStation(item);
      stationsById.set(station.id, station);
    });
    return Array.from(stationsById.values());
  }

  const response = await fetchNearbyStations({
    lat: userLocation.latitude,
    lon: userLocation.longitude,
    radius: distanceKm ?? defaultDistanceKm,
    connectorType: connectorFilters,
    speedTier: speedFilters,
    limit: 200
  });

  const stationsById = new Map<string, Station>();
  response.forEach((item) => {
    const station = toStation(item);
    stationsById.set(station.id, station);
  });
  return Array.from(stationsById.values()).sort((left, right) => (left.distanceKm ?? 0) - (right.distanceKm ?? 0));
}

function toStation(item: StationApiItem): Station {
  const addressParts = [item.address, item.city, item.province].filter(Boolean);
  const apiConnectors = Array.isArray(item.connectors) ? item.connectors : [];
  const connectors = apiConnectors.length
    ? apiConnectors.map((connector) => toConnectorInfo(connector, item))
    : item.connector_types.length
    ? item.connector_types.map((connector) => toLegacyConnectorInfo(connector, item))
    : [
        {
          count: 1,
          powerKw: item.power_kw,
          speedTier: item.speed_tier,
          type: 'Unknown connector'
        }
      ];

  return {
    id: item.id,
    address: addressParts.join(', ') || 'Address not available',
    city: item.city,
    connectors,
    distanceKm: item.distance_km ?? undefined,
    latitude: item.latitude,
    longitude: item.longitude,
    name: item.name ?? 'Unnamed SPKLU Station',
    province: item.province
  };
}

function toConnectorInfo(connector: StationConnectorApiItem, station: StationApiItem): ConnectorInfo {
  return {
    count: typeof connector.count === 'number' ? connector.count : 1,
    powerKw: typeof connector.power_kw === 'number' ? connector.power_kw : station.power_kw,
    speedTier: typeof connector.speed_tier === 'string' ? connector.speed_tier : station.speed_tier,
    type: typeof connector.type === 'string' && connector.type ? connector.type : 'Unknown connector'
  };
}

function toLegacyConnectorInfo(connector: StationConnectorTypeApiItem, station: StationApiItem): ConnectorInfo {
  if (typeof connector === 'string') {
    return {
      count: 1,
      powerKw: station.power_kw,
      speedTier: station.speed_tier,
      type: connector
    };
  }

  const label = typeof connector.type === 'string' ? connector.type : 'Unknown connector';
  const count = typeof connector.count === 'number' ? connector.count : null;
  const speedTier = typeof connector.speed_tier === 'string' ? connector.speed_tier : null;
  const powerKw = typeof connector.power_kw === 'number' ? connector.power_kw : null;

  return {
    count: count ?? 1,
    powerKw: powerKw ?? station.power_kw,
    speedTier: speedTier ?? station.speed_tier,
    type: label || 'Unknown connector'
  };
}

function formatSpeedTier(speedTier: string | null) {
  if (!speedTier) {
    return 'UNKNOWN';
  }

  return speedTier.replace(/_/g, '-').toUpperCase();
}

function formatPowerRange(speedTier: SpeedTierApiItem) {
  if (speedTier.max_kw === null) {
    return `Over ${formatKw(speedTier.min_kw)} kW`;
  }

  if (speedTier.min_kw === 0) {
    return `Up to ${formatKw(speedTier.max_kw)} kW`;
  }

  return `${formatKw(speedTier.min_kw)} - ${formatKw(speedTier.max_kw)} kW`;
}

function formatKw(value: number) {
  return Number.isInteger(value) ? String(value) : String(value);
}

function toBoundingBox(center: Coordinates, radiusKm: number) {
  const latDelta = radiusKm / 111;
  const lonDelta = radiusKm / (111 * Math.cos((center.latitude * Math.PI) / 180));

  return [
    center.longitude - lonDelta,
    center.latitude - latDelta,
    center.longitude + lonDelta,
    center.latitude + latDelta
  ].join(',');
}

function colorSvg(svg: string, color: string) {
  return svg
    .replace(/<path /g, `<path fill="${color}" `)
    .replace('<svg ', '<svg width="30" height="34" style="display:block" ');
}

function getDistancePercent(distanceKm: number) {
  const index = distanceOptions.findIndex((option) => option === distanceKm);
  const fallbackIndex = distanceOptions.findIndex((option) => option === defaultDistanceKm);
  const safeIndex = index >= 0 ? index : fallbackIndex;

  return (safeIndex / (distanceOptions.length - 1)) * 100;
}

function getMobileFilterSheetHeight(screenHeight: number, topInset: number, bottomOffset: number) {
  const searchBarBottom = topInset + 24 + 66 + 12;
  const availableMapHeight = screenHeight - bottomOffset;
  const maxHeightWithSearchVisible = screenHeight - bottomOffset - searchBarBottom;
  const cappedHeight = Math.min(availableMapHeight * 0.95, maxHeightWithSearchVisible);

  return Math.max(104, Math.floor(cappedHeight));
}

function getSearchResultsSheetHeight(screenHeight: number, topInset: number, bottomOffset: number) {
  const searchBarBottom = topInset + 24 + 66 + 12;
  const maxHeightWithSearchVisible = screenHeight - bottomOffset - searchBarBottom;

  return Math.max(104, Math.floor(maxHeightWithSearchVisible));
}

function filterStationsByKeyword(stations: Station[], query: string) {
  const keywords = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  if (!keywords.length) {
    return stations;
  }

  return stations.filter((station) => {
    const searchableText = [
      station.name,
      station.address,
      station.province ?? '',
      station.city ?? ''
    ]
      .join(' ')
      .toLowerCase();

    return keywords.every((keyword) => searchableText.includes(keyword));
  });
}

function toggleSelected(key: string, selectedKeys: string[], setSelectedKeys: (keys: string[]) => void) {
  setSelectedKeys(selectedKeys.includes(key) ? selectedKeys.filter((selectedKey) => selectedKey !== key) : [...selectedKeys, key]);
}

function getSelectedConnectorTypes(selectedKeys: string[], options: ConnectorTypeApiItem[]) {
  const optionsByName = new Map(options.map((option) => [option.name, option]));

  return selectedKeys
    .map((key) => optionsByName.get(key))
    .filter((option): option is ConnectorTypeApiItem => Boolean(option));
}

function getSelectedSpeedTiers(selectedKeys: string[], options: SpeedTierApiItem[]) {
  const optionsById = new Map(options.map((option) => [option.id, option]));

  return selectedKeys
    .map((key) => optionsById.get(key))
    .filter((option): option is SpeedTierApiItem => Boolean(option));
}

function resetFilters(
  setConnectorTypes: (keys: string[]) => void,
  setChargingSpeeds: (keys: string[]) => void,
  setDistanceKm: (distanceKm: number) => void
) {
  setConnectorTypes([]);
  setChargingSpeeds([]);
  setDistanceKm(defaultDistanceKm);
}

function updateSheetSizeFromDelta(deltaY: number, setExpanded: React.Dispatch<React.SetStateAction<boolean>>) {
  setExpanded(current => {
    if (deltaY > 18 && current) {
      LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
      return false;
    }
    if (deltaY < -18 && !current) {
      LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
      return true;
    }
    return current;
  });
}

type WebTransitionStyle = ViewStyle & {
  boxShadow?: string;
  transitionDuration?: string;
  transitionProperty?: string;
  transitionTimingFunction?: string;
};

function getSheetStateStyle(mode: DrawerMode, expanded: boolean, detailSheetHeight?: number, filterSheetHeight?: number, resultsSheetHeight?: number): WebTransitionStyle {
  const expandedHeights: Record<DrawerMode, number> = {
    detail: detailSheetHeight ?? 254,
    filter: filterSheetHeight ?? 430,
    results: resultsSheetHeight ?? 650
  };

  return {
    height: expanded ? expandedHeights[mode] : 104,
    ...getWebTransition('height', '240ms', 'cubic-bezier(0.22, 1, 0.36, 1)')
  };
}

function getExpandedContentStateStyle(expanded: boolean): WebTransitionStyle {
  return {
    opacity: expanded ? 1 : 0,
    pointerEvents: expanded ? 'auto' : 'none',
    transform: [{ translateY: expanded ? 0 : 16 }],
    ...getWebTransition('opacity, transform', '180ms', 'ease-out')
  };
}

function getWebTransition(property: string, duration: string, timingFunction: string): WebTransitionStyle {
  if (Platform.OS !== 'web') {
    return {};
  }

  return {
    transitionDuration: duration,
    transitionProperty: property,
    transitionTimingFunction: timingFunction
  };
}
