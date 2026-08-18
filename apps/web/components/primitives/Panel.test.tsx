import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Panel, SectionLabel } from './Panel';

describe('Panel', () => {
  it('renders its content', () => {
    render(
      <Panel>
        <p>Freight rates</p>
      </Panel>,
    );

    expect(screen.getByText('Freight rates')).toBeInTheDocument();
  });

  it('carries the shared border and surface so panels never drift apart', () => {
    render(<Panel>content</Panel>);

    const panel = screen.getByText('content');
    expect(panel).toHaveClass('border-hairline');
    expect(panel).toHaveClass('bg-panel');
  });

  it('accepts layout classes from the screen using it', () => {
    render(<Panel className="col-span-2">content</Panel>);

    expect(screen.getByText('content')).toHaveClass('col-span-2');
  });
});

describe('SectionLabel', () => {
  it('renders as a heading so the page has a real outline', () => {
    render(<SectionLabel>Top movers</SectionLabel>);

    expect(screen.getByRole('heading', { name: 'Top movers' })).toBeInTheDocument();
  });

  it('uses muted grey for a supporting group', () => {
    render(<SectionLabel>Top movers</SectionLabel>);

    expect(screen.getByRole('heading')).toHaveClass('text-ink-muted');
  });

  it('uses the accent colour for the panel a screen is built around', () => {
    render(<SectionLabel tone="primary">Shadow CPI index</SectionLabel>);

    expect(screen.getByRole('heading')).toHaveClass('text-accent');
  });

  it('leaves the text as written and upper-cases it in style only', () => {
    render(<SectionLabel>Top movers</SectionLabel>);

    const heading = screen.getByRole('heading');
    expect(heading).toHaveTextContent('Top movers');
    expect(heading).toHaveClass('uppercase');
  });
});
