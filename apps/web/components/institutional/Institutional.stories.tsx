import type { Meta, StoryObj } from '@storybook/react-vite';
import type { Holders } from '../../lib/api';
import { HoldersTable } from './HoldersTable';
import { TickerPicker } from './TickerPicker';

type Holder = Holders['holders'][number];

function holder(overrides: Partial<Holder> = {}): Holder {
  return {
    filer_name: 'Bridgewater Associates',
    filer_cik: '0001350694',
    shares_held: 14_850_200,
    market_value_usd: '1240000000.00',
    pct_portfolio: '6.8',
    shares_change_qoq: 1_600_000,
    delta_pct: '12.4',
    quarter_end: '2026-06-30',
    source_url: 'https://www.sec.gov/edgar/browse/?CIK=0001350694',
    ...overrides,
  };
}

const meta = {
  title: 'Screens/Institutional',
  component: HoldersTable,
} satisfies Meta<typeof HoldersTable>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Several funds holding the same stock, largest position first. */
export const Populated: Story = {
  args: {
    holders: {
      ticker: 'XOM',
      holders: [
        holder(),
        holder({
          filer_name: 'Berkshire Hathaway',
          filer_cik: '0001067983',
          shares_held: 28_410_500,
          market_value_usd: '3450000000.00',
          pct_portfolio: '11.2',
          shares_change_qoq: -600_000,
          delta_pct: '-2.1',
        }),
        holder({
          filer_name: 'Renaissance Technologies',
          filer_cik: '0001037389',
          shares_held: 5_120_400,
          market_value_usd: '230400000.00',
          pct_portfolio: '4.1',
          shares_change_qoq: null,
          delta_pct: null,
        }),
      ],
    },
  },
};

/** No fund has reported this stock. */
export const Empty: Story = {
  args: { holders: { ticker: 'XOM', holders: [] } },
};

/** The picker that puts the chosen ticker in the URL. */
export const Picker: Story = {
  args: { holders: { ticker: 'NVDA', holders: [] } },
  render: () => <TickerPicker ticker="NVDA" />,
};
