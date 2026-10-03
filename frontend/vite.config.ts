import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@capture-guide": fileURLToPath(
        new URL("../capture.md", import.meta.url),
      ),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] },
    proxy: { "/api": process.env.API_TARGET || "http://127.0.0.1:8000" },
  },
});
