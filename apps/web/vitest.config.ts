import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

/**
 * Vitest configuration for unit and React component tests.
 *
 * Tests run in a simulated browser environment (jsdom) so components can be
 * rendered and queried the way a user would perceive them. Browser-driven
 * end-to-end specs live in `e2e/` and are run by Playwright instead, so they are
 * excluded here.
 *
 * The coverage thresholds fail the run rather than print a warning: a threshold
 * nobody enforces is a threshold that quietly slides.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['**/*.test.{ts,tsx}'],
    exclude: ['node_modules/**', '.next/**', 'e2e/**'],
    // Rendering a component and driving it through user events is slower than a plain
    // function call, and slower still on a machine that is busy or short of memory. The
    // default five seconds fails there for no reason worth acting on, which trains people
    // to rerun a red suite instead of reading it.
    testTimeout: 20000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['app/**/*.{ts,tsx}', 'components/**/*.{ts,tsx}', 'lib/**/*.{ts,tsx}'],
      // Stories, tests, and barrel files contain no logic worth measuring.
      exclude: ['**/*.stories.tsx', '**/*.test.{ts,tsx}', '**/index.ts'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 80,
        statements: 80,
      },
    },
  },
});
