export type LocationPermissionStatus = 'granted' | 'denied' | 'undetermined' | 'unavailable';

export type UserLocationResult = {
  coordinates: { latitude: number; longitude: number } | null;
  status: LocationPermissionStatus;
};

export type NavigationFix = {
  latitude: number;
  longitude: number;
  heading?: number | null;
  speed?: number | null;
  accuracy?: number | null;
  timestamp: number;
};

export type NavigationLocationSubscription = { remove: () => void };

/** Browser counterpart of Expo's location subscription. */
export async function watchNavigationLocation(
  onFix: (fix: NavigationFix) => void,
  onError?: () => void
): Promise<NavigationLocationSubscription | null> {
  if (typeof window === 'undefined' || !window.isSecureContext || !navigator.geolocation) {
    onError?.();
    return null;
  }

  const watchId = navigator.geolocation.watchPosition(
    (position) => onFix({
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      heading: position.coords.heading,
      speed: position.coords.speed,
      accuracy: position.coords.accuracy,
      timestamp: position.timestamp,
    }),
    () => onError?.(),
    { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 }
  );

  return { remove: () => navigator.geolocation.clearWatch(watchId) };
}

export async function getUserLocation(options: { requestPermission?: boolean } = {}): Promise<UserLocationResult> {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined' && !window.isSecureContext) {
      resolve({ coordinates: null, status: 'unavailable' });
      return;
    }

    if (!navigator.geolocation) {
      return resolve({ coordinates: null, status: 'unavailable' });
    }

    const readCurrentPosition = () => navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          coordinates: {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude
          },
          status: 'granted'
        });
      },
      (error) => {
        resolve({
          coordinates: null,
          status: error.code === error.PERMISSION_DENIED ? 'denied' : 'unavailable'
        });
      }
    );

    if (options.requestPermission) {
      readCurrentPosition();
      return;
    }

    if (!navigator.permissions?.query) {
      resolve({ coordinates: null, status: 'undetermined' });
      return;
    }

    navigator.permissions
      .query({ name: 'geolocation' })
      .then((permission) => {
        if (permission.state === 'granted') {
          readCurrentPosition();
          return;
        }

        resolve({
          coordinates: null,
          status: permission.state === 'denied' ? 'denied' : 'undetermined'
        });
      })
      .catch(() => {
        resolve({ coordinates: null, status: 'undetermined' });
      });
  });
}
