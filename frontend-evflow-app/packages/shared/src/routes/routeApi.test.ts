import { describe, expect, it } from 'vitest';
import { normaliseRouteApiError, RouteApiError } from './routeApiError';

describe('route API error normalisation', () => {
  it('maps FastAPI 422 locations to route fields without object coercion', () => {
    const error = normaliseRouteApiError(422, { detail: [
      { loc: ['body', 'current_soc_pct'], msg: 'Input should be less than or equal to 100', input: 120 },
      { loc: ['body', 'destination'], msg: 'Outside the supported service area' },
      { loc: ['body', 'vehicle', 'usable_range_km'], msg: 'Must be greater than zero' },
    ] }, 'Invalid route');
    expect(error).toBeInstanceOf(RouteApiError);
    expect(error.status).toBe(422);
    expect(error.fieldErrors).toEqual({
      current_soc_pct: 'Input should be less than or equal to 100',
      destination: 'Outside the supported service area',
      vehicle: 'Must be greater than zero',
    });
    expect(error.message).not.toContain('[object Object]');
    expect(JSON.stringify(error.safeDetail)).not.toContain('120');
  });

  it('preserves a safe backend code and structured field errors', () => {
    const error = normaliseRouteApiError(422, { detail: { code: 'outside_service_area', message: 'Destination is unsupported', field_errors: { destination: 'Choose a supported destination' } } }, 'Invalid route');
    expect(error.code).toBe('outside_service_area');
    expect(error.fieldErrors.destination).toBe('Choose a supported destination');
  });
});
