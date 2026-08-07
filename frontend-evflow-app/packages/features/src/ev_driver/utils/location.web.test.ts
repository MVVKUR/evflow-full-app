import { afterEach, describe, expect, it, vi } from 'vitest';
import { geolocationErrorStatus, getUserLocation } from './location.web';

/**
 * The coordinates the old implementation handed back, labelled 'granted', on
 * every failure path. Nothing may return them any more, so the value is kept
 * here purely as the thing to assert against.
 */
const fabricatedJakarta = { latitude: -6.1754, longitude: 106.8272 };

type PermissionOutcome = 'granted' | 'denied' | 'prompt' | 'reject';

type GeolocationBehaviour =
  | { kind: 'success'; latitude: number; longitude: number }
  | { kind: 'error'; code: number };

type BrowserOptions = {
  isSecureContext?: boolean;
  geolocation?: GeolocationBehaviour | 'missing';
  permissions?: PermissionOutcome | 'missing' | 'query_missing';
};

/** Records whether the call that raises the browser prompt was reached. */
type BrowserHandle = { readCount: () => number };

const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');

function setGlobal(name: string, value: unknown): void {
  Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
}

function positionFixture(latitude: number, longitude: number): GeolocationPosition {
  return {
    coords: { latitude, longitude, accuracy: 5, altitude: null, altitudeAccuracy: null, heading: null, speed: null },
    timestamp: 1_700_000_000_000
  } as unknown as GeolocationPosition;
}

function errorFixture(code: number): GeolocationPositionError {
  return { code, message: 'stub', PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 } as unknown as GeolocationPositionError;
}

function installBrowser(options: BrowserOptions = {}): BrowserHandle {
  const { isSecureContext = true, geolocation = { kind: 'success', latitude: -6.9147, longitude: 107.6098 }, permissions = 'granted' } = options;

  let reads = 0;

  const geolocationStub = geolocation === 'missing'
    ? undefined
    : {
        getCurrentPosition: (onSuccess: PositionCallback, onError?: PositionErrorCallback | null) => {
          reads += 1;
          if (geolocation.kind === 'success') {
            onSuccess(positionFixture(geolocation.latitude, geolocation.longitude));
            return;
          }
          onError?.(errorFixture(geolocation.code));
        },
        watchPosition: () => 0,
        clearWatch: () => undefined
      };

  const permissionsStub = permissions === 'missing'
    ? undefined
    : permissions === 'query_missing'
      ? {}
      : {
          query: () => (permissions === 'reject'
            ? Promise.reject(new TypeError("'geolocation' is not a valid permission name"))
            : Promise.resolve({ state: permissions }))
        };

  setGlobal('window', { isSecureContext });
  setGlobal('navigator', { geolocation: geolocationStub, permissions: permissionsStub });

  return { readCount: () => reads };
}

function restoreGlobal(name: string, descriptor: PropertyDescriptor | undefined): void {
  if (descriptor) {
    Object.defineProperty(globalThis, name, descriptor);
    return;
  }
  Reflect.deleteProperty(globalThis, name);
}

afterEach(() => {
  restoreGlobal('navigator', originalNavigator);
  restoreGlobal('window', originalWindow);
  vi.restoreAllMocks();
});

describe('geolocationErrorStatus', () => {
  it('reports a permission denial as a denial', () => {
    expect(geolocationErrorStatus(1)).toBe('denied');
  });

  it('reports an unavailable position as a GPS error, not a denial', () => {
    expect(geolocationErrorStatus(2)).toBe('gps_error');
  });

  it('reports a timeout as a GPS error, so the driver is offered a retry', () => {
    expect(geolocationErrorStatus(3)).toBe('gps_error');
  });

  it('treats an unrecognised code as a GPS error rather than assuming consent was refused', () => {
    expect(geolocationErrorStatus(0)).toBe('gps_error');
    expect(geolocationErrorStatus(99)).toBe('gps_error');
  });
});

describe('getUserLocation: environments without usable geolocation', () => {
  it('reports "unavailable" with no coordinates when there is no window', async () => {
    installBrowser();
    Reflect.deleteProperty(globalThis, 'window');

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'unavailable' });
  });

  it('reports "unavailable" with no coordinates when there is no navigator', async () => {
    installBrowser();
    Reflect.deleteProperty(globalThis, 'navigator');

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'unavailable' });
  });

  it('reports "unavailable" on an insecure origin instead of inventing a position', async () => {
    installBrowser({ isSecureContext: false });

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'unavailable' });
  });

  it('reports "unavailable" when the geolocation API is missing', async () => {
    installBrowser({ geolocation: 'missing' });

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'unavailable' });
  });

  it('does not log the missing fix to the console', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    installBrowser({ isSecureContext: false });

    await getUserLocation();

    expect(warn).not.toHaveBeenCalled();
  });
});

