import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" makes built asset paths relative, so pywebview can load dist/index.html
// over file:// without a server.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
});
