import { beforeEach, describe, expect, it } from 'vitest';
import { defaultDistanceKm, defaultStationAreaMode } from './areaFilterMode';
import {
  clearStationAreaSelection,
  parseStationAreaSelection,
  readStationAreaSelection,
  saveStationAreaSelection,
  type SessionStorageLike
} from './areaFilterSession';

function createStorage(seed: Record<string, string> = {}): SessionStorageLike & { entries: Map<string, string> } {
  const entries = new Map<string, string>(Object.entries(seed));

  return {
    entries,
    getItem: (key) => entries.get(key) ?? null,
    removeItem: (key) => {
      entries.delete(key);
    },
    setItem: (key, value) => {
      entries.set(key, value);
    }
  };
}

function createThrowingStorage(): SessionStorageLike {
  return {
    getItem: () => {
      throw new Error('storage blocked');
    },
    removeItem: () => {
      throw new Error('storage blocked');
    },
    setItem: () => {
      throw new Error('storage blocked');
    }
  };
}

describe('station area selection session', () => {
  beforeEach(() => {
    clearStationAreaSelection(createStorage());
  });

  it('defaults to the always-satisfiable mode when nothing is stored', () => {
    expect(readStationAreaSelection(createStorage())).toEqual({
      distanceKm: defaultDistanceKm,
      mode: defaultStationAreaMode
    });
  });

  it('survives an unmount and remount of the screen', () => {
    const storage = createStorage();
    saveStationAreaSelection({ distanceKm: 3, mode: 'near' }, storage);

    // A remount reads from storage rather than from the previous component state.
    clearMemoryOnly();
    expect(readStationAreaSelection(storage)).toEqual({ distanceKm: 3, mode: 'near' });
  });

  it('keeps the choice in memory when storage is unavailable, as on native', () => {
    saveStationAreaSelection({ distanceKm: 10, mode: 'near' }, null);

    expect(readStationAreaSelection(null)).toEqual({ distanceKm: 10, mode: 'near' });
  });

  it('keeps the choice in memory when storage throws', () => {
    const storage = createThrowingStorage();
    saveStationAreaSelection({ distanceKm: 5, mode: 'near' }, storage);

    expect(readStationAreaSelection(storage)).toEqual({ distanceKm: 5, mode: 'near' });
  });

  it('falls back to the default when storage throws on read', () => {
    expect(readStationAreaSelection(createThrowingStorage())).toEqual({
      distanceKm: defaultDistanceKm,
      mode: defaultStationAreaMode
    });
  });

  it('returns a copy so a caller cannot mutate the stored selection', () => {
    const storage = createStorage();
    saveStationAreaSelection({ distanceKm: 3, mode: 'near' }, storage);

    const first = readStationAreaSelection(storage);
    first.mode = 'all';
    first.distanceKm = 10;

    expect(readStationAreaSelection(storage)).toEqual({ distanceKm: 3, mode: 'near' });
  });

  it('clears both the memory copy and the stored copy', () => {
    const storage = createStorage();
    saveStationAreaSelection({ distanceKm: 3, mode: 'near' }, storage);

    clearStationAreaSelection(storage);

    expect(storage.entries.size).toBe(0);
    expect(readStationAreaSelection(storage)).toEqual({
      distanceKm: defaultDistanceKm,
      mode: defaultStationAreaMode
    });
  });
});

describe('stored selection parsing', () => {
  it('reads back a valid record', () => {
    expect(parseStationAreaSelection('{"mode":"near","distanceKm":10}')).toEqual({ distanceKm: 10, mode: 'near' });
  });

  it.each([
    ['missing value', null],
    ['empty string', ''],
    ['malformed json', '{not json'],
    ['a json array', '[]'],
    ['a json null', 'null'],
    ['a json string', '"near"'],
    ['an unknown mode', '{"mode":"everywhere","distanceKm":3}'],
    ['no mode at all', '{"distanceKm":3}']
  ])('rejects %s', (_label, rawSelection) => {
    expect(parseStationAreaSelection(rawSelection)).toBeNull();
  });

  it.each([
    ['a distance the slider cannot show', '{"mode":"near","distanceKm":7}'],
    ['a string distance', '{"mode":"near","distanceKm":"3"}'],
    ['a missing distance', '{"mode":"near"}']
  ])('keeps the mode but repairs %s', (_label, rawSelection) => {
    expect(parseStationAreaSelection(rawSelection)).toEqual({ distanceKm: defaultDistanceKm, mode: 'near' });
  });
});

/** Simulates a screen remount: component state is gone, session storage is not. */
function clearMemoryOnly() {
  clearStationAreaSelection(null);
}
