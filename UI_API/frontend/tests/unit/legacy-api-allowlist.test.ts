import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../..');

describe('legacy API allowlist freeze', () => {
  it('lists every direct fetch("/api/") usage and does not grow beyond known entries', () => {
    const allowlist = JSON.parse(
      readFileSync(resolve(root, 'legacy-api-allowlist.json'), 'utf8'),
    ) as {
      entries: Array<{ file: string; pattern: string }>;
    };
    const sources = [
      { file: 'frontend/admin/admin.js', text: readFileSync(resolve(root, 'admin/admin.js'), 'utf8') },
      { file: 'frontend/kiosk/app.js', text: readFileSync(resolve(root, 'kiosk/app.js'), 'utf8') },
    ];
    const found: Array<{ file: string; path: string }> = [];
    const re = /fetch\(\s*[`'"](\/api\/[^`'"]+)/g;
    for (const source of sources) {
      let match: RegExpExecArray | null;
      while ((match = re.exec(source.text)) !== null) {
        const path = match[1] ?? '';
        if (path) found.push({ file: source.file, path });
      }
    }
    for (const hit of found) {
      const ok = allowlist.entries.some((entry) => {
        if (entry.file !== hit.file) return false;
        // pattern stores fetch('...') prefix; match against reconstructed call start
        const prefix = entry.pattern.replace(/^fetch\(['"]/, '').replace(/['"]$/, '');
        return hit.path.startsWith(prefix) || `fetch('${hit.path}'`.startsWith(entry.pattern);
      });
      expect(ok, `unexpected legacy fetch not on allowlist: ${JSON.stringify(hit)}`).toBe(true);
    }
    // Freeze: allowlist must not silently expand without review.
    expect(allowlist.entries.length).toBeLessThanOrEqual(2);
    expect(found.length).toBeGreaterThan(0);
  });
});
