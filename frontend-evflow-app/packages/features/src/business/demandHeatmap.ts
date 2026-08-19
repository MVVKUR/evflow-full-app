import type { LeafletMapMarker, LeafletPolygonLayer, MapViewport } from '@evflow/ui';

export type DemandPriority = 'high' | 'moderate' | 'low';
export type PlannerLayerKey = 'optimalSites' | 'demandHeatmap' | 'existingSpklus' | 'commercialPois' | 'populationDensity' | 'landUse';
export type PlannerLayerState = Record<PlannerLayerKey, boolean>;
export type OptimalSite = { id: string; latitude: number; longitude: number; score: number; district: string };

export const defaultPlannerLayers: PlannerLayerState = {
  optimalSites: true, demandHeatmap: true, existingSpklus: false, commercialPois: false, populationDensity: false, landUse: false
};

export const jakartaViewport: MapViewport = { north: -6.06, south: -6.38, east: 106.98, west: 106.62, zoom: 11 };

const demandZones: Array<{ id: string; priority: DemandPriority; coordinates: Array<[number, number]> }> = [
  { id: 'central-gap', priority: 'high', coordinates: [[-6.12, 106.79], [-6.12, 106.87], [-6.19, 106.87], [-6.19, 106.79]] },
  { id: 'south-growth', priority: 'high', coordinates: [[-6.21, 106.78], [-6.21, 106.86], [-6.29, 106.86], [-6.29, 106.78]] },
  { id: 'west-corridor', priority: 'moderate', coordinates: [[-6.14, 106.67], [-6.14, 106.76], [-6.25, 106.76], [-6.25, 106.67]] },
  { id: 'east-network', priority: 'moderate', coordinates: [[-6.17, 106.88], [-6.17, 106.96], [-6.28, 106.96], [-6.28, 106.88]] },
  { id: 'north-covered', priority: 'low', coordinates: [[-6.06, 106.76], [-6.06, 106.86], [-6.12, 106.86], [-6.12, 106.76]] }
];

const priorityColors: Record<DemandPriority, string> = { high: '#ef4444', moderate: '#f59e0b', low: '#10b981' };
export function prioritySemanticCategory(priority: DemandPriority) { return priority === 'high' ? 'High Priority' : priority === 'moderate' ? 'Moderate Priority' : 'Low Priority'; }
export function viabilityTier(score: number) { return score >= 85 && score <= 100 ? 1 : score >= 70 && score <= 84 ? 2 : null; }

export function generateMockOptimalSites(viewport: MapViewport): OptimalSite[] {
  const templates = [[0.2, 0.28, 94], [0.68, 0.24, 88], [0.48, 0.6, 82], [0.25, 0.78, 76], [0.77, 0.72, 72]] as const;
  return templates.map(([x, y, score], index) => ({
    id: `mock-optimal-${score}`, district: ['Central Jakarta', 'North Jakarta', 'South Jakarta', 'West Jakarta', 'East Jakarta'][index], score,
    latitude: viewport.south + (viewport.north - viewport.south) * y,
    longitude: viewport.west + (viewport.east - viewport.west) * x
  }));
}

export function demandHeatmapPolygons(): LeafletPolygonLayer[] {
  return demandZones.map((zone) => ({ id: zone.id, coordinates: zone.coordinates, fillColor: priorityColors[zone.priority], fillOpacity: 0.28, color: priorityColors[zone.priority], weight: 1 }));
}

export function plannerPolygons(
  layers: PlannerLayerState,
  overlays: {
    commercialPois?: LeafletPolygonLayer[];
    demandHeatmap?: LeafletPolygonLayer[];
    landUse?: LeafletPolygonLayer[];
    populationDensity?: LeafletPolygonLayer[];
  } = {}
): LeafletPolygonLayer[] {
  return [
    ...(layers.landUse ? overlays.landUse ?? [] : []),
    ...(layers.populationDensity ? overlays.populationDensity ?? [] : []),
    ...(layers.demandHeatmap ? overlays.demandHeatmap ?? demandHeatmapPolygons() : []),
    ...(layers.commercialPois ? overlays.commercialPois ?? [] : [])
  ];
}
export function plannerMarkers(
  layers: PlannerLayerState,
  sites: OptimalSite[],
  existingSpklus: LeafletMapMarker[] = []
): LeafletMapMarker[] {
  const recommendationMarkers = sites.map((site) => ({ id: site.id, label: `${site.district} · Viability ${site.score}`, latitude: site.latitude, longitude: site.longitude, iconSvg: scoreMarkerSvg(site.score) }));
  return [...(layers.existingSpklus ? existingSpklus : []), ...(layers.optimalSites ? recommendationMarkers : [])];
}
function scoreMarkerSvg(score: number) {
  const tier = viabilityTier(score); const fill = tier === 1 ? '#00a9e8' : '#f3f6fa'; const text = tier === 1 ? '#ffffff' : '#1f2937'; const stroke = tier === 1 ? '#ffffff' : '#64748b'; const halo = tier === 1 ? 'filter:drop-shadow(0 0 8px rgba(0,169,232,.72));' : 'filter:drop-shadow(0 2px 4px rgba(15,23,42,.28));';
  return `<div style="${halo}width:42px;height:42px;border-radius:21px;background:${fill};border:3px solid ${stroke};display:flex;align-items:center;justify-content:center;font:800 14px Arial;color:${text}">${score}</div>`;
}
