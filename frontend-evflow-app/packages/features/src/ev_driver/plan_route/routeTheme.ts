export const routeColors = {
  brand: '#008A91',
  brandDark: '#00676D',
  brandSoft: '#D8F1F2',
  success: '#08A65C',
  successSoft: '#ECFAF3',
  warning: '#ED7100',
  warningSoft: '#FFF5EC',
  error: '#D5252A',
  errorSoft: '#FFF0F0',
  surface: '#FFFFFF',
  onBrand: '#FFFFFF',
  surfaceSecondary: '#F4F7F7',
  control: '#E7ECED',
  mapFallback: '#E8F0ED',
  textPrimary: '#20292D',
  textSecondary: '#66747B',
  border: '#D5DFE1',
  handle: '#B9C5C7',
  errorBorder: '#F1B4B6',
  disabled: '#D9E0E2',
  overlay: 'rgba(25, 42, 44, 0.34)',
} as const;

export const routeSpacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 28 } as const;
export const routeRadius = { sm: 10, md: 14, lg: 20, sheet: 28, pill: 999 } as const;
export const routeShadow = {
  shadowColor: '#142B2D',
  shadowOffset: { width: 0, height: 5 },
  shadowOpacity: 0.14,
  shadowRadius: 16,
  elevation: 8,
} as const;
