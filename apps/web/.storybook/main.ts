import type { StorybookConfig } from '@storybook/react-vite';

/**
 * Storybook configuration.
 *
 * Storybook renders each component in isolation, which is how this project
 * documents and reviews UI states (default, loading, error, empty) without
 * needing a running backend.
 *
 * The React-Vite framework is used rather than the Next.js one because the
 * latter currently pulls in a dependency with an unpatched high-severity
 * advisory. Reusable components here are plain React and do not rely on
 * Next-specific runtime behaviour, so nothing is lost.
 */
const config: StorybookConfig = {
  stories: ['../components/**/*.stories.@(ts|tsx)', '../app/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-docs', '@storybook/addon-a11y', '@storybook/addon-vitest'],
  core: {
    // No usage data leaves the developer machine or CI.
    disableTelemetry: true,
  },
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  typescript: {
    // Type checking runs once in CI through `npm run typecheck`; repeating it
    // here would slow down every Storybook start for no extra safety.
    check: false,
    reactDocgen: 'react-docgen-typescript',
  },
};

export default config;
