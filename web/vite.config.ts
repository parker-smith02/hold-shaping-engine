/// <reference types="vitest" />
import { defineConfig } from "vite";

// The editor talks to the local FastAPI server (holdgen-server, default :8000).
export default defineConfig({
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.HOLDGEN_API ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { outDir: "dist", sourcemap: true, target: "es2022" },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
