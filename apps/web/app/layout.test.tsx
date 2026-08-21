import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import RootLayout, { metadata } from './layout';

/**
 * The layout is asserted on its returned element tree rather than through
 * `render`, because mounting a full `html`/`body` document inside jsdom's
 * existing document produces invalid nesting.
 */
describe('RootLayout', () => {
  it('declares the document language for screen readers', () => {
    const element = RootLayout({ children: null }) as ReactElement<{ lang: string }>;

    expect(element.type).toBe('html');
    expect(element.props.lang).toBe('en');
  });

  it('tolerates attributes a browser extension adds to the root element', () => {
    const element = RootLayout({ children: null }) as ReactElement<{
      suppressHydrationWarning: boolean;
    }>;

    expect(element.props.suppressHydrationWarning).toBe(true);
  });

  it('renders its children inside the document body', () => {
    const child = <p>content</p>;

    const element = RootLayout({ children: child }) as ReactElement<{
      children: ReactElement<{ children: unknown }>[];
    }>;

    const body = element.props.children.find((node) => node.type === 'body');
    expect(body).toBeDefined();
    expect(body?.props.children).toBe(child);
  });

  it('applies a theme before the first paint, so no wrong-colour flash is shown', () => {
    const element = RootLayout({ children: null }) as ReactElement<{
      'data-theme': string;
      children: ReactElement<{ children: unknown }>[];
    }>;

    // A default on the element itself covers the case where the script cannot run.
    expect(element.props['data-theme']).toBe('dark');

    const head = element.props.children.find((node) => node.type === 'head');
    const script = (
      head as ReactElement<{
        children: ReactElement<{
          dangerouslySetInnerHTML: { __html: string };
        }>;
      }>
    ).props.children;
    expect(script.props.dangerouslySetInnerHTML.__html).toContain('shadow-cpi-theme');
    expect(script.props.dangerouslySetInnerHTML.__html).toContain('light');
  });

  it('exposes page metadata used for the browser title and description', () => {
    expect(metadata.title).toBe('Shadow CPI');
    expect(metadata.description).toContain('Alternative data intelligence');
  });
});
