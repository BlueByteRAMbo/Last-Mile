import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // keep the two heavy libraries out of the main bundle so the app shell loads and caches separately
        manualChunks: { mapbox: ['mapbox-gl'], charts: ['recharts'] },
      },
    },
    chunkSizeWarningLimit: 2000,  // mapbox-gl alone is ~1.9 MB minified; that chunk is expected to be large
  },
})
