import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    // Railway atribui um domínio público dinâmico; aceitamos qualquer host
    // já que a autorização real fica no CORS do backend.
    allowedHosts: true,
  },
});
