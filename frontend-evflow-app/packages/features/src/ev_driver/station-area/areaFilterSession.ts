import {
  defaultDistanceKm,
  defaultStationAreaMode,
  isDistanceOption,
  isStationAreaMode,
  type DistanceOption,
  type StationAreaMode
} from './areaFilterMode';

/**
 * Session persistence for the area filter.
 *
 * EVDriverContainer swaps screens by conditional render, so DriverMapScreen
 * unmounts whenever the driver opens Wallet or Profile and loses all of its
 * state. Without this the area choice silently reverts every time they come
 * back. The in-memory-plus-sessionStorage shape mirrors
 * packages/shared/src/auth/session.ts so React Native, where sessionStorage
 * does not exist, still keeps the choice for as long as the app is running.
 */
export type StationAreaSelection = {
  mode: StationAreaMode;
  distanceKm: DistanceOption;
};

export type SessionStorageLike = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
};

const areaSelectionKey = 'evflow.driver.stationAreaFilter';

export const defaultStationAreaSelection: StationAreaSelection = {
  distanceKm: defaultDistanceKm,
  mode: defaultStationAreaMode
};

let memorySelection: StationAreaSelection | null = null;

export function saveStationAreaSelection(
  selection: StationAreaSelection,
  storage: SessionStorageLike | null = getSessionStorage()
): void {
  memorySelection = { ...selection };

  try {
    storage?.setItem(areaSelectionKey, JSON.stringify(selection));
  } catch {
    // Native and storage-restricted browsers fall back to the in-memory copy.
  }
}

/**
 * Returns the stored selection, or the default when nothing valid is stored.
 * A stored value is external input by the time it is read back, so both fields
 * are re-validated rather than trusted.
 */
export function readStationAreaSelection(
  storage: SessionStorageLike | null = getSessionStorage()
): StationAreaSelection {
  if (memorySelection) {
    return { ...memorySelection };
  }

  const stored = parseStationAreaSelection(readRawSelection(storage));

  if (!stored) {
    return { ...defaultStationAreaSelection };
  }

  memorySelection = stored;
  return { ...stored };
}

export function clearStationAreaSelection(
  storage: SessionStorageLike | null = getSessionStorage()
): void {
  memorySelection = null;

  try {
    storage?.removeItem(areaSelectionKey);
  } catch {
    // Nothing to recover: the in-memory copy is already cleared.
  }
}

export function parseStationAreaSelection(rawSelection: string | null): StationAreaSelection | null {
  if (!rawSelection) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(rawSelection);

    if (typeof parsed !== 'object' || parsed === null) {
      return null;
    }

    const candidate = parsed as Partial<Record<keyof StationAreaSelection, unknown>>;

    if (!isStationAreaMode(candidate.mode)) {
      return null;
    }

    return {
      // A distance outside the slider stops cannot be represented by the
      // control, so it falls back rather than desyncing the slider.
      distanceKm: isDistanceOption(candidate.distanceKm) ? candidate.distanceKm : defaultDistanceKm,
      mode: candidate.mode
    };
  } catch {
    return null;
  }
}

function readRawSelection(storage: SessionStorageLike | null): string | null {
  try {
    return storage?.getItem(areaSelectionKey) ?? null;
  } catch {
    return null;
  }
}

function getSessionStorage(): SessionStorageLike | null {
  if (typeof globalThis === 'undefined') {
    return null;
  }

  return globalThis.sessionStorage ?? null;
}
