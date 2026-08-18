import type { Meta, StoryObj } from '@storybook/react-vite';
import { MetricCard } from './MetricCard';

const meta = {
  title: 'Primitives/MetricCard',
  component: MetricCard,
} satisfies Meta<typeof MetricCard>;

export default meta;

type Story = StoryObj<typeof meta>;

/** A figure with its change and its source, as shown under a copilot answer. */
export const Default: Story = {
  args: {
    label: 'Steel HRC US',
    value: '840',
    unit: 'ton',
    currencySymbol: '$',
    change: 8.2,
    sourceName: 'COMEX / Chicago Spot',
  },
};

/** A falling cost. */
export const Falling: Story = {
  args: {
    label: 'EU Brent crude',
    value: '82.40',
    unit: 'bbl',
    currencySymbol: '$',
    change: -2.1,
    sourceName: 'eia.gov',
    sourceUrl: 'https://api.eia.gov/v2/petroleum/pri/spt/data',
  },
};

/** Behind its freshness target, which is stated rather than hidden. */
export const Stale: Story = {
  args: {
    label: 'Baltic Dry Index',
    value: '2045',
    unit: 'index_point',
    change: 5.1,
    sourceName: 'tradingeconomics.com',
    isStale: true,
  },
};

/** While the figure is being fetched. */
export const Loading: Story = {
  args: { label: 'Copper', isLoading: true },
};

/** Nothing recorded yet, said plainly instead of shown as a blank. */
export const Empty: Story = {
  args: { label: 'Lithium Carbonate', value: null, sourceName: 'not yet collected' },
};
