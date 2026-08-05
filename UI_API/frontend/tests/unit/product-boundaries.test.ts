import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(import.meta.dirname, '../..');
const productRoots = {
  admin: resolve(frontendRoot, 'admin'),
  kiosk: resolve(frontendRoot, 'kiosk'),
};
const sharedRoot = resolve(frontendRoot, 'shared');
const importPattern = /\b(?:from\s+|import\s*\()\s*['"]([^'"]+)['"]/g;

function sourceFiles(root: string): string[] {
  return readdirSync(root).flatMap((name) => {
    const path = resolve(root, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(?:js|ts)$/.test(name) ? [path] : [];
  });
}

function importedPaths(path: string): string[] {
  const source = readFileSync(path, 'utf8');
  return Array.from(source.matchAll(importPattern), (match) => match[1])
    .filter((specifier): specifier is string => typeof specifier === 'string')
    .filter((specifier) => specifier.startsWith('.'))
    .map((specifier) => resolve(dirname(path), specifier));
}

function isWithin(path: string, root: string): boolean {
  const pathFromRoot = relative(root, path);
  return pathFromRoot === '' || (!pathFromRoot.startsWith(`..${sep}`) && pathFromRoot !== '..');
}

describe('independent product frontend boundaries', () => {
  it.each([
    ['admin', 'kiosk'],
    ['kiosk', 'admin'],
  ] as const)('%s does not import the %s product', (sourceProduct, targetProduct) => {
    const violations = sourceFiles(productRoots[sourceProduct]).flatMap((path) =>
      importedPaths(path)
        .filter((imported) => isWithin(imported, productRoots[targetProduct]))
        .map((imported) => `${relative(frontendRoot, path)} -> ${relative(frontendRoot, imported)}`),
    );
    expect(violations).toEqual([]);
  });

  it('shared foundation does not import either product', () => {
    const violations = sourceFiles(sharedRoot).flatMap((path) =>
      importedPaths(path)
        .filter((imported) => Object.values(productRoots).some((root) => isWithin(imported, root)))
        .map((imported) => `${relative(frontendRoot, path)} -> ${relative(frontendRoot, imported)}`),
    );
    expect(violations).toEqual([]);
  });
});
