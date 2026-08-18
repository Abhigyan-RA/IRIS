import type { Meta, StoryObj } from '@storybook/react-vite';
import { Delta } from './Delta';

const meta = {
  title: 'Primitives/Delta',
  component: Delta,
} satisfies Meta<typeof Delta>;

export default meta;

type Story = StoryObj<typeof meta>;

/** A rising cost, which this product treats as bad news. */
export const Rise: Story = {
  args: { value: 8.2 },
};

/** A falling cost. */
export const Fall: Story = {
  args: { value: -2.1 },
};

/** No change was reported, which is not the same as a change of zero. */
export const Unreported: Story = {
  args: { value: null },
};

/** Exactly flat. */
export const Flat: Story = {
  args: { value: 0 },
};

/** With a window label, as shown beside a selected entity. */
export const WithPeriod: Story = {
  args: { value: 8.4, period: '7d' },
};
