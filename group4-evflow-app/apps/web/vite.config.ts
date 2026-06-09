import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    extensions: ['.web.tsx', '.web.ts', '.web.jsx', '.web.js', '.mjs', '.js', '.mts', '.ts', '.jsx', '.tsx', '.json'],
    alias: {
      'react-native': 'react-native-web',
      '@evflow/shared': path.resolve(__dirname, '../../packages/shared/src'),
      '@evflow/ui': path.resolve(__dirname, '../../packages/ui/src'),
      '@evflow/maps': path.resolve(__dirname, '../../packages/maps/src'),
      '@evflow/features': path.resolve(__dirname, '../../packages/features/src')
    }
  }
});