describe('getUserLocation: explicit permission request', () => {
  it('returns the real fix when the driver allows the prompt', async () => {
    installBrowser({ geolocation: { kind: 'success', latitude: -7.2575, longitude: 112.7521 } });

    expect(await getUserLocation({ requestPermission: true })).toEqual({
      coordinates: { latitude: -7.2575, longitude: 112.7521 },
      status: 'granted'
    });
  });

  it('reports a denial as "denied" so the caller stops asking', async () => {
    installBrowser({ geolocation: { kind: 'error', code: 1 } });

    expect(await getUserLocation({ requestPermission: true })).toEqual({ coordinates: null, status: 'denied' });
  });

  it('reports an unavailable position as "gps_error"', async () => {
    installBrowser({ geolocation: { kind: 'error', code: 2 } });

    expect(await getUserLocation({ requestPermission: true })).toEqual({ coordinates: null, status: 'gps_error' });
  });

  it('reports a timeout as "gps_error"', async () => {
    installBrowser({ geolocation: { kind: 'error', code: 3 } });

    expect(await getUserLocation({ requestPermission: true })).toEqual({ coordinates: null, status: 'gps_error' });
  });
});

describe('getUserLocation: silent read must not raise the prompt', () => {
  it('returns the fix without prompting when permission was already granted', async () => {
    const browser = installBrowser({ permissions: 'granted', geolocation: { kind: 'success', latitude: -6.2, longitude: 106.8 } });

    expect(await getUserLocation()).toEqual({
      coordinates: { latitude: -6.2, longitude: 106.8 },
      status: 'granted'
    });
    expect(browser.readCount()).toBe(1);
  });

  it('reports "denied" without reading when permission was refused', async () => {
    const browser = installBrowser({ permissions: 'denied' });

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'denied' });
    expect(browser.readCount()).toBe(0);
  });

  it('reports "undetermined" without reading when permission has not been decided', async () => {
    const browser = installBrowser({ permissions: 'prompt' });

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'undetermined' });
    expect(browser.readCount()).toBe(0);
  });

  it('reports "undetermined" without reading when the Permissions API is absent', async () => {
    const browser = installBrowser({ permissions: 'missing' });

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'undetermined' });
    expect(browser.readCount()).toBe(0);
  });

  it('reports "undetermined" without reading when the Permissions API has no query', async () => {
    const browser = installBrowser({ permissions: 'query_missing' });

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'undetermined' });
    expect(browser.readCount()).toBe(0);
  });

  it('reports "undetermined" when the permission query rejects the geolocation descriptor', async () => {
    const browser = installBrowser({ permissions: 'reject' });

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'undetermined' });
    expect(browser.readCount()).toBe(0);
  });

  it('still surfaces a read failure that happens after a confirmed grant', async () => {
    installBrowser({ permissions: 'granted', geolocation: { kind: 'error', code: 2 } });

    expect(await getUserLocation()).toEqual({ coordinates: null, status: 'gps_error' });
  });
});

describe('getUserLocation never fabricates a position', () => {
  const failingEnvironments: ReadonlyArray<{ name: string; options: BrowserOptions; requestPermission: boolean }> = [
    { name: 'insecure origin', options: { isSecureContext: false }, requestPermission: false },
    { name: 'no geolocation API', options: { geolocation: 'missing' }, requestPermission: false },
    { name: 'permission denied', options: { permissions: 'denied' }, requestPermission: false },
    { name: 'permission undecided', options: { permissions: 'prompt' }, requestPermission: false },
    { name: 'permission query rejected', options: { permissions: 'reject' }, requestPermission: false },
    { name: 'no Permissions API', options: { permissions: 'missing' }, requestPermission: false },
    { name: 'prompt refused', options: { geolocation: { kind: 'error', code: 1 } }, requestPermission: true },
    { name: 'position unavailable', options: { geolocation: { kind: 'error', code: 2 } }, requestPermission: true },
    { name: 'read timed out', options: { geolocation: { kind: 'error', code: 3 } }, requestPermission: true }
  ];

  it.each(failingEnvironments)('returns null coordinates and never "granted" for: $name', async ({ options, requestPermission }) => {
    installBrowser(options);

    const result = await getUserLocation({ requestPermission });

    expect(result.coordinates).toBeNull();
    expect(result.status).not.toBe('granted');
    expect(result.coordinates).not.toEqual(fabricatedJakarta);
  });
});
