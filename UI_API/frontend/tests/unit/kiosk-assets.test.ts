import { existsSync } from 'node:fs';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * A moved asset breaks nothing at build time: the URL is a string, so a stale
 * path ships and the customer sees a missing image. These references are
 * checked against the files that actually exist.
 */

const FRONTEND_ROOT = resolve(__dirname, '../..');
const STATIC_REFERENCE = /\/static\/([A-Za-z0-9._\-/]+\.(?:jpg|jpeg|png|svg|webp))/g;

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (['node_modules', 'dist', 'coverage', 'test-results', 'assets'].includes(entry)) continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) sourceFiles(path, found);
    else if (/\.(js|ts|css|html)$/.test(entry)) found.push(path);
  }
  return found;
}

describe('static asset references', () => {
  it('every referenced image exists on disk', () => {
    const missing: string[] = [];
    for (const file of sourceFiles(FRONTEND_ROOT)) {
      const source = readFileSync(file, 'utf8');
      for (const match of source.matchAll(STATIC_REFERENCE)) {
        const relative = match[1] ?? '';
        // Item images are served by the catalog API when uploaded; only the
        // bundled kiosk assets are files this repository has to contain.
        if (!relative.startsWith('kiosk/assets/')) continue;
        if (!existsSync(join(FRONTEND_ROOT, relative))) {
          missing.push(`${file.replace(FRONTEND_ROOT, '.')} -> /static/${relative}`);
        }
      }
    }
    expect(missing).toEqual([]);
  });

  it('kiosk assets are addressed under the kiosk product, not the frontend root', () => {
    const strays: string[] = [];
    for (const file of sourceFiles(FRONTEND_ROOT)) {
      const source = readFileSync(file, 'utf8');
      for (const match of source.matchAll(STATIC_REFERENCE)) {
        const relative = match[1] ?? '';
        if (/^(menu_images|mcd_categories)\//.test(relative) || relative === 'image2.png') {
          strays.push(`${file.replace(FRONTEND_ROOT, '.')} -> /static/${relative}`);
        }
      }
    }
    expect(strays).toEqual([]);
  });
});
