const SVG_NS = 'xmlns="http://www.w3.org/2000/svg"';

export const menuIconSvg =
  `<svg width="22" height="22" viewBox="0 0 22 22" fill="none" ${SVG_NS}><path d="M3 6H19M3 11H19M3 16H19" stroke="#191C1E" stroke-width="2" stroke-linecap="round"/></svg>`;

export const bellIconSvg =
  `<svg width="18" height="18" viewBox="0 0 18 18" fill="none" ${SVG_NS}><path d="M9 2C6.24 2 4 4.24 4 7V10.6L2.6 13.35C2.28 13.99 2.72 14.7 3.42 14.7H14.58C15.28 14.7 15.72 13.99 15.4 13.35L14 10.6V7C14 4.24 11.76 2 9 2Z" stroke="#3D494B" stroke-width="1.6" stroke-linejoin="round"/><path d="M7.4 16.4C7.72 16.98 8.32 17.35 9 17.35C9.68 17.35 10.28 16.98 10.6 16.4" stroke="#3D494B" stroke-width="1.6" stroke-linecap="round"/></svg>`;

export const plusIconSvg =
  `<svg width="22" height="22" viewBox="0 0 22 22" fill="none" ${SVG_NS}><path d="M11 4V18M4 11H18" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round"/></svg>`;

export type BusinessNavIconName = 'overview' | 'stations' | 'planner' | 'customers' | 'reports';

const navIconBodies: Record<BusinessNavIconName, (color: string) => string> = {
  overview: (color) =>
    `<rect x="3" y="3" width="6" height="6" rx="1.2" stroke="${color}" stroke-width="1.7"/><rect x="11" y="3" width="6" height="6" rx="1.2" stroke="${color}" stroke-width="1.7"/><rect x="3" y="11" width="6" height="6" rx="1.2" stroke="${color}" stroke-width="1.7"/><rect x="11" y="11" width="6" height="6" rx="1.2" stroke="${color}" stroke-width="1.7"/>`,
  stations: (color) =>
    `<path d="M11 1.5L4 11H9L8 18.5L16 8.5H10.5L11 1.5Z" fill="${color}"/>`,
  planner: (color) =>
    `<path d="M10 18C10 18 16 12.6 16 8.2C16 4.8 13.3 2 10 2C6.7 2 4 4.8 4 8.2C4 12.6 10 18 10 18Z" stroke="${color}" stroke-width="1.7" stroke-linejoin="round"/><circle cx="10" cy="8.2" r="2.2" stroke="${color}" stroke-width="1.7"/>`,
  customers: (color) =>
    `<circle cx="7" cy="6.8" r="2.8" stroke="${color}" stroke-width="1.7"/><path d="M2 17C2 14.2 4.2 12.4 7 12.4C9.8 12.4 12 14.2 12 17" stroke="${color}" stroke-width="1.7" stroke-linecap="round"/><circle cx="14.2" cy="7.6" r="2.2" stroke="${color}" stroke-width="1.7"/><path d="M14 12.6C16.3 12.9 18 14.6 18 17" stroke="${color}" stroke-width="1.7" stroke-linecap="round"/>`,
  reports: (color) =>
    `<path d="M5 2H12L16 6V18H5V2Z" stroke="${color}" stroke-width="1.7" stroke-linejoin="round"/><path d="M8 9.5H13M8 13H13" stroke="${color}" stroke-width="1.7" stroke-linecap="round"/>`
};

export function buildNavIconSvg(name: BusinessNavIconName, color: string): string {
  return `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" ${SVG_NS}>${navIconBodies[name](color)}</svg>`;
}

const DONUT_SIZE = 112;
const DONUT_STROKE_WIDTH = 12;

export function buildDonutSvg(percent: number): string {
  const center = DONUT_SIZE / 2;
  const radius = (DONUT_SIZE - DONUT_STROKE_WIDTH) / 2;
  const circumference = 2 * Math.PI * radius;
  const arcLength = circumference * (Math.min(Math.max(percent, 0), 100) / 100);

  return (
    `<svg width="${DONUT_SIZE}" height="${DONUT_SIZE}" viewBox="0 0 ${DONUT_SIZE} ${DONUT_SIZE}" fill="none" ${SVG_NS}>` +
    `<circle cx="${center}" cy="${center}" r="${radius}" stroke="#E2E8EA" stroke-width="${DONUT_STROKE_WIDTH}"/>` +
    `<circle cx="${center}" cy="${center}" r="${radius}" stroke="#006973" stroke-width="${DONUT_STROKE_WIDTH}" stroke-linecap="round" stroke-dasharray="${arcLength.toFixed(2)} ${circumference.toFixed(2)}" transform="rotate(-90 ${center} ${center})"/>` +
    '</svg>'
  );
}
