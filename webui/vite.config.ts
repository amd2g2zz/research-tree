import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev proxy: REST → /api, WebSocket → /ws (server on 8787, see webui-server)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8787",
      "/ws": { target: "ws://127.0.0.1:8787", ws: true },
    },
  },
});
