import js from '@eslint/js';
import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';
import prettier from 'eslint-config-prettier';
import storybook from 'eslint-plugin-storybook';
import tseslint from 'typescript-eslint';

/**
 * ESLint configuration for the dashboard.
 *
 * A few things worth knowing if you are editing this file:
 *
 * - `next/core-web-vitals` already includes the accessibility (jsx-a11y) and
 *   React Hooks rule sets, so those plugins are not listed separately.
 * - Type-aware rules are limited to TypeScript sources. Config files such as
 *   `postcss.config.mjs` are not part of the TypeScript program, and type-aware
 *   rules cannot run against them.
 * - `prettier` comes last so formatting is owned by Prettier alone and never
 *   argued about in review.
 */
export default tseslint.config(
  {
    ignores: [
      '.next/**',
      'storybook-static/**',
      'coverage/**',
      'next-env.d.ts',
      '*.config.mjs',
      'postcss.config.mjs',
    ],
  },
  js.configs.recommended,
  ...nextCoreWebVitals,
  ...storybook.configs['flat/recommended'],
  {
    files: ['**/*.{ts,tsx,mts}'],
    extends: [tseslint.configs.strictTypeChecked, tseslint.configs.stylisticTypeChecked],
    settings: {
      // Pinned explicitly: the React plugin cannot auto-detect the version when
      // packages are hoisted to the workspace root.
      react: { version: '19.2' },
    },
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Exported functions and components must declare their types, so callers
      // can rely on the signature rather than reading the implementation.
      '@typescript-eslint/explicit-module-boundary-types': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
      // Styling goes through Tailwind classes. Inline styles bypass the design
      // tokens and are only acceptable for a value Tailwind cannot express,
      // which requires removing this rule locally with an explanation.
      'react/forbid-dom-props': ['error', { forbid: ['style'] }],
      eqeqeq: ['error', 'always'],
      // Use the shared logger rather than console output.
      'no-console': 'error',
    },
  },
  {
    files: ['**/*.test.ts', '**/*.test.tsx', '**/*.stories.tsx', 'vitest.setup.ts'],
    rules: {
      // Tests knowingly assert on values the type system cannot narrow.
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },
  prettier,
);
