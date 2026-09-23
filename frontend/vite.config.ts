import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// En desarrollo, /api se redirige al backend FastAPI: el navegador ve un solo
// origen, así que no hace falta CORS ni exponer la API directamente.
const API_TARGET = process.env.FACETRACK_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: API_TARGET, changeOrigin: true } },
  },
  preview: {
    port: 4173,
    proxy: { "/api": { target: API_TARGET, changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    css: { modules: { classNameStrategy: "non-scoped" } },
  },
});
