import { defineConfig } from 'vite';

// base './' 讓打包後的 dist 能被 axum 以任意路徑服務。
// dev 時把 /ws 代理到後端 axum（127.0.0.1:3000）。
export default defineConfig({
  base: './',
  server: {
    proxy: {
      '/ws': {
        target: 'ws://127.0.0.1:3000',
        ws: true,
      },
    },
  },
});
