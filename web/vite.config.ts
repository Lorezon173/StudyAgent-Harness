import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// proxy target defaults to 8000, can be overridden via VITE_API_TARGET (e.g., 8001 when 8000 is occupied)
const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/health": { target: apiTarget, changeOrigin: true },
    },
  },
  build: { outDir: "dist" },
  test: { environment: "node" },
});
