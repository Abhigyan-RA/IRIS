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
      children: ReactElement<{ children: unknown }>;
    }>;

    expect(element.props.children.type).toBe('body');
    expect(element.props.children.props.children).toBe(child);
  });

  it('exposes page metadata used for the browser title and description', () => {
    expect(metadata.title).toBe('Shadow CPI');
    expect(metadata.description).toContain('Alternative data intelligence');
  });
});
