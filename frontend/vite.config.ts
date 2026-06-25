import { defineConfig } from "vite";

const backendTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": backendTarget,
      "/assets": backendTarget,
      "/health": backendTarget,
      "/favicon.ico": backendTarget
    }
  },
  preview: {
    host: "127.0.0.1",
    port: 4173
  }
});
