import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// The designer ships as one HTML file inside the Python wheel: no server, no
// asset requests. viteSingleFile inlines the JS and CSS for us.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: { target: "es2022", assetsInlineLimit: 100_000_000, cssCodeSplit: false },
});
