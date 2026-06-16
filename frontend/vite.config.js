import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

/**
 * Build the Vite configuration for the admin frontend.
 *
 * Returns:
 *   Vite configuration object with the API proxy for local development.
 */
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
});

