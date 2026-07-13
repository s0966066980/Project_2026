import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts'],
    coverage: {
      include: ['shared/api/**/*.ts'],
      reporter: ['text', 'json-summary'],
      thresholds: { branches: 80, functions: 80, lines: 80, statements: 80 },
    },
  },
});
