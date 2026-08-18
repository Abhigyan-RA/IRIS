import type { Meta, StoryObj } from '@storybook/react-vite';
import { LivePill } from './LivePill';

const meta = {
  title: 'Shell/LivePill',
  component: LivePill,
} satisfies Meta<typeof LivePill>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Collection is running and recent. */
export const Live: Story = {
  args: { updatedLabel: '2m ago' },
};

/** Collection has stopped, which the badge states rather than implies. */
export const Stopped: Story = {
  args: { updatedLabel: '41m ago', isLive: false },
};
