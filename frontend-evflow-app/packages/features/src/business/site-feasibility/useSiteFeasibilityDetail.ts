import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deletePlannerSavedSite,
  fetchPlannerSavedSiteStatus,
  PlannerApiError,
  savePlannerSite
} from '@evflow/shared';
import { getSiteFeasibility } from './siteFeasibilityData';
import {
  getSiteFinancialProjection,
  isMockOptimalSiteId
} from './siteFeasibilityFinancial';
import { getMockSiteFeasibility } from './siteFeasibilityMockData';
import type { FinancialProjection, SiteFeasibilityData, SiteFeasibilityTab } from './siteFeasibilityTypes';

type DetailOptions = {
  onMessage?: (message: string) => void;
  onSavedChange?: (saved: boolean) => void;
};

export function useSiteFeasibilityDetail(siteId: string | null, options: DetailOptions = {}) {
  const callbacks = useRef(options);
  callbacks.current = options;
  const isMock = siteId ? isMockOptimalSiteId(siteId) : false;
  const [data, setData] = useState<SiteFeasibilityData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [financial, setFinancial] = useState<FinancialProjection | null>(null);
  const [financialError, setFinancialError] = useState<string | null>(null);
  const [financialLoading, setFinancialLoading] = useState(false);
  const [financialRetry, setFinancialRetry] = useState(0);
  const [activeTab, setActiveTab] = useState<SiteFeasibilityTab>('feasibility');
  const [isSaved, setIsSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setActiveTab('feasibility');
    setRetry(0);
    setFinancialRetry(0);
  }, [siteId]);

  useEffect(() => {
    if (!siteId || isMock) {
      setIsSaved(false);
      setIsSaving(false);
      return;
    }
    let active = true;
    setIsSaving(true);
    void fetchPlannerSavedSiteStatus(siteId)
      .then((result) => { if (active) setIsSaved(result.saved); })
      .catch((requestError: unknown) => {
        if (active) callbacks.current.onMessage?.(`Saved Sites: ${plannerErrorCopy(requestError)}`);
      })
      .finally(() => { if (active) setIsSaving(false); });
    return () => { active = false; };
  }, [isMock, siteId]);

  useEffect(() => {
    if (!siteId) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    void getSiteFeasibility(siteId)
      .then((result) => { if (active) setData(result); })
      .catch((requestError: unknown) => { if (active) setError(plannerErrorCopy(requestError)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [retry, siteId]);

  useEffect(() => {
    if (!siteId) {
      setFinancial(null);
      setFinancialError(null);
      setFinancialLoading(false);
      return;
    }
    if (isMock) {
      setFinancial(getMockSiteFeasibility(siteId).financial);
      setFinancialError(null);
      setFinancialLoading(false);
      return;
    }
    let active = true;
    setFinancial(null);
    setFinancialLoading(true);
    setFinancialError(null);
    void getSiteFinancialProjection(siteId)
      .then((result) => { if (active) setFinancial(result); })
      .catch((requestError: unknown) => { if (active) setFinancialError(plannerRoiErrorCopy(requestError)); })
      .finally(() => { if (active) setFinancialLoading(false); });
    return () => { active = false; };
  }, [financialRetry, isMock, siteId]);

  const toggleSaved = useCallback(() => {
    if (!siteId || isMock || isSaving) return;
    const previous = isSaved;
    const next = !previous;
    setIsSaved(next);
    setIsSaving(true);
    callbacks.current.onSavedChange?.(next);
    const request = next ? savePlannerSite(siteId) : deletePlannerSavedSite(siteId);
    void request.catch((requestError: unknown) => {
      setIsSaved(previous);
      callbacks.current.onSavedChange?.(previous);
      callbacks.current.onMessage?.(`Saved Sites: ${plannerErrorCopy(requestError)}`);
    }).finally(() => setIsSaving(false));
  }, [isMock, isSaved, isSaving, siteId]);

  return {
    activeTab,
    data,
    error,
    financial,
    financialError,
    financialLoading,
    isMock,
    isSaved,
    isSaving,
    loading,
    retry: () => setRetry((value) => value + 1),
    retryFinancial: () => setFinancialRetry((value) => value + 1),
    setActiveTab,
    toggleSaved
  };
}

export function plannerErrorCopy(error: unknown) {
  if (error instanceof PlannerApiError) return error.message;
  if (error instanceof TypeError) return 'Unable to reach the backend.';
  return 'Planning data could not be loaded.';
}

function plannerRoiErrorCopy(error: unknown) {
  if (error instanceof PlannerApiError) {
    if (error.status === 401) return 'Session expired. Sign in again.';
    if (error.status === 403) return 'Business Planner access is required.';
    if (error.status === 404) return 'This planning cell is no longer available.';
    return error.message;
  }
  if (error instanceof TypeError) return 'Unable to reach the backend.';
  return 'Financial projection could not be calculated.';
}
