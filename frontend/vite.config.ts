import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
    proxy: {
      "/health": process.env.VITE_API_PROXY ?? "http://localhost:8000",
      "/queue": process.env.VITE_API_PROXY ?? "http://localhost:8000",
      "/transactions": process.env.VITE_API_PROXY ?? "http://localhost:8000",
      "/process": process.env.VITE_API_PROXY ?? "http://localhost:8000",
      "/statements": process.env.VITE_API_PROXY ?? "http://localhost:8000",
    },
  },
});
