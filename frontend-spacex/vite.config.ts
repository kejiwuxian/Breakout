import { defineConfig } from "vite";

/** SpaceX-track UI — production base path `/spacex/` (served by FastAPI). */
export default defineConfig({
  base: "/spacex/",
  server: {
    port: 5175,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/scenario": "http://127.0.0.1:8000",
      "/api": "http://127.0.0.1:8000",
      "/alerts": "http://127.0.0.1:8000",
      "/subscribe": "http://127.0.0.1:8000",
      "/voice": "http://127.0.0.1:8000",
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
});
