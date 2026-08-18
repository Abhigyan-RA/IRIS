import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Ripple } from '../../lib/api';
import { RippleChain, RippleLinks, chainLayers } from './RippleChain';

function ripple(overrides: Partial<Ripple> = {}): Ripple {
  return {
    commodity: 'Copper',
    depth: 2,
    nodes: [
      { name: 'Copper', kind: 'Commodity' },
      { name: 'Stator Coil', kind: 'Component' },
      { name: 'EV Battery Manufacturing', kind: 'Industry' },
    ],
    links: [
      { source: 'Copper', relationship: 'REFINED_INTO', target: 'Stator Coil', weight: null },
      {
        source: 'Stator Coil',
        relationship: 'REQUIRED_FOR',
        target: 'EV Battery Manufacturing',
        weight: 0.18,
      },
    ],
    affected_industries: ['EV Battery Manufacturing'],
    exposed_filers: [],
    explanation: null,
    ...overrides,
  };
}

describe('chainLayers', () => {
  it('groups the chain into components then industries', () => {
    expect(chainLayers(ripple())).toEqual([
      { kind: 'Component', members: ['Stator Coil'] },
      { kind: 'Industry', members: ['EV Battery Manufacturing'] },
    ]);
  });

  it('leaves out the commodity itself, which is shown separately', () => {
    const layers = chainLayers(ripple());

    expect(layers.flatMap((layer) => layer.members)).not.toContain('Copper');
  });

  it('lists each member once even when several paths reach it', () => {
    const layers = chainLayers(
      ripple({
        nodes: [
          { name: 'Copper', kind: 'Commodity' },
          { name: 'Construction', kind: 'Industry' },
          { name: 'Construction', kind: 'Industry' },
        ],
      }),
    );

    expect(layers[0]?.members).toEqual(['Construction']);
  });

  it('returns nothing when only the commodity is known', () => {
    expect(chainLayers(ripple({ nodes: [{ name: 'Copper', kind: 'Commodity' }] }))).toEqual([]);
  });
});

describe('RippleChain', () => {
  it('shows the commodity and everything downstream of it', () => {
    render(<RippleChain ripple={ripple()} />);

    expect(screen.getByText('Copper')).toBeInTheDocument();
    expect(screen.getByText('Stator Coil')).toBeInTheDocument();
    expect(screen.getByText('EV Battery Manufacturing')).toBeInTheDocument();
  });

  it('labels each layer so the order means something', () => {
    render(<RippleChain ripple={ripple()} />);

    expect(screen.getByText('Component')).toBeInTheDocument();
    expect(screen.getByText('Industry')).toBeInTheDocument();
  });

  it('says a gap in coverage is a gap, not an absence of effect', () => {
    render(<RippleChain ripple={ripple({ nodes: [{ name: 'Copper', kind: 'Commodity' }] })} />);

    expect(screen.getByText(/gap in coverage/)).toBeInTheDocument();
  });

  it('is a labelled region', () => {
    render(<RippleChain ripple={ripple()} />);

    expect(screen.getByRole('region', { name: /Propagation map/ })).toBeInTheDocument();
  });
});

describe('RippleLinks', () => {
  it('writes out each step in readable words', () => {
    render(<RippleLinks ripple={ripple()} />);

    expect(screen.getByText('refined into')).toBeInTheDocument();
    expect(screen.getByText('required for')).toBeInTheDocument();
  });

  it('reports the share of input cost where the graph records one', () => {
    render(<RippleLinks ripple={ripple()} />);

    expect(screen.getByText('18% of input cost')).toBeInTheDocument();
  });

  it('says nothing about cost share when none is recorded', () => {
    render(
      <RippleLinks
        ripple={ripple({
          links: [
            { source: 'Copper', relationship: 'REFINED_INTO', target: 'Stator Coil', weight: null },
          ],
        })}
      />,
    );

    expect(screen.queryByText(/of input cost/)).not.toBeInTheDocument();
  });

  it('renders nothing at all when there are no steps', () => {
    const { container } = render(<RippleLinks ripple={ripple({ links: [] })} />);

    expect(container).toBeEmptyDOMElement();
  });
});
