import { describe, expect, it, vi } from 'vitest';

vi.mock('react-native', () => ({ NativeModules: {} }));

import type { PlannerRoiResponse } from '@evflow/shared';
import {
  DEMO_PLANNER_ROI_ASSUMPTIONS,
  getPaybackProjectionCopy,
  getSiteFinancialLifecycleKey,
  getSiteFinancialProjection,
  isMockOptimalSiteId,
  plannerRoiToFinancialProjection
} from './siteFeasibilityFinancial';

const response: PlannerRoiResponse = {
  cell_id: 'JBDTBK_22219', kota: 'Kota Jakarta Timur', score: 0.91,
  population: 1000, poi_total: 20, station_count: 1, nearest_station_m: 500, stations_2km: 2,
  sessions_per_day: 19.2, sessions_per_month: 584.4, energy_per_month_kwh: 17532,
  capacity_sessions_per_day: 96, utilisation: 0.2,
  revenue_monthly_idr: 44_694_912, energy_cost_idr_per_kwh: 1450,
  energy_cost_monthly_idr: 25_421_400, opex_monthly_idr: 15_000_000,
  gross_margin_monthly_idr: 4_273_512, capex_total_idr: 500_000_000,
  payback_months: 117, payback_years: 9.75, net_at_horizon_idr: 12_821_440,
  breaks_even: true, horizon_years: 10,
  inputs: {
    connectors: 2, power_kw: 60, sessions_per_day: 19.2, energy_per_session_kwh: 30,
    capex_per_connector_idr: 250_000_000, opex_monthly_idr: 15_000_000,
    tariff_idr_per_kwh: 2480, admin_fee_idr: 2500, energy_cost_idr_per_kwh: 1450,
    horizon_years: 10
  },
  input_sources: {
    capex_per_connector_idr: 'planner', utilisation_target: 'planner',
    tariff_idr_per_kwh: 'charging tariff configuration'
  },
  demand_basis: 'Demand is an explicit planner utilisation assumption, not a forecast.',
  cost_basis: 'Energy purchase cost comes from the planner input.',
  provenance: { population_source: 'WorldPop', features_source: 'OSM', demand_basis: 'coverage', cell_size_m: 500 }
};

describe('site financial projection', () => {
  it('maps backend values and derives daily energy only from returned inputs', () => {
    const financial = plannerRoiToFinancialProjection(response);

    expect(financial).toMatchObject({
      sessionsPerDay: 19.2,
      energyPerDayKwh: 576,
      monthlyRevenueIdr: 44_694_912,
      paybackYears: 9.75,
      projectionKind: 'backend',
      inputSources: response.input_sources
    });
  });

  it('preserves a non-break-even result as nullable payback', () => {
    const financial = plannerRoiToFinancialProjection({
      ...response, payback_months: null, payback_years: null, breaks_even: false
    });
    expect(financial).toMatchObject({ paybackYears: null, breaksEven: false });
    expect(getPaybackProjectionCopy(financial)).toEqual({
      value: 'No Payback', supporting: 'Does not break even'
    });
  });

  it('centralizes the temporary demo assumptions and supplies exactly one demand basis', () => {
    expect(DEMO_PLANNER_ROI_ASSUMPTIONS).toMatchObject({
      capex_per_connector_idr: 250_000_000,
      opex_monthly_idr: 15_000_000,
      utilisation_target: 0.2
    });
    expect('sessions_per_day' in DEMO_PLANNER_ROI_ASSUMPTIONS).toBe(false);
  });

  it('does not send mock site IDs to the ROI endpoint', async () => {
    expect(isMockOptimalSiteId('mock-optimal-94')).toBe(true);
    await expect(getSiteFinancialProjection('mock-optimal-94'))
      .rejects.toThrow('Mock sites use their dedicated mock financial projection.');
  });

  it('requests ROI once across tab changes and once more for the next real site', () => {
    const tabs = ['feasibility', 'financial', 'nearby', 'financial'];
    let previousKey: string | null = null;
    let requests = 0;
    const openOrRender = (siteId: string | null, retry = 0) => {
      const key = getSiteFinancialLifecycleKey(siteId, retry);
      if (key !== previousKey) {
        previousKey = key;
        if (siteId && !isMockOptimalSiteId(siteId)) requests += 1;
      }
    };

    tabs.forEach(() => openOrRender('JBDTBK_22219'));
    expect(requests).toBe(1);

    openOrRender('JBDTBK_08697');
    expect(requests).toBe(2);

    openOrRender('mock-optimal-94');
    expect(requests).toBe(2);

    expect(getSiteFinancialLifecycleKey('JBDTBK_22219', 1)).toBe('JBDTBK_22219:1');
  });
});
