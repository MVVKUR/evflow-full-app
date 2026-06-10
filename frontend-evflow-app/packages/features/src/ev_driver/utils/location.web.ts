export type LocationPermissionStatus = 'granted' | 'denied' | 'undetermined' | 'unavailable';

export type UserLocationResult = {
  coordinates: { latitude: number; longitude: number } | null;
  status: LocationPermissionStatus;
};

export async function getUserLocation(options: { requestPermission?: boolean } = {}): Promise<UserLocationResult> {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined' && !window.isSecureContext) {
      resolve({ coordinates: null, status: 'unavailable' });
      return;
    }

    if (!navigator.geolocation) {
      console.log('Geolocation is not supported by this browser.');
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
        console.error('Error getting location on web:', error);
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
