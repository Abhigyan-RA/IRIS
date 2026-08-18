import type { Meta, StoryObj } from '@storybook/react-vite';
import { Sparkline } from './Sparkline';

const meta = {
  title: 'Charts/Sparkline',
  component: Sparkline,
} satisfies Meta<typeof Sparkline>;

export default meta;

type Story = StoryObj<typeof meta>;

/** A rising series, drawn in the accent colour. */
export const Rising: Story = {
  args: {
    values: [4.1, 4.15, 4.2, 4.34, 4.4, 4.52],
    label: 'Copper, 30 day trend, rising',
  },
};

/** A falling series, drawn green because a falling cost is good news here. */
export const Falling: Story = {
  args: {
    values: [86.2, 85.1, 84.4, 83.2, 82.4],
    label: 'Brent crude, 30 day trend, falling',
    strokeClassName: 'stroke-fall',
  },
};

/** A flat series, drawn along the middle rather than collapsing. */
export const Flat: Story = {
  args: { values: [5, 5, 5, 5], label: 'Unchanged' },
};

/** Not enough history yet, which is stated rather than drawn as a dot. */
export const NotEnoughHistory: Story = {
  args: { values: [4.52], label: 'Copper trend' },
};
