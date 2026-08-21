import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AppShell } from './AppShell';

/**
 * The frame must produce exactly one scrollbar.
 *
 * A fixed-height frame with a scrolling panel inside it gives the reader two
 * scrollbars side by side: the page's and the panel's. Which one responds to the
 * wheel then depends on where the pointer happens to be, and on a short window both
 * appear at once. So the document is the only scroll container, and the rail and top
 * bar stay put by sticking rather than by being pinned inside a clipped box.
 */
describe('AppShell scrolling', () => {
  it('does not create a second scroll container around the screen', () => {
    render(
      <AppShell currentPath="/risk-map">
        <p>content</p>
      </AppShell>,
    );

    const main = screen.getByRole('main');
    expect(main.className).not.toMatch(/overflow-y-(auto|scroll)/);
    expect(main.className.split(' ')).not.toContain('h-screen');
  });

  it('lets the document grow with the screen rather than clipping it to the viewport', () => {
    const { container } = render(
      <AppShell currentPath="/risk-map">
        <p>content</p>
      </AppShell>,
    );

    const frame = container.firstElementChild;
    const tokens = String(frame?.className).split(' ');
    expect(tokens).toContain('min-h-screen');
    expect(tokens).not.toContain('h-screen');
  });

  it('keeps the top bar visible while the page scrolls', () => {
    render(
      <AppShell currentPath="/risk-map">
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByRole('banner').className).toMatch(/sticky/);
  });

  it('keeps the navigation rail visible while the page scrolls', () => {
    render(
      <AppShell currentPath="/risk-map">
        <p>content</p>
      </AppShell>,
    );

    expect(screen.getByRole('navigation').className).toMatch(/sticky/);
  });
});
