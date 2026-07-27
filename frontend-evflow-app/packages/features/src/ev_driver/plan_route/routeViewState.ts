import type { RouteViewMode } from './planRouteTypes';

export type RouteViewAction =
  | 'simulate'
  | 'start_navigation'
  | 'overview'
  | 'end_navigation'
  | 'complete'
  | 'cancel';

export function transitionRouteView(current: RouteViewMode, action: RouteViewAction): RouteViewMode {
  switch (action) {
    case 'simulate': return 'simulation';
    case 'start_navigation': return current === 'simulation' ? 'active_navigation' : current;
    case 'overview': return current === 'active_navigation' ? 'simulation' : current;
    case 'complete': return current === 'active_navigation' ? 'completed' : current;
    case 'end_navigation':
    case 'cancel': return 'input';
  }
}

export function isImmersiveRouteView(mode: RouteViewMode): boolean {
  return mode === 'active_navigation';
}

export function showDesktopNavigation(desktop: boolean, immersive: boolean): boolean {
  return desktop && !immersive;
}

export function showMobileNavigation(desktop: boolean, immersive: boolean, walletSuccess: boolean): boolean {
  return !desktop && !immersive && !walletSuccess;
}
