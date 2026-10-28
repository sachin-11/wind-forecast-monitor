import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api is proxied to the FastAPI server so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: { output: { manualChunks: { charts: ["recharts"], react: ["react", "react-dom"] } } },
  },
  server: {
    port: 5173,
    proxy: { "/api": process.env.VITE_PROXY_TARGET ?? "http://localhost:8000" },
  },
});
