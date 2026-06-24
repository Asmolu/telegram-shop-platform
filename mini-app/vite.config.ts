import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const appVersion = process.env.VITE_APP_VERSION
  ?? `${process.env.npm_package_version ?? '0.1.0'}-${Date.now()}`;

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  plugins: [react()],
  build: {
    manifest: true,
  },
  server: {
    port: 5173,
  },
});
