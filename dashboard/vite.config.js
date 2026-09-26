import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard talks to the BATMAN gateway. In dev, proxy /v1 to the API so
// there are no CORS surprises and the frontend can use relative URLs.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
