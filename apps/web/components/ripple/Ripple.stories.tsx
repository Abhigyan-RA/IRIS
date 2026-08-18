import type { Meta, StoryObj } from '@storybook/react-vite';
import type { Ripple, Trend } from '../../lib/api';
import { RippleChain, RippleLinks } from './RippleChain';
import { PropagationReport, SelectedNode } from './SelectedNode';

const RIPPLE: Ripple = {
  commodity: 'Copper',
  depth: 2,
  nodes: [
    { name: 'Copper', kind: 'Commodity' },
    { name: 'Stator Coil', kind: 'Component' },
    { name: 'EV Battery Manufacturing', kind: 'Industry' },
    { name: 'Consumer Electronics', kind: 'Industry' },
  ],
  links: [
    { source: 'Copper', relationship: 'REFINED_INTO', target: 'Stator Coil', weight: null },
    {
      source: 'Stator Coil',
      relationship: 'REQUIRED_FOR',
      target: 'EV Battery Manufacturing',
      weight: null,
    },
    {
      source: 'Copper',
      relationship: 'IMPACTS_COST_OF',
      target: 'Consumer Electronics',
      weight: 0.09,
    },
  ],
  affected_industries: ['Consumer Electronics', 'EV Battery Manufacturing'],
  exposed_filers: [],
  explanation:
    'Copper is refined into stator coils, which electric vehicle manufacturing depends on, so a sustained rise raises battery pack costs within a quarter.',
};

const TREND: Trend = {
  entity_name: 'Copper',
  sector: 'metals',
  currency: 'USD',
  unit: 'lb',
  days: 30,
  points: [
    { recorded_at: '2026-07-16T12:00:00Z', price: '4.10' },
    { recorded_at: '2026-07-26T12:00:00Z', price: '4.22' },
    { recorded_at: '2026-08-05T12:00:00Z', price: '4.38' },
    { recorded_at: '2026-08-15T12:00:00Z', price: '4.52' },
  ],
  change_pct_over_window: '10.2',
  latest_price: '4.52',
  source_name: 'investing.com',
  source_url: 'https://www.investing.com/commodities/copper',
};

const meta = {
  title: 'Screens/Ripple',
  component: RippleChain,
} satisfies Meta<typeof RippleChain>;

export default meta;

type Story = StoryObj<typeof meta>;

/** The chain from a commodity through components to industries. */
export const Chain: Story = {
  args: { ripple: RIPPLE },
};

/** A commodity whose downstream links have not been mapped yet. */
export const ChainUnmapped: Story = {
  args: {
    ripple: {
      ...RIPPLE,
      nodes: [{ name: 'Unobtainium', kind: 'Commodity' }],
      links: [],
      explanation: null,
    },
  },
};

/** Each relationship written out, with cost share where recorded. */
export const Relationships: Story = {
  args: { ripple: RIPPLE },
  render: () => <RippleLinks ripple={RIPPLE} />,
};

/** The selected entity with its price and trend. */
export const Selected: Story = {
  args: { ripple: RIPPLE },
  render: () => (
    <div className="w-80">
      <SelectedNode trend={TREND} commodity="Copper" />
    </div>
  ),
};

/** The selected entity before any price has been recorded for it. */
export const SelectedWithoutPrice: Story = {
  args: { ripple: RIPPLE },
  render: () => (
    <div className="w-80">
      <SelectedNode trend={null} commodity="Unobtainium" />
    </div>
  ),
};

/** The written explanation of what the chain means. */
export const Report: Story = {
  args: { ripple: RIPPLE },
  render: () => <PropagationReport ripple={RIPPLE} />,
};
