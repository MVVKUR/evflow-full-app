import type {
  PlannerCandidateApi,
  PlannerCellsGeoJsonResponse,
  PlannerGeoJsonGeometry,
  StationApiItem
} from '@evflow/shared';
import type { LeafletMapMarker, LeafletPolygonLayer } from '@evflow/ui';
import type { DemandPriority, OptimalSite } from './demandHeatmap';

const priorityColors: Record<DemandPriority, string> = {
  high: '#ef4444',
  moderate: '#f59e0b',
  low: '#10b981'
};

export type PlannerLandUseMetric = 'commercial' | 'industrial' | 'residential' | 'retail';

const landUseColors: Record<PlannerLandUseMetric, string> = {
  commercial: '#0EA5E9',
  industrial: '#64748B',
  residential: '#8B5CF6',
  retail: '#F97316'
};

export function plannerCandidateToOptimalSite(candidate: PlannerCandidateApi): OptimalSite {
  return {
    id: candidate.cell_id,
    district: cleanAreaName(candidate.kota) ?? 'Jabodetabek',
    latitude: candidate.latitude,
    longitude: candidate.longitude,
    score: Math.round(clampUnit(candidate.score) * 100)
  };
}

export function plannerCellsToPolygons(response: PlannerCellsGeoJsonResponse): LeafletPolygonLayer[] {
  return response.features.flatMap((feature) => {
    const priority = scoreToDemandPriority(feature.properties.score ?? feature.properties.value ?? 0);
    return geometryOuterRings(feature.geometry).map((ring, index) => ({
      id: `${feature.properties.cell_id}-${index}`,
      coordinates: ring.map(([longitude, latitude]) => [latitude, longitude] as [number, number]),
      fillColor: priorityColors[priority],
      fillOpacity: 0.28,
      color: priorityColors[priority],
      weight: 0.6
    }));
  });
}

export function plannerCellsToMetricPolygons(
  response: PlannerCellsGeoJsonResponse,
  fillColor: string,
  idPrefix: string
): LeafletPolygonLayer[] {
  const values = response.features
    .map((feature) => feature.properties.value)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0);
  const maximum = Math.max(...values, 0);

  return response.features.flatMap((feature) => {
    const value = feature.properties.value ?? 0;
    if (value <= 0 || maximum <= 0) return [];
    const intensity = Math.sqrt(Math.min(value / maximum, 1));
    return geometryOuterRings(feature.geometry).map((ring, index) => ({
      id: `${idPrefix}-${feature.properties.cell_id}-${index}`,
      coordinates: toLeafletCoordinates(ring),
      fillColor,
      fillOpacity: 0.08 + intensity * 0.3,
      color: fillColor,
      weight: 0.35
    }));
  });
}

export function plannerLandUseToPolygons(
  responses: Partial<Record<PlannerLandUseMetric, PlannerCellsGeoJsonResponse>>
): LeafletPolygonLayer[] {
  const cells = new Map<string, {
    feature: PlannerCellsGeoJsonResponse['features'][number];
    metric: PlannerLandUseMetric;
    value: number;
  }>();

  (Object.entries(responses) as Array<[PlannerLandUseMetric, PlannerCellsGeoJsonResponse]>).forEach(([metric, response]) => {
    response.features.forEach((feature) => {
      const value = feature.properties.value ?? 0;
      const existing = cells.get(feature.properties.cell_id);
      if (value > 0 && (!existing || value > existing.value)) {
        cells.set(feature.properties.cell_id, { feature, metric, value });
      }
    });
  });

  return Array.from(cells.values()).flatMap(({ feature, metric, value }) =>
    geometryOuterRings(feature.geometry).map((ring, index) => ({
      id: `land-use-${feature.properties.cell_id}-${index}`,
      coordinates: toLeafletCoordinates(ring),
      fillColor: landUseColors[metric],
      fillOpacity: 0.12 + Math.min(value, 1) * 0.26,
      color: landUseColors[metric],
      weight: 0.4
    }))
  );
}

export function plannerStationsToMarkers(stations: StationApiItem[]): LeafletMapMarker[] {
  return stations.map((station) => ({
    id: `station:${station.id}`,
    label: station.name ?? 'Existing SPKLU',
    latitude: station.latitude,
    longitude: station.longitude,
    type: 'station'
  }));
}

export function scoreToDemandPriority(score: number): DemandPriority {
  if (score >= 0.75) return 'high';
  if (score >= 0.5) return 'moderate';
  return 'low';
}

export function plannerViewportBbox(viewport: { west: number; south: number; east: number; north: number }) {
  return `${viewport.west},${viewport.south},${viewport.east},${viewport.north}`;
}

function geometryOuterRings(geometry: PlannerGeoJsonGeometry): number[][][] {
  if (geometry.type === 'Polygon') {
    const polygon = geometry.coordinates as number[][][];
    return polygon.length ? [polygon[0] ?? []] : [];
  }
  const multiPolygon = geometry.coordinates as number[][][][];
  return multiPolygon.map((polygon) => polygon[0] ?? []).filter((ring) => ring.length > 0);
}

function toLeafletCoordinates(ring: number[][]): Array<[number, number]> {
  return ring.map(([longitude, latitude]) => [latitude, longitude]);
}

function cleanAreaName(value: string | null) {
  return value?.replace(/^(Kota|Kabupaten)\s+/i, '').trim() || null;
}

function clampUnit(value: number) {
  return Math.min(Math.max(value, 0), 1);
}
