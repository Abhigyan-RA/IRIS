import type { Meta, StoryObj } from '@storybook/react-vite';
import { StatusDot } from './StatusDot';

const meta = {
  title: 'Primitives/StatusDot',
  component: StatusDot,
  parameters: {
    backgrounds: { default: 'canvas' },
  },
} satisfies Meta<typeof StatusDot>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Everything is running normally. */
export const Healthy: Story = {
  args: { status: 'healthy', label: 'Freight and shipping' },
};

/** Running, but behind its freshness target. */
export const Degraded: Story = {
  args: { status: 'degraded', label: 'Energy and materials' },
};

/** Not running: the collector could not be repaired. */
export const Failed: Story = {
  args: { status: 'failed', label: 'Oil price feed' },
};

/** Actively updating right now. */
export const Live: Story = {
  args: { status: 'live', label: 'Aggregate health' },
};

/** All four side by side, which is how they appear across the health screen. */
export const AllStates: Story = {
  args: { status: 'healthy', label: 'Freight' },
  render: () => (
    <div className="flex items-center gap-6">
      <StatusDot status="healthy" label="Freight" />
      <StatusDot status="degraded" label="Energy" />
      <StatusDot status="failed" label="Oil price feed" />
      <StatusDot status="live" label="Aggregate" />
    </div>
  ),
};
