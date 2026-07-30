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

const defaultWebLocation = {
  latitude: -6.1754,
  longitude: 106.8272
};

/** Browser counterpart of Expo's location subscription with simulated GPS fallback for localhost/web development. */
export async function watchNavigationLocation(
  onFix: (fix: NavigationFix) => void,
  onError?: () => void
): Promise<NavigationLocationSubscription | null> {
  if (typeof window === 'undefined') {
    onError?.();
    return null;
  }

  const startSimulatedWatch = () => {
    console.warn("Using simulated GPS navigation stream for localhost/web.");
    let lat = defaultWebLocation.latitude;
    let lon = defaultWebLocation.longitude;
    const timerId = setInterval(() => {
      lat += 0.0001;
      lon += 0.0001;
      onFix({
        latitude: lat,
        longitude: lon,
        heading: 45,
        speed: 15,
        accuracy: 5,
        timestamp: Date.now(),
      });
    }, 2000);
    onFix({
      latitude: lat,
      longitude: lon,
      heading: 45,
      speed: 15,
      accuracy: 5,
      timestamp: Date.now(),
    });
    return { remove: () => clearInterval(timerId) };
  };

  if (!window.isSecureContext || !navigator.geolocation) {
    return startSimulatedWatch();
  }

  let usingFallback = false;
  let fallbackSub: NavigationLocationSubscription | null = null;

  const watchId = navigator.geolocation.watchPosition(
    (position) => {
      if (usingFallback) return;
      onFix({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        heading: position.coords.heading,
        speed: position.coords.speed,
        accuracy: position.coords.accuracy,
        timestamp: position.timestamp,
      });
    },
    () => {
      if (!usingFallback) {
        usingFallback = true;
        navigator.geolocation.clearWatch(watchId);
        fallbackSub = startSimulatedWatch();
      }
    },
    { enableHighAccuracy: true, maximumAge: 2000, timeout: 5000 }
  );

  return {
    remove: () => {
      navigator.geolocation.clearWatch(watchId);
      fallbackSub?.remove();
    }
  };
}

export async function getUserLocation(options: { requestPermission?: boolean } = {}): Promise<UserLocationResult> {
  return new Promise((resolve) => {
    const resolveFallback = () => {
      console.warn("GPS/Geolocation unavailable or blocked on localhost/web. Falling back to default Jakarta coordinates (-6.1754, 106.8272).");
      resolve({
        coordinates: {
          latitude: defaultWebLocation.latitude,
          longitude: defaultWebLocation.longitude
        },
        status: 'granted'
      });
    };

    if (typeof window !== 'undefined' && !window.isSecureContext) {
      return resolveFallback();
    }

    if (!navigator.geolocation) {
      return resolveFallback();
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
        resolveFallback();
      },
      {
        enableHighAccuracy: true,
        maximumAge: 10_000,
        timeout: 8_000
      }
    );

    if (options.requestPermission) {
      readCurrentPosition();
      return;
    }

    if (!navigator.permissions?.query) {
      readCurrentPosition();
      return;
    }

    navigator.permissions
      .query({ name: 'geolocation' })
      .then((permission) => {
        if (permission.state === 'granted') {
          readCurrentPosition();
          return;
        }
        resolveFallback();
      })
      .catch(() => {
        resolveFallback();
      });
  });
}
