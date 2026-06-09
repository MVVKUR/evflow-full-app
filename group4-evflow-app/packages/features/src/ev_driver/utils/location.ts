import * as Location from 'expo-location';

export type LocationPermissionStatus = 'granted' | 'denied' | 'undetermined' | 'unavailable';

export type UserLocationResult = {
  coordinates: { latitude: number; longitude: number } | null;
  status: LocationPermissionStatus;
};

export async function getUserLocation(options: { requestPermission?: boolean } = {}): Promise<UserLocationResult> {
  try {
    const permission = options.requestPermission
      ? await Location.requestForegroundPermissionsAsync()
      : await Location.getForegroundPermissionsAsync();

    if (permission.status !== Location.PermissionStatus.GRANTED) {
      console.log('Permission to access location was denied');
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
    console.error('Error getting location:', error);
    return {
      coordinates: null,
      status: 'unavailable'
    };
  }
}
