import type { Preview } from '@storybook/react-vite';
import '../app/globals.css';

/**
 * Settings applied to every story.
 *
 * Accessibility violations are treated as errors rather than notices, because a
 * dashboard that a keyboard or screen-reader user cannot operate is not finished.
 */
const preview: Preview = {
  parameters: {
    controls: { expanded: true },
    a11y: { test: 'error' },
  },
};

export default preview;
