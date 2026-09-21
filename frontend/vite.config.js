import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The API is served at the root (/search, /records/..., /gaps/...), not under
// an /api prefix, so every backend route family must be proxied by name.
// Keep this list in step with the routes in backend/app/main.py.
const API_ROUTES = ['/health', '/search', '/records', '/dashboard', '/heatmap', '/orgs', '/gaps', '/alerts'];
const target = process.env.VITE_API_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(API_ROUTES.map((r) => [r, { target, changeOrigin: true }])),
  },
});
