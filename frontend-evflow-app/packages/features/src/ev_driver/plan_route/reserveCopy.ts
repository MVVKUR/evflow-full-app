/**
 * The one line under a mid-navigation warning that talks about the reserve.
 *
 * It used to be hardcoded and rendered for every warning code except
 * no_suitable_station, so a tight-but-safe projection showed the server saying
 * "23%, just above your 20% reserve" directly above the app saying "Projected
 * arrival is below your 20% reserve". Contradicting ourselves about the number
 * a driver uses to decide whether to stop is worse than saying nothing.
 */

/** Points above the reserve that still count as tight. Mirrors the server's ROUTE_TIGHT_MARGIN_SOC_PCT. */
export const TIGHT_MARGIN_SOC_PCT = 5;

export function getReserveCopy(
  projectedSocPct: number | null | undefined,
  reservePct: number
): string | null {
  // No projection means no claim: silence beats inventing a verdict.
  if (typeof projectedSocPct !== 'number' || Number.isNaN(projectedSocPct)) return null;

  const margin = projectedSocPct - reservePct;
  if (margin < 0) return `Projected arrival is below your ${reservePct}% reserve.`;
  if (margin <= TIGHT_MARGIN_SOC_PCT) {
    return `Projected arrival clears your ${reservePct}% reserve by only ${Math.round(margin)}%.`;
  }
  // Comfortably above: the warning is about something else, so this line adds nothing.
  return null;
}
