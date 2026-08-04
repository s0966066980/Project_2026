import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const frontendRoot = resolve(import.meta.dirname, '../..');
const allowExact = new Set([
  'shared/api/v1Client.ts',
]);

function walk(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === 'dist' || name === 'coverage') continue;
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, acc);
    else if (/\.(js|ts|tsx|mjs|cjs)$/.test(name)) acc.push(full);
  }
  return acc;
}

describe('frontend API boundary', () => {
  it('forbids direct fetch("/api/...") outside v1Client', () => {
    const files = walk(frontendRoot);
    const re = /fetch\s*\(\s*[`'"]\/api\//g;
    const offenders: string[] = [];
    for (const file of files) {
      const rel = relative(frontendRoot, file).replace(/\\/g, '/');
      if (allowExact.has(rel)) continue;
      if (rel.includes('legacy-api-allowlist')) continue;
      const text = readFileSync(file, 'utf8');
      if (re.test(text)) offenders.push(rel);
      re.lastIndex = 0;
    }
    // During cutover, admin.js may still hold legacy members fetch — track count.
    // Fail if new files appear beyond known debt.
    const allowedDebt = new Set(['admin/admin.js']);
    const unexpected = offenders.filter((o) => !allowedDebt.has(o));
    expect(unexpected, `unexpected direct API fetch: ${unexpected.join(', ')}`).toEqual([]);
  });
});
