export type LocationPermissionStatus = 'granted' | 'denied' | 'undetermined' | 'unavailable' | 'gps_error';

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

/**
 * Origin of the simulated navigation stream below. It is NOT a stand-in for
 * the driver: getUserLocation deliberately never returns it, because reporting
 * an invented position as a real fix is indistinguishable to the caller from a
 * successful read. Only watchNavigationLocation still walks from this point,
 * and that is a separately tracked defect.
 */
const defaultWebLocation = {
  latitude: -6.1754,
  longitude: 106.8272
};

/** Documented GeolocationPositionError codes; the constant is not defined in non-browser runtimes. */
const permissionDeniedCode = 1;
const positionUnavailableCode = 2;
const timeoutCode = 3;

/**
 * Translate a browser geolocation failure into the status union.
 *
 * The distinction matters downstream: a denial is a decision the driver made
 * and the UI should stop asking, while an unavailable position or a timeout is
 * a transient hardware failure the driver can retry. Collapsing both into one
 * status is what previously made every failure look alike.
 *
 * Exported so it can be tested as the total function it is, rather than only
 * through the promise that wraps the geolocation callback.
 */
export function geolocationErrorStatus(code: number): LocationPermissionStatus {
  if (code === permissionDeniedCode) {
    return 'denied';
  }

  if (code === positionUnavailableCode || code === timeoutCode) {
    return 'gps_error';
  }

  return 'gps_error';
}

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

/**
 * Read the driver's position, or say honestly why it could not be read.
 *
 * This function never invents coordinates. Every failure path resolves with
 * `coordinates: null` and the status that describes the failure, so a caller
 * can tell "the driver is here" apart from "we do not know where the driver
 * is". The previous implementation resolved every failure with hardcoded
 * Jakarta coordinates and status 'granted', which meant no caller on web could
 * ever detect a missing fix: distance sorting, the radius ring and the "you are
 * here" pin were all drawn around a place the driver had never been.
 *
 * When `requestPermission` is falsy this is a silent read: it will not raise
 * the browser permission prompt. That matters because a browser denial is
 * sticky per origin, so the prompt must be spent on an explicit driver action
 * rather than on page load.
 */
export async function getUserLocation(options: { requestPermission?: boolean } = {}): Promise<UserLocationResult> {
  return new Promise((resolve) => {
    const resolveUnlocated = (status: LocationPermissionStatus) => {
      resolve({ coordinates: null, status });
    };

    // Server-side render, or any runtime without the browser globals.
    if (typeof window === 'undefined' || typeof navigator === 'undefined') {
      return resolveUnlocated('unavailable');
    }

    // Browsers gate geolocation behind HTTPS, so on plain http:// the API is
    // present but permanently unusable. That is 'unavailable', not a denial.
    if (!window.isSecureContext) {
      return resolveUnlocated('unavailable');
    }

    if (!navigator.geolocation) {
      return resolveUnlocated('unavailable');
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
        resolveUnlocated(geolocationErrorStatus(error.code));
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

    // From here the caller asked for a silent read. getCurrentPosition raises
    // the permission prompt whenever the state is 'prompt', so it may only be
    // reached once the Permissions API has confirmed an existing grant.
    if (!navigator.permissions?.query) {
      return resolveUnlocated('undetermined');
    }

    navigator.permissions
      .query({ name: 'geolocation' })
      .then((permission) => {
        if (permission.state === 'granted') {
          readCurrentPosition();
          return;
        }

        resolveUnlocated(permission.state === 'denied' ? 'denied' : 'undetermined');
      })
      .catch(() => {
        // Some browsers reject the 'geolocation' descriptor outright. We
        // genuinely cannot tell whether permission exists, and guessing
        // 'denied' would suppress the prompt the driver still needs.
        resolveUnlocated('undetermined');
      });
  });
}
