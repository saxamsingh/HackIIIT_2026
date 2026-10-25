/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev every backend path is proxied, so the app needs no VITE_API_BASE and no CORS.
const API = process.env.KHETKAAJ_API ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  test: { environment: "node", include: ["src/**/*.test.ts"] },
  server: {
    proxy: Object.fromEntries(["/health", "/api", "/files", "/demo", "/webhooks", "/whatsapp"].map((p) => [p, API])),
  },
});
