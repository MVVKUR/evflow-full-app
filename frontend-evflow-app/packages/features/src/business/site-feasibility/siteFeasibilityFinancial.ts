import {
  fetchPlannerRoi,
  type PlannerRoiInput,
  type PlannerRoiResponse
} from '@evflow/shared';
import type { FinancialProjection } from './siteFeasibilityTypes';

export const DEMO_PLANNER_ROI_ASSUMPTIONS = {
  capex_per_connector_idr: 250_000_000,
  opex_monthly_idr: 15_000_000,
  utilisation_target: 0.2,
  connectors: 2,
  power_kw: 60,
  energy_per_session_kwh: 30,
  energy_cost_idr_per_kwh: 1450,
  horizon_years: 10
} satisfies Omit<PlannerRoiInput, 'cell_id'>;

export function isMockOptimalSiteId(siteId: string) {
  return siteId.startsWith('mock-optimal-');
}

export function getSiteFinancialLifecycleKey(siteId: string | null, retry: number) {
  return siteId === null ? null : `${siteId}:${retry}`;
}

export async function getSiteFinancialProjection(siteId: string): Promise<FinancialProjection> {
  if (isMockOptimalSiteId(siteId)) {
    throw new Error('Mock sites use their dedicated mock financial projection.');
  }

  return plannerRoiToFinancialProjection(await fetchPlannerRoi({
    cell_id: siteId,
    ...DEMO_PLANNER_ROI_ASSUMPTIONS
  }));
}

export function plannerRoiToFinancialProjection(response: PlannerRoiResponse): FinancialProjection {
  return {
    sessionsPerDay: response.sessions_per_day,
    energyPerDayKwh: response.sessions_per_day * response.inputs.energy_per_session_kwh,
    monthlyRevenueIdr: response.revenue_monthly_idr,
    paybackYears: response.payback_years,
    breaksEven: response.breaks_even,
    utilisation: response.utilisation,
    capacitySessionsPerDay: response.capacity_sessions_per_day,
    demandBasis: response.demand_basis,
    costBasis: response.cost_basis,
    inputSources: response.input_sources,
    projectionKind: 'backend'
  };
}

export function getPaybackProjectionCopy(financial: FinancialProjection) {
  if (!financial.breaksEven || financial.paybackYears === null) {
    return { supporting: 'Does not break even', value: 'No Payback' };
  }

  const supporting = financial.paybackYears < 3
    ? 'Rapid capital recovery'
    : financial.paybackYears <= 5
      ? 'Standard capital recovery'
      : 'Long-term capital recovery';
  return { supporting, value: `${financial.paybackYears.toFixed(1)} Yrs` };
}
