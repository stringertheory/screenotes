import { createReadStream, existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import app from './app.json';

const server = `http://127.0.0.1:${app.port}`;
const FONTS = fileURLToPath(new URL('./node_modules/@excalidraw/excalidraw/dist/prod/fonts', import.meta.url));
// Excalidraw's Chinese, Japanese and Korean font is 12 MB. Text in those scripts falls back to a system font.
const SKIPPED_FONTS = new Set(['Xiaolai']);

/** The drawing editor's fonts, at /excalidraw/fonts/, where Annotate.tsx tells Excalidraw to look, so drawing needs
 *  no network. Copied into the build, and served from node_modules while developing. */
function excalidrawFonts(): Plugin {
  return {
    name: 'excalidraw-fonts',
    configureServer: dev => void dev.middlewares.use('/excalidraw/fonts', (request, response, next) => {
      const file = join(FONTS, decodeURIComponent((request.url ?? '').split('?')[0]));
      if (!file.startsWith(FONTS + sep) || !existsSync(file) || !statSync(file).isFile()) return next();
      response.setHeader('Content-Type', 'font/woff2');
      createReadStream(file).pipe(response);
    }),
    generateBundle() {
      for (const family of readdirSync(FONTS)) {
        if (SKIPPED_FONTS.has(family)) continue;
        for (const name of readdirSync(join(FONTS, family))) {
          this.emitFile({ type: 'asset', fileName: `excalidraw/fonts/${family}/${name}`, source: readFileSync(join(FONTS, family, name)) });
        }
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), excalidrawFonts(), { name: 'app-name', transformIndexHtml: html => html.replace('%APP_NAME%', app.name) }],
  server: {
    port: app.devPort,
    strictPort: true,
    proxy: {
      '/api': {
        target: server,
        changeOrigin: true,
        // The server accepts only its own page, so requests from this one are passed on as its own.
        configure: proxy => proxy.on('proxyReq', (request, incoming) => {
          if (incoming.headers.origin === `http://${incoming.headers.host}`) request.setHeader('Origin', server);
        }),
      },
    },
  },
});
