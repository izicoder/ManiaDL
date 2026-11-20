import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Assets are served by the WinForms host from a virtual origin
// (https://maniadl.app/), so root-absolute asset paths are fine.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "chrome110",
  },
  server: {
    port: 5173,
  },
});
