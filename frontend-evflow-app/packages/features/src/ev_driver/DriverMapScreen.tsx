import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, LayoutAnimation, PanResponder, Platform, Pressable, ScrollView, Text, TextInput, UIManager, View, useWindowDimensions, type ViewStyle } from 'react-native';
import { driverMapStyles as styles, LeafletMap } from '@evflow/ui';
import { fetchConnectorTypes, fetchNearbyStations, fetchSpeedTiers, fetchStations, type ConnectorTypeApiItem, type SpeedTierApiItem, type StationApiItem, type StationConnectorApiItem, type StationConnectorTypeApiItem } from '@evflow/shared';
import { getUserLocation, type LocationPermissionStatus } from './utils/location';
import { getStationAvailabilityBand, stationBandColors, stationBandLabels } from './station-area/stationAvailabilityBand';
import { defaultDistanceKm, defaultStationAreaMode, distanceOptions, getAreaFilterLabels, getAreaResultsTitle, getEmptyResultsMessage, getLocationPermissionPrompt, getMountLocationDecision, getStationFetchDecision, getStationQueryPlan, isStationAreaMode, resolveStationAreaMode, shouldRequestLocationForNearMe, shouldShowRadiusRing, stationAreaModeOptions, type DistanceOption, type ResolvedStationAreaMode, type StationAreaMode, type StationFetchDecision, type UserLocationSnapshot } from './station-area/areaFilterMode';
import { readStationAreaSelection, saveStationAreaSelection } from './station-area/areaFilterSession';
import { FilterCategory, type FilterOption } from './components/FilterCategory';
import { selectedSpkluMarkerSvg, spkluMarkerSvg } from './components/spkluMarkerSvg';
import { PlatformSlider } from '../shared/PlatformSlider';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { closeButtonIcon, filterSettingIcon, lightningIcon, searchIcon } from './components/driverMapIcons';
import { ConnectorAvailabilityRow } from './components/ConnectorAvailabilityRow';
import { NearbyAlternatives } from './components/NearbyAlternatives';
import { ALTERNATIVES_FETCH_LIMIT, ALTERNATIVES_RADIUS_KM, selectNearbyAlternatives, shouldOfferAlternatives } from './station-area/nearbyAlternatives';
import { PeakHoursChart } from './components/PeakHoursChart';
import { StationAvailabilitySummary } from './components/StationAvailabilitySummary';
import { StationDetailActions } from './components/StationDetailActions';
import { aggregateConnectorStatuses } from './station-status/aggregateConnectorStatuses';
import { getApiStationLiveStatus as defaultStationStatusLoader } from './station-status/apiStationStatus';
import { getDrawerAwareMapCenter, getDrawerModeAfterClosingStationDetail, getFreshCachedStationStatus, invalidateCachedStationStatus, isCurrentStationStatusRequest, loadValidStationStatus, shouldRenderSearchBar, type CachedStationStatus } from './station-status/stationDetailState';
import { type StationLiveStatus, type StationStatusLoader } from './station-status/types';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export type DriverMapScreenProps = {
  bottomOffset?: number;
  onChargeHere?: (stationId: string) => void;
  stationStatusLoader?: StationStatusLoader;
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
  // Live plug counts, used to colour the pin. Optional because an older server
  // does not send them, and absent must read as "unknown", never as "full".
  availableConnectors?: number | null;
  totalConnectors?: number | null;
};

type Coordinates = {
  latitude: number;
  longitude: number;
};

type MapViewState = {
  center: Coordinates;
  zoom: number;
};

