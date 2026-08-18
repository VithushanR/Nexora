// Vite config: React plugin + dev server settings.
// TODO: add a /api proxy to the FastAPI backend if avoiding CORS is preferred over VITE_API_BASE_URL.

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
