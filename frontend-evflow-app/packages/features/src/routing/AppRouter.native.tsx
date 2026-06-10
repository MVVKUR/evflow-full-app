import { NativeRouter } from 'react-router-native';
import { AppRoutes } from './AppRoutes';
import { ReceiptPdfViewer } from '../shared/ReceiptPdfViewer';

export function AppRouter() {
  return (
    <NativeRouter>
      <AppRoutes />
      <ReceiptPdfViewer />
    </NativeRouter>
  );
}