const collapsedSheetHeight = 104;
const collapsedDetailSheetHeight = 204;
const stationDetailZoom = 15;
const defaultMapView: MapViewState = {
  center: {
    latitude: -6.1754,
    longitude: 106.8272
  },
  zoom: 13
};
export function DriverMapScreen({
  bottomOffset = 0,
  onChargeHere,
  stationStatusLoader = defaultStationStatusLoader,
  topInset = 0
}: DriverMapScreenProps) {
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
  const [storedAreaSelection] = useState(readStationAreaSelection);
  const [areaMode, setAreaMode] = useState<StationAreaMode>(storedAreaSelection.mode);
  const [appliedAreaMode, setAppliedAreaMode] = useState<StationAreaMode>(storedAreaSelection.mode);
  const [distanceKm, setDistanceKm] = useState<DistanceOption>(storedAreaSelection.distanceKm);
  const [appliedDistanceKm, setAppliedDistanceKm] = useState<DistanceOption>(storedAreaSelection.distanceKm);
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
  const [stationLiveStatus, setStationLiveStatus] = useState<StationLiveStatus | null>(null);
  const [stationStatusError, setStationStatusError] = useState<string | null>(null);
  const [stationStatusLoading, setStationStatusLoading] = useState(false);
  const [stationStatusRetry, setStationStatusRetry] = useState(0);
  const [nearbyAlternatives, setNearbyAlternatives] = useState<Station[] | null>(null);
  const [alternativesError, setAlternativesError] = useState<string | null>(null);
  const [alternativesLoading, setAlternativesLoading] = useState(false);
  const [alternativesRetry, setAlternativesRetry] = useState(0);
  const previousMapViewRef = useRef<MapViewState>(defaultMapView);
  const previousResultsExpandedRef = useRef(false);
  const requestedLocationPermissionRef = useRef(false);
  const selectedStationRef = useRef<Station | null>(selectedStation);
  const expandedRef = useRef(expanded);
  const searchQueryRef = useRef(searchQuery);
  const searchRestoreStateRef = useRef<{ drawerMode: DrawerMode; expanded: boolean; selectedStation: Station | null } | null>(null);
  const stationStatusCacheRef = useRef(new Map<string, CachedStationStatus>());
  const stationStatusRequestRef = useRef(0);
  const searchActive = drawerMode !== 'detail' && (searchFocused || searchQuery.trim().length > 0);
  const locationSnapshot = useMemo<UserLocationSnapshot>(
    () => ({ coordinates: userLocation, status: locationPermissionStatus }),
    [locationPermissionStatus, userLocation]
  );
  // Draft and applied are resolved separately: the filter drawer previews the
  // mode being edited while the map and the results list still reflect the
  // mode that was last applied.
  const draftAreaResolution = useMemo(
    () => resolveStationAreaMode(areaMode, locationSnapshot),
    [areaMode, locationSnapshot]
  );
  const appliedAreaResolution = useMemo(
    () => resolveStationAreaMode(appliedAreaMode, locationSnapshot),
    [appliedAreaMode, locationSnapshot]
  );
  // Whether the stations request can run yet. 'near' with an unanswered
  // permission has no result to show and no query worth running.
  const appliedFetchDecision = useMemo(
    () => getStationFetchDecision(appliedAreaMode, locationSnapshot),
    [appliedAreaMode, locationSnapshot]
  );

  useEffect(() => {
    selectedStationRef.current = selectedStation;
  }, [selectedStation]);

  // EVDriverContainer swaps screens by conditional render, so this component
  // unmounts on every tab change. The committed area choice is stored outside
  // component state so returning to the map does not silently reset it.
  useEffect(() => {
    saveStationAreaSelection({ distanceKm: appliedDistanceKm, mode: appliedAreaMode });
  }, [appliedAreaMode, appliedDistanceKm]);

  useEffect(() => {
    expandedRef.current = expanded;
  }, [expanded]);

  useEffect(() => {
    if (drawerMode !== 'detail' || !selectedStation) {
      setStationLiveStatus(null);
      setStationStatusError(null);
      setStationStatusLoading(false);
      return;
    }

    const stationId = selectedStation.id;
    const cachedStatus = getFreshCachedStationStatus(stationStatusCacheRef.current, stationId);
    if (cachedStatus) {
      setStationLiveStatus(cachedStatus);
      setStationStatusError(null);
      setStationStatusLoading(false);
      return;
    }

    const request = { requestId: ++stationStatusRequestRef.current, stationId };
    let active = true;
    setStationLiveStatus(null);
    setStationStatusError(null);
    setStationStatusLoading(true);

    void loadValidStationStatus(stationStatusLoader, stationId)
      .then((status) => {
        if (!active || !isCurrentStationStatusRequest(request, stationStatusRequestRef.current, selectedStationRef.current?.id ?? null)) {
          return;
        }
        stationStatusCacheRef.current.set(stationId, { data: status, fetchedAt: Date.now() });
        setStationLiveStatus(status);
        setStationStatusError(null);
      })
      .catch((error: unknown) => {
        if (!active || !isCurrentStationStatusRequest(request, stationStatusRequestRef.current, selectedStationRef.current?.id ?? null)) {
          return;
        }
        setStationLiveStatus(null);
        setStationStatusError(error instanceof Error ? error.message : 'Unable to load live station status.');
      })
      .finally(() => {
        if (active && isCurrentStationStatusRequest(request, stationStatusRequestRef.current, selectedStationRef.current?.id ?? null)) {
          setStationStatusLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [drawerMode, selectedStation?.id, stationStatusLoader, stationStatusRetry]);

  // AC 3.4.1: when the opened station turns out to be unusable right now (all
  // connectors taken/broken, or the wait estimate is over the threshold), load
  // nearby stations with a free connector so the driver can pivot without
  // leaving this screen. The search is centred on the STATION, not the driver.
  useEffect(() => {
    const liveAvailability = stationLiveStatus ? aggregateConnectorStatuses(stationLiveStatus.connectors) : null;
    if (drawerMode !== 'detail' || !selectedStation || !shouldOfferAlternatives(liveAvailability)) {
      setNearbyAlternatives(null);
      setAlternativesError(null);
      setAlternativesLoading(false);
      return;
    }

    const stationId = selectedStation.id;
    let active = true;
    setAlternativesLoading(true);
    setAlternativesError(null);

    fetchNearbyStations({
      lat: selectedStation.latitude,
      lon: selectedStation.longitude,
      radius: ALTERNATIVES_RADIUS_KM,
      connectorType: appliedConnectorTypes.filter((connector) => connector.name),
      speedTier: appliedChargingSpeeds.filter((speedTier) => speedTier.id),
      limit: ALTERNATIVES_FETCH_LIMIT
    })
      .then((items) => {
        if (!active || selectedStationRef.current?.id !== stationId) return;
        setNearbyAlternatives(toUniqueStations(selectNearbyAlternatives(items, stationId)));
      })
      .catch(() => {
        if (!active || selectedStationRef.current?.id !== stationId) return;
        setNearbyAlternatives(null);
        setAlternativesError('Unable to load nearby alternatives. Check your connection and retry.');
      })
      .finally(() => {
        if (!active || selectedStationRef.current?.id !== stationId) return;
        setAlternativesLoading(false);
      });

    return () => {
      active = false;
    };
  }, [drawerMode, selectedStation?.id, selectedStation?.latitude, selectedStation?.longitude, stationLiveStatus, appliedConnectorTypes, appliedChargingSpeeds, alternativesRetry]);

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

  // Choosing "Near me" without a fix asks for one rather than failing quietly.
  // If the driver refuses, resolveStationAreaMode downgrades the request to
  // "All" and the drawer says why; no stand-in coordinates are invented.
  const handleSelectAreaMode = (nextMode: StationAreaMode) => {
    setAreaMode(nextMode);

    if (nextMode === 'near' && shouldRequestLocationForNearMe(locationSnapshot)) {
      void resolveUserLocation(true);
    }
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

      // A session starts on "near me", which cannot be answered without a fix,
      // so opening the screen has to go and get one rather than degrade to the
      // whole country. Whether that means prompting now or waiting for a tap
      // is decided by getMountLocationDecision, not by this effect.
      const mountDecision = getMountLocationDecision({
        alreadyRequested: requestedLocationPermissionRef.current,
        // Ask on every platform, browser included. Holding the prompt back on
        // web left the driver on an EMPTY map captioned "Nearby SPKLU Stations
        // (0)": the card explaining why lives in the results sheet, which mounts
        // collapsed at opacity 0, so nothing on screen said what to do. An empty
        // map with no explanation is a worse failure than the sticky-denial risk
        // of asking, and a map app asking for location on open is expected.
        // A refusal is not a dead end: it degrades to the national list with a
        // visible reason, and re-resolves by itself if permission is granted later.
        canPromptOnMount: true,
        location: { coordinates: locationResult.coordinates, status: locationResult.status },
        storedMode: storedAreaSelection.mode
      });

      if (mountDecision === 'request_permission') {
        await resolveUserLocation(true);
        return;
      }

      // 'await_driver_action' still resolves: the fetch effect holds the
      // stations request itself, so the screen settles into the permission
      // card instead of an indefinite spinner.
      setLocationResolved(true);
    })();

    return () => {
      mounted = false;
    };
  }, [storedAreaSelection]);

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

    // Nothing is loading here, so no spinner: the screen is waiting on the
    // driver. Running the query anyway would paint every station in the
    // country for the moment before they answer.
    if (appliedFetchDecision === 'await_permission') {
      setStations([]);
      setStationsError(null);
      setStationsLoading(false);
      return;
    }

    let mounted = true;

    async function loadStations() {
      setStationsLoading(true);
      setStationsError(null);

      try {
        const nextStations = await loadSpkluStations({
          areaMode: appliedAreaMode,
          chargingSpeeds: appliedChargingSpeeds,
          connectorTypes: appliedConnectorTypes,
          distanceKm: appliedDistanceKm,
          location: locationSnapshot
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
  }, [appliedAreaMode, appliedChargingSpeeds, appliedConnectorTypes, appliedDistanceKm, appliedFetchDecision, locationResolved, locationSnapshot]);

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
  const activeFilterLabels = useMemo(
    () => [
      ...getAreaFilterLabels(appliedAreaResolution, appliedDistanceKm),
      ...appliedConnectorTypes.map((connector) => connector.name),
      ...appliedChargingSpeeds.map((speed) => speed.label)
    ],
    [appliedAreaResolution, appliedChargingSpeeds, appliedConnectorTypes, appliedDistanceKm]
  );
  // Four badges, built once, not one per station: with a thousand pins on
  // screen, generating an SVG string per marker would dominate the render.
  const bandIcons = useMemo(() => ({
    free: spkluMarkerSvg(32, stationBandColors.free),
    limited: spkluMarkerSvg(32, stationBandColors.limited),
    full: spkluMarkerSvg(32, stationBandColors.full),
    unknown: spkluMarkerSvg(32)
  }), []);
  const selectedBandIcons = useMemo(() => ({
    free: selectedSpkluMarkerSvg(44, stationBandColors.free),
    limited: selectedSpkluMarkerSvg(44, stationBandColors.limited),
    full: selectedSpkluMarkerSvg(44, stationBandColors.full),
    unknown: selectedSpkluMarkerSvg(44)
  }), []);
  const stationMarkers = useMemo(
    () =>
      visibleStations.map((station) => {
        const band = getStationAvailabilityBand(station.availableConnectors, station.totalConnectors);
        return {
          id: station.id,
          // Colour is not the only carrier: the popup label says it in words.
          label: band === 'unknown' ? station.name : `${station.name ?? 'SPKLU'} — ${stationBandLabels[band]}`,
          latitude: station.latitude,
          longitude: station.longitude,
          iconSvg: bandIcons[band],
          selectedIconSvg: selectedBandIcons[band]
        };
      }),
    [bandIcons, selectedBandIcons, visibleStations]
  );
  const stationMarkerIcon = useMemo(() => spkluMarkerSvg(32), []);
  // Selected badge: same artwork ringed in dark teal + white and slightly larger,
  // so the tapped station is unmistakable among its neighbours.
  const selectedStationMarkerIcon = useMemo(() => selectedSpkluMarkerSvg(44), []);
  const detailSheetHeight = width < 768
    ? Math.floor((height - bottomOffset) * 0.8)
    : Math.min(720, height - bottomOffset - 32);
  const filterSheetHeight = width < 768 ? getMobileFilterSheetHeight(height, topInset, bottomOffset) : undefined;
  const searchSheetHeight = getSearchResultsSheetHeight(height, topInset, bottomOffset);

  useEffect(() => {
    if (drawerMode !== 'detail' || !selectedStation) {
      return;
    }

    const drawerHeight = expanded ? detailSheetHeight : collapsedDetailSheetHeight;
    setMapView({
      center: getDrawerAwareMapCenter(selectedStation, stationDetailZoom, bottomOffset + drawerHeight),
      zoom: stationDetailZoom
    });
  }, [bottomOffset, detailSheetHeight, drawerMode, expanded, selectedStation?.id]);

  const activateSearchResults = () => {
    searchRestoreStateRef.current ??= { drawerMode, expanded, selectedStation };

    animateNext();
    setSearchFocused(true);
    setSelectedStation(null);
    setDrawerMode(getDrawerModeAfterClosingStationDetail());
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
    selectedStationRef.current = station;
    setSelectedStation(station);

    setMapView({
      center: getDrawerAwareMapCenter(station, stationDetailZoom, bottomOffset + collapsedDetailSheetHeight),
      zoom: stationDetailZoom
    });
    setDrawerMode('detail');
    setExpanded(false);
  };
  const closeStationDetail = () => {
    stationStatusRequestRef.current += 1;
    animateNext();
    selectedStationRef.current = null;
    setSelectedStation(null);
    setMapView(previousMapViewRef.current);
    setDrawerMode(getDrawerModeAfterClosingStationDetail());
    setExpanded(previousResultsExpandedRef.current);
  };

  return (
    <View style={styles.page}>
      <LeafletMap
        center={mapView.center}
        currentLocation={userLocation}
        markerIconSvg={stationMarkerIcon}
        markers={stationMarkers}
        radiusKm={getRadiusRingKm(
          drawerMode === 'filter' ? areaMode : appliedAreaMode,
          locationSnapshot,
          drawerMode === 'filter' ? distanceKm : appliedDistanceKm
        )}
        selectedMarkerIconSvg={selectedStationMarkerIcon}
        selectedMarkerId={selectedStation?.id ?? null}
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

      {shouldRenderSearchBar(drawerMode) ? <View style={[styles.searchBar, { top: 24 + topInset }]}>
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
      </View> : null}

        <View style={[styles.sheet, getSheetStateStyle(drawerMode, expanded, detailSheetHeight, filterSheetHeight, searchSheetHeight), { bottom: bottomOffset }]} {...drawerPanResponder.panHandlers}>
          <Pressable
            accessibilityLabel={expanded ? 'Collapse drawer' : 'Expand drawer'}
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
              areaResolution={draftAreaResolution}
              chargingSpeeds={chargingSpeeds}
              chargingSpeedOptions={speedFilterOptions}
              connectorTypes={connectorTypes}
              connectorTypeOptions={connectorFilterOptions}
              distanceKm={distanceKm}
              expanded={expanded}
              locationPermissionLoading={locationPermissionLoading}
              onApply={() => {
                animateNext();
                setAppliedAreaMode(areaMode);
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
              onRequestLocation={() => resolveUserLocation(true)}
              onReset={() => {
                resetFilters(setConnectorTypes, setChargingSpeeds, setDistanceKm, setAreaMode);
                animateNext();
                setAppliedAreaMode(defaultStationAreaMode);
                setAppliedChargingSpeeds([]);
                setAppliedConnectorTypes([]);
                setAppliedDistanceKm(defaultDistanceKm);
                setDrawerMode('results');
                setSelectedStation(null);
                setExpanded(true);
              }}
              onSelectAreaMode={handleSelectAreaMode}
              onSelectDistance={setDistanceKm}
              onToggleChargingSpeed={(key) => toggleSelected(key, chargingSpeeds, setChargingSpeeds)}
              onToggleConnectorType={(key) => toggleSelected(key, connectorTypes, setConnectorTypes)}
              onScroll={handleScroll}
            />
          ) : null}

          {drawerMode === 'results' ? (
            <ResultsDrawer
              activeFilterLabels={activeFilterLabels}
              appliedDistanceKm={appliedDistanceKm}
              areaResolution={appliedAreaResolution}
              expanded={expanded}
              fetchDecision={appliedFetchDecision}
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
              alternatives={nearbyAlternatives}
              alternativesError={alternativesError}
              alternativesLoading={alternativesLoading}
              expanded={expanded}
              liveStatus={stationLiveStatus}
              onScroll={handleScroll}
              station={selectedStation}
              onClose={closeStationDetail}
              onChargeHere={onChargeHere ? () => onChargeHere(selectedStation.id) : undefined}
              onRetry={() => {
                invalidateCachedStationStatus(stationStatusCacheRef.current, selectedStation.id);
                setStationStatusRetry((current) => current + 1);
              }}
              onRetryAlternatives={() => setAlternativesRetry((current) => current + 1)}
              onSelectAlternative={openStationDetail}
              statusError={stationStatusError}
              statusLoading={stationStatusLoading}
            />
          ) : null}
        </View>
    </View>
  );
}

type FilterDrawerProps = {
  areaResolution: ResolvedStationAreaMode;
  chargingSpeeds: string[];
  chargingSpeedOptions: FilterOption[];
  connectorTypes: string[];
  connectorTypeOptions: FilterOption[];
  distanceKm: DistanceOption;
  expanded: boolean;
  locationPermissionLoading: boolean;
  onApply: () => void;
  onClose: () => void;
  onRequestLocation: () => void;
  onReset: () => void;
  onSelectAreaMode: (mode: StationAreaMode) => void;
  onSelectDistance: (distanceKm: DistanceOption) => void;
  onToggleChargingSpeed: (key: string) => void;
  onToggleConnectorType: (key: string) => void;
  onScroll?: (e: any) => void;
};

function FilterDrawer({
  areaResolution,
  chargingSpeeds,
  chargingSpeedOptions,
  connectorTypes,
  connectorTypeOptions,
  distanceKm,
  expanded,
  locationPermissionLoading,
  onApply,
  onClose,
  onRequestLocation,
  onReset,
  onSelectAreaMode,
  onSelectDistance,
  onToggleChargingSpeed,
  onToggleConnectorType,
  onScroll
}: FilterDrawerProps) {
  const areaOptions = useMemo<FilterOption[]>(
    () => stationAreaModeOptions.map((option) => ({ key: option.key, label: option.label })),
    []
  );

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
          <View style={{ gap: 10 }}>
            <FilterCategory
              title="Area"
              options={areaOptions}
              selectedKeys={[areaResolution.mode]}
              onToggle={(key) => {
                // Single choice, not a toggle: re-pressing the active option
                // keeps it selected rather than leaving no area filter at all.
                if (isStationAreaMode(key)) {
                  onSelectAreaMode(key);
                }
              }}
            />

            {areaResolution.reason ? (
              <View accessibilityLiveRegion="polite" style={styles.locationPermissionCard}>
                <View style={styles.locationPermissionTextWrap}>
                  <Text style={styles.locationPermissionTitle}>Near me needs your location</Text>
                  <Text style={styles.locationPermissionBody}>{areaResolution.reason}</Text>
                </View>
                <Pressable
                  accessibilityRole="button"
                  disabled={locationPermissionLoading}
                  onPress={onRequestLocation}
                  style={[
                    styles.locationPermissionButton,
                    locationPermissionLoading && styles.locationPermissionButtonDisabled
                  ]}
                >
                  <Text style={styles.locationPermissionButtonText}>
                    {locationPermissionLoading ? 'Checking...' : 'Try location again'}
                  </Text>
                </Pressable>
              </View>
            ) : null}
          </View>

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
            {areaResolution.mode === 'near' ? null : (
              <Text style={styles.sliderLabel}>Applies to the Near me area.</Text>
            )}
            <PlatformSlider
              style={{ width: '100%', height: 40, marginTop: 8 }}
              minimumValue={0}
              maximumValue={distanceOptions.length - 1}
              step={1}
              value={Math.max(0, distanceOptions.indexOf(distanceKm))}
              onValueChange={(value) => onSelectDistance(distanceOptions[clampDistanceIndex(value)])}
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
  activeFilterLabels: string[];
  appliedDistanceKm: DistanceOption;
  areaResolution: ResolvedStationAreaMode;
  fetchDecision: StationFetchDecision;
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
  activeFilterLabels,
  appliedDistanceKm,
  areaResolution,
  expanded,
  fetchDecision,
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
  // Only a driver who actually asked for "near me" is missing something; one
  // who chose "all stations" is not nagged for a location they do not need.
  const shouldShowLocationPrompt = !hasUserLocation && areaResolution.requestedMode === 'near';
  const locationPrompt = getLocationPermissionPrompt(areaResolution, locationPermissionStatus);

  return (
    <View style={styles.drawerBody}>
      <View style={styles.resultsHeader}>
        <Text style={styles.resultsTitle}>{filteredBySearch ? 'Search Results' : getAreaResultsTitle(areaResolution, fetchDecision)} ({stations.length})</Text>
        <Pressable accessibilityRole="button" onPress={onFilter} style={styles.filterButton}>
          <SvgAssetIcon color="#4c5960" height={14} name="filter" svg={filterSettingIcon} width={14} />
          <Text style={styles.filterButtonText}>Filter</Text>
        </Pressable>
      </View>
      {activeFilterLabels.length > 0 ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
          {activeFilterLabels.map((label) => (
            <View key={label} style={{ backgroundColor: '#e9fbfc', borderColor: '#b7dfe2', borderRadius: 999, borderWidth: 1, paddingHorizontal: 10, paddingVertical: 5 }}>
              <Text style={{ color: '#005f64', fontSize: 11, fontWeight: '900' }}>{label}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={[styles.expandedContent, getExpandedContentStateStyle(expanded)]}>
        {shouldShowLocationPrompt ? (
          <View style={styles.locationPermissionCard}>
            <View style={styles.locationPermissionTextWrap}>
              <Text style={styles.locationPermissionTitle}>{locationPrompt.title}</Text>
              <Text style={styles.locationPermissionBody}>{locationPrompt.body}</Text>
            </View>
            <Pressable
              accessibilityRole="button"
              disabled={locationPermissionLoading}
              onPress={onRequestLocation}
              style={[
                styles.locationPermissionButton,
                locationPermissionLoading && styles.locationPermissionButtonDisabled
              ]}
            >
              <Text style={styles.locationPermissionButtonText}>
                {locationPermissionLoading ? 'Checking...' : locationPrompt.buttonLabel}
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
          {loading ? <Text style={styles.stationAddress}>Loading SPKLU stations...</Text> : null}
          {!loading && stationsError ? <Text style={styles.stationAddress}>{stationsError}</Text> : null}
          {!loading && !stationsError && stations.length === 0 ? (
            <Text style={styles.stationAddress}>
              {filteredBySearch ? 'No SPKLU stations match your search.' : getEmptyResultsMessage(areaResolution, appliedDistanceKm, fetchDecision)}
            </Text>
          ) : null}
          {!loading && !stationsError
            ? stations.map((station) => <StationCard key={station.id} station={station} onPress={() => onSelectStation(station)} />)
            : null}
        </ScrollView>
      </View>
    </View>
  );
}

type StationDetailDrawerProps = {
  alternatives: Station[] | null;
  alternativesError: string | null;
  alternativesLoading: boolean;
  expanded: boolean;
  liveStatus: StationLiveStatus | null;
  station: Station;
  onClose: () => void;
  onChargeHere?: () => void;
  onRetry: () => void;
  onRetryAlternatives: () => void;
  onScroll?: (e: any) => void;
  onSelectAlternative: (station: Station) => void;
  statusError: string | null;
  statusLoading: boolean;
};

function StationDetailDrawer({
  alternatives,
  alternativesError,
  alternativesLoading,
  expanded,
  liveStatus,
  station,
  onChargeHere,
  onClose,
  onRetry,
  onRetryAlternatives,
  onScroll,
  onSelectAlternative,
  statusError,
  statusLoading
}: StationDetailDrawerProps) {
  const availability = useMemo(
    () => aggregateConnectorStatuses(liveStatus?.connectors ?? []),
    [liveStatus]
  );

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

      <View style={{ gap: 9 }}>
        <Text numberOfLines={expanded ? 2 : 1} style={styles.stationAddress}>{station.address}</Text>
        <StationAvailabilitySummary availability={availability} />
      </View>

      <View style={[styles.expandedContent, { marginTop: 12 }, getExpandedContentStateStyle(expanded)]}>
        <ScrollView
          contentContainerStyle={styles.stationDetailContent}
          showsVerticalScrollIndicator={false}
          onScroll={onScroll}
          scrollEventThrottle={16}
        >
          {statusLoading ? (
            <View accessibilityLabel="Loading live station status" accessibilityLiveRegion="polite" style={{ alignItems: 'center', flexDirection: 'row', gap: 10, minHeight: 48 }}>
              <ActivityIndicator color="#00696F" />
              <Text style={styles.stationAddress}>Loading live connector status...</Text>
            </View>
          ) : null}
          {statusError ? (
            <View accessibilityLiveRegion="polite" style={{ backgroundColor: '#FFF7ED', borderColor: '#F4C384', borderRadius: 12, borderWidth: 1, gap: 8, padding: 12 }}>
              <Text style={{ color: '#7A4410', fontSize: 13, lineHeight: 18 }}>{statusError}</Text>
              <Pressable accessibilityLabel="Retry station status" accessibilityRole="button" onPress={onRetry} style={{ alignItems: 'center', alignSelf: 'flex-start', borderColor: '#00696F', borderRadius: 8, borderWidth: 1, justifyContent: 'center', minHeight: 44, paddingHorizontal: 16 }}>
                <Text style={{ color: '#005F64', fontSize: 13, fontWeight: '900' }}>Retry</Text>
              </Pressable>
            </View>
          ) : null}
          {liveStatus ? (
            <View style={{ gap: 8 }}>
              {availability.groups.map((group) => <ConnectorAvailabilityRow group={group} key={group.key} />)}
            </View>
          ) : null}
          {liveStatus && shouldOfferAlternatives(availability) ? (
            <NearbyAlternatives
              alternatives={alternatives}
              error={alternativesError}
              loading={alternativesLoading}
              onRetry={onRetryAlternatives}
              onSelect={onSelectAlternative}
              reason={availability.availableCount <= 0 ? 'full' : 'long_wait'}
            />
          ) : null}
          {liveStatus ? <PeakHoursChart availabilityState={availability.state} peakHours={liveStatus.peakHours} /> : null}
          <StationDetailActions availability={availability} onBack={onClose} onChargeHere={onChargeHere} />
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
  areaMode: StationAreaMode;
  chargingSpeeds?: SpeedTierApiItem[];
  connectorTypes?: ConnectorTypeApiItem[];
  distanceKm: number;
  location: UserLocationSnapshot;
};

/**
 * The endpoint is now chosen by the driver's explicit area mode instead of
 * being inferred from whether any filter happened to be non-default. Connector
 * and speed filters apply to both endpoints, so they no longer force a
 * proximity query.
 */
async function loadSpkluStations({
  areaMode,
  chargingSpeeds = [],
  connectorTypes = [],
  distanceKm,
  location
}: LoadSpkluStationsOptions) {
  const connectorFilters = connectorTypes.filter((connector) => connector.name);
  const speedFilters = chargingSpeeds.filter((speedTier) => speedTier.id);
  const plan = getStationQueryPlan(areaMode, location, distanceKm);

  if (plan.endpoint === 'list') {
    const response = await fetchStations({
      connectorType: connectorFilters,
      limit: plan.limit,
      speedTier: speedFilters
    });

    return toUniqueStations(response.items);
  }

  const response = await fetchNearbyStations({
    lat: plan.latitude,
    lon: plan.longitude,
    radius: plan.radiusKm,
    connectorType: connectorFilters,
    speedTier: speedFilters,
    limit: plan.limit
  });

  return toUniqueStations(response).sort((left, right) => (left.distanceKm ?? 0) - (right.distanceKm ?? 0));
}

/** The same station can arrive from several sources, so the id wins. */
function toUniqueStations(items: StationApiItem[]): Station[] {
  const stationsById = new Map<string, Station>();

  items.forEach((item) => {
    const station = toStation(item);
    stationsById.set(station.id, station);
  });

  return Array.from(stationsById.values());
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
    province: item.province,
    availableConnectors: item.available_connectors ?? null,
    totalConnectors: item.total_connectors ?? null
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
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
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
  setDistanceKm: (distanceKm: DistanceOption) => void,
  setAreaMode: (mode: StationAreaMode) => void
) {
  setConnectorTypes([]);
  setChargingSpeeds([]);
  setDistanceKm(defaultDistanceKm);
  setAreaMode(defaultStationAreaMode);
}

/** Null hides the ring; a ring without a real fix would assert a place the driver is not. */
function getRadiusRingKm(
  mode: StationAreaMode,
  location: UserLocationSnapshot,
  distanceKm: DistanceOption
): number | null {
  return shouldShowRadiusRing(mode, location) ? distanceKm : null;
}

/** The slider reports a continuous value on web, so the index has to be snapped and bounded. */
function clampDistanceIndex(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }

  return Math.min(distanceOptions.length - 1, Math.max(0, Math.round(value)));
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
    height: expanded ? expandedHeights[mode] : mode === 'detail' ? collapsedDetailSheetHeight : collapsedSheetHeight,
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
