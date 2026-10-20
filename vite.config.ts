import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': { target: loadEnv(mode, '.', 'API_').API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: false } } },
  build: { outDir: 'dist' },
}));
