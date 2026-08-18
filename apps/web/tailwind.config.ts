import type { Config } from 'tailwindcss';

/**
 * Tailwind configuration and the single home for design tokens.
 *
 * Every value here was read from the design references in `designs/`. Because
 * those references are screenshots rather than a design file, colours are sampled
 * from pixels and spacing is measured, so treat them as faithful to within a step
 * of the scale rather than exact. Anything genuinely ambiguous is called out in a
 * comment.
 *
 * The rule for components is simple: if a value comes from the design, it is named
 * here and referenced by name. A hardcoded colour in a component cannot be
 * restyled consistently and will drift.
 */
const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
    './.storybook/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Surfaces, darkest to lightest. The interface is near-black with panels
        // lifted a few percent, which is what keeps the coloured data readable.
        canvas: '#08090b',
        rail: '#0b0c0e',
        panel: '#111214',
        'panel-raised': '#16181c',
        'panel-inset': '#1a1d21',
        hairline: '#1f2226',
        'hairline-strong': '#2a2e34',

        // Text, in descending prominence.
        ink: '#e8eaed',
        'ink-muted': '#9ba1a8',
        'ink-faint': '#6b7280',

        // The one accent colour: panel titles, active navigation, tickers, links,
        // and the primary chart series.
        accent: {
          DEFAULT: '#22d3ee',
          soft: '#0e7490',
          wash: 'rgba(34, 211, 238, 0.08)',
        },

        // Data colours. In this product a rising cost is bad news, so "up" is red
        // and "down" is green. That is the opposite of a stock chart and is
        // deliberate: the reader cares about cost, not price direction.
        rise: '#f43f5e',
        fall: '#22c55e',
        warn: '#f59e0b',
        neutral: '#9ba1a8',
      },
      fontFamily: {
        // Numbers, timestamps, tickers, and log lines are monospaced throughout the
        // design, so figures line up column to column and a changing digit does not
        // shift the ones beside it.
        sans: [
          'ui-sans-serif',
          'Inter',
          'system-ui',
          'Segoe UI',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'JetBrains Mono',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'monospace',
        ],
      },
      fontSize: {
        // Section labels: small, upper case, widely spaced.
        label: ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.08em' }],
        // The headline figure on the risk map and the health screen.
        headline: ['3.25rem', { lineHeight: '1.05', letterSpacing: '-0.02em' }],
        // A selected entity's name.
        title: ['1.75rem', { lineHeight: '1.2', letterSpacing: '-0.01em' }],
      },
      borderRadius: {
        card: '0.75rem',
        pill: '9999px',
      },
      spacing: {
        // Width of the fixed icon rail.
        rail: '5rem',
        // Width of the right-hand context panel.
        aside: '21rem',
        // Height of the top bar.
        topbar: '4rem',
      },
      boxShadow: {
        // Markers on the map glow in their status colour. The colour itself is set
        // per marker, so only the shape is defined here.
        marker: '0 0 24px 0 rgb(0 0 0 / 0.6)',
      },
    },
  },
  plugins: [],
};

export default config;
