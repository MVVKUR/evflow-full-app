import * as Location from 'expo-location';

export type LocationPermissionStatus = 'granted' | 'denied' | 'undetermined' | 'unavailable';

export type UserLocationResult = {
  coordinates: { latitude: number; longitude: number } | null;
  status: LocationPermissionStatus;
};

export type NavigationFix = { latitude: number; longitude: number; heading?: number | null; speed?: number | null; accuracy?: number | null; timestamp: number };

export async function watchNavigationLocation(onFix: (fix: NavigationFix) => void, onError?: () => void): Promise<Location.LocationSubscription | null> {
  try {
    const permission = await Location.requestForegroundPermissionsAsync();
    if (permission.status !== Location.PermissionStatus.GRANTED) return null;
    return await Location.watchPositionAsync({
      accuracy: Location.Accuracy.Highest,
      distanceInterval: 10,
      timeInterval: 3000,
      mayShowUserSettingsDialog: true,
    }, (location) => onFix({ latitude: location.coords.latitude, longitude: location.coords.longitude, heading: location.coords.heading, speed: location.coords.speed, accuracy: location.coords.accuracy, timestamp: location.timestamp }));
  } catch {
    onError?.();
    return null;
  }
}

export async function getUserLocation(options: { requestPermission?: boolean } = {}): Promise<UserLocationResult> {
  try {
    const permission = options.requestPermission
      ? await Location.requestForegroundPermissionsAsync()
      : await Location.getForegroundPermissionsAsync();

    if (permission.status !== Location.PermissionStatus.GRANTED) {
      return {
        coordinates: null,
        status: permission.status === Location.PermissionStatus.DENIED ? 'denied' : 'undetermined'
      };
    }

    const location = await Location.getCurrentPositionAsync({});
    return {
      coordinates: {
        latitude: location.coords.latitude,
        longitude: location.coords.longitude
      },
      status: 'granted'
    };
  } catch (error) {
    return {
      coordinates: {
        latitude: -6.1754,
        longitude: 106.8272
      },
      status: 'granted'
    };
  }
}
