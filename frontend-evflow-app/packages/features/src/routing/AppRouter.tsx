import { BrowserRouter } from 'react-router-dom';
import { AppRoutes } from './AppRoutes';

export function AppRouter() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
