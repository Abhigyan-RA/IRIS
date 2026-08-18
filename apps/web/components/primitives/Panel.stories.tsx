import type { Meta, StoryObj } from '@storybook/react-vite';
import { Panel, SectionLabel } from './Panel';

const meta = {
  title: 'Primitives/Panel',
  component: Panel,
} satisfies Meta<typeof Panel>;

export default meta;

type Story = StoryObj<typeof meta>;

/** The plain surface, as used for every block on every screen. */
export const Default: Story = {
  args: {
    children: <p className="p-4 text-ink-muted">Panel content</p>,
  },
};

/** With a supporting heading, as above the movers row. */
export const WithSecondaryLabel: Story = {
  args: { children: null },
  render: () => (
    <div className="space-y-3">
      <SectionLabel>Top movers (24h)</SectionLabel>
      <Panel>
        <p className="p-4 text-ink-muted">Six cards sit here.</p>
      </Panel>
    </div>
  ),
};

/** With a primary heading, as used for the panel a screen is built around. */
export const WithPrimaryLabel: Story = {
  args: { children: null },
  render: () => (
    <div className="space-y-3">
      <SectionLabel tone="primary">Shadow CPI index</SectionLabel>
      <Panel>
        <p className="tabular p-4 text-headline">114.7</p>
      </Panel>
    </div>
  ),
};
