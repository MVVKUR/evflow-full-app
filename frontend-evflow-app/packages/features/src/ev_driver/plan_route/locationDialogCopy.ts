import type { LocationPermissionStatus } from '../utils/location';

export type LocationDialogCopy = {
  title: string;
  body: string;
  hint: string;
  primaryLabel: string;
};

/**
 * What the location dialog says, given the status and whether the driver has
 * already pressed the button.
 *
 * The first showing is an invitation. Every showing AFTER a failed attempt has
 * to explain what went wrong, because otherwise pressing "Allow location" with
 * location disabled in the OS repaints identical words and reads as a broken
 * button -- the browser answers instantly from a remembered denial and never
 * shows a prompt.
 */
export function getLocationDialogCopy(
  status: LocationPermissionStatus | null,
  attempts: number
): LocationDialogCopy {
  const retry = attempts > 0;

  if (status === 'gps_error') {
    return {
      title: 'Location unavailable',
      body: retry
        ? 'GPS still could not fix your position. This usually clears indoors near a window, or you can set the starting point yourself.'
        : 'GPS could not determine your location. Retry or choose a starting point manually.',
      hint: 'You can continue without granting permission.',
      primaryLabel: retry ? 'Try again' : 'Allow location',
    };
  }

  if (status === 'unavailable') {
    return {
      title: 'Location is switched off',
      body: 'Location services are turned off for this device, so the browser cannot share a position even after you allow it. Turn location on in your system settings, or set the starting point yourself.',
      hint: 'Setting the origin manually works just as well.',
      primaryLabel: 'Try again',
    };
  }

  if (status === 'denied') {
    return {
      title: 'Location permission blocked',
      body: 'This site is blocked from using your location, so the request was refused without asking. Allow location for this site in your browser settings (the icon at the left of the address bar), then try again.',
      hint: 'Setting the origin manually works just as well.',
      primaryLabel: 'Try again',
    };
  }

  return {
    title: 'Location access needed',
    body: retry
      ? 'No position came back. Your browser may have dismissed the prompt — try again, or set the starting point yourself.'
      : 'EV-FLOW uses your location as the route origin. Raw coordinates are not stored by the frontend.',
    hint: 'You can continue without granting permission.',
    primaryLabel: retry ? 'Try again' : 'Allow location',
  };
}
