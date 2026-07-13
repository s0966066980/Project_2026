import { resolve } from 'node:path';

import { defineConfig } from 'vite';

export default defineConfig({
  publicDir: false,
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      input: {
        admin: resolve(__dirname, 'admin/admin.js'),
        kiosk: resolve(__dirname, 'kiosk/app.js'),
      },
      output: {
        entryFileNames: '[name]/app.js',
        chunkFileNames: 'shared/[name]-[hash].js',
      },
    },
  },
});
