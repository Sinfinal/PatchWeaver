import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/console/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 15173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:18080",
        changeOrigin: true,
      },
      "/healthz": {
        target: "http://127.0.0.1:18080",
        changeOrigin: true,
      },
    },
  },
});
