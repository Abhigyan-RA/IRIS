import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Ripple, Trend } from '../../lib/api';
import { PropagationReport, SelectedNode } from './SelectedNode';

function trend(overrides: Partial<Trend> = {}): Trend {
  return {
    entity_name: 'Copper',
    sector: 'metals',
    currency: 'USD',
    unit: 'lb',
    days: 30,
    points: [
      { recorded_at: '2026-07-16T12:00:00Z', price: '4.10' },
      { recorded_at: '2026-08-15T12:00:00Z', price: '4.52' },
    ],
    change_pct_over_window: '10.2',
    latest_price: '4.52',
    source_name: 'investing.com',
    source_url: 'https://www.investing.com/commodities/copper',
    ...overrides,
  };
}

function ripple(overrides: Partial<Ripple> = {}): Ripple {
  return {
    commodity: 'Copper',
    depth: 2,
    nodes: [],
    links: [
      {
        source: 'Copper',
        relationship: 'IMPACTS_COST_OF',
        target: 'EV Battery Manufacturing',
        weight: 0.18,
      },
    ],
    affected_industries: ['EV Battery Manufacturing'],
    exposed_filers: [],
    explanation: 'Copper feeds electric vehicle manufacturing, so a rise raises battery costs.',
    ...overrides,
  };
}

describe('SelectedNode', () => {
  it('names the entity as the page heading', () => {
    render(<SelectedNode trend={trend()} commodity="Copper" />);

    expect(screen.getByRole('heading', { level: 1, name: 'Copper' })).toBeInTheDocument();
  });

  it('shows the latest price with its currency and unit', () => {
    render(<SelectedNode trend={trend()} commodity="Copper" />);

    expect(screen.getByText(/4.52 USD/)).toBeInTheDocument();
    expect(screen.getByText('/ lb')).toBeInTheDocument();
  });

  it('shows the change across the window with the window length', () => {
    render(<SelectedNode trend={trend()} commodity="Copper" />);

    expect(screen.getByText('+10.2%')).toBeInTheDocument();
    expect(screen.getByText('30d')).toBeInTheDocument();
  });

  it('draws the trend and describes its direction', () => {
    render(<SelectedNode trend={trend()} commodity="Copper" />);

    expect(screen.getByRole('img', { name: 'Copper, 30 day trend, rising' })).toBeInTheDocument();
  });

  it('describes a falling trend as falling', () => {
    render(
      <SelectedNode
        commodity="Brent"
        trend={trend({
          entity_name: 'Brent',
          points: [
            { recorded_at: '2026-07-16T12:00:00Z', price: '86.00' },
            { recorded_at: '2026-08-15T12:00:00Z', price: '82.40' },
          ],
        })}
      />,
    );

    expect(screen.getByRole('img', { name: /falling/ })).toBeInTheDocument();
  });

  it('links to the source so a figure can be checked', () => {
    render(<SelectedNode trend={trend()} commodity="Copper" />);

    expect(screen.getByRole('link', { name: 'investing.com' })).toHaveAttribute(
      'href',
      'https://www.investing.com/commodities/copper',
    );
  });

  it('still names the entity when no price has been recorded', () => {
    render(<SelectedNode trend={null} commodity="Unobtainium" />);

    expect(screen.getByRole('heading', { level: 1, name: 'Unobtainium' })).toBeInTheDocument();
    expect(screen.getByText(/No price has been recorded/)).toBeInTheDocument();
  });
});

describe('PropagationReport', () => {
  it('shows the explanation', () => {
    render(<PropagationReport ripple={ripple()} />);

    expect(screen.getByText(/feeds electric vehicle manufacturing/)).toBeInTheDocument();
  });

  it('says what the explanation was grounded in', () => {
    render(<PropagationReport ripple={ripple()} />);

    expect(screen.getByText(/1 recorded relationship reaching 1 industry/)).toBeInTheDocument();
  });

  it('renders nothing when no explanation was produced', () => {
    const { container } = render(<PropagationReport ripple={ripple({ explanation: null })} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for a blank explanation rather than an empty box', () => {
    const { container } = render(<PropagationReport ripple={ripple({ explanation: '   ' })} />);

    expect(container).toBeEmptyDOMElement();
  });
});
