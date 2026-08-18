import type { Meta, StoryObj } from '@storybook/react-vite';
import type { RiskMap, RiskMapEntry } from '../../lib/api';
import { ContributionBreakdown, IndexSummary } from './IndexSummary';
import { RiskMapPanel } from './RiskMapPanel';
import { TopMovers } from './TopMovers';

function entry(overrides: Partial<RiskMapEntry> = {}): RiskMapEntry {
  return {
    entity_name: 'Copper',
    region: 'Global',
    sector: 'metals',
    price: '4.52',
    currency: 'USD',
    unit: 'lb',
    pct_change_1d: '1.8',
    pct_change_7d: null,
    recorded_at: '2026-08-15T12:00:00Z',
    source_name: 'investing.com',
    source_url: 'https://www.investing.com/commodities/copper',
    ingestion_method: 'brightdata_scrape',
    is_stale: false,
    ...overrides,
  };
}

const BUSY_MAP: RiskMap = {
  generated_at: '2026-08-15T14:32:05Z',
  sectors: [
    {
      sector: 'metals',
      entries: [
        entry({
          entity_name: 'Steel_HRC_US',
          region: 'North America',
          price: '840',
          unit: 'ton',
          pct_change_1d: '8.2',
        }),
        entry({ entity_name: 'Copper', pct_change_1d: '1.8' }),
      ],
    },
    {
      sector: 'freight',
      entries: [
        entry({
          entity_name: 'FBX_Global',
          sector: 'freight',
          unit: 'feu',
          price: '5240',
          pct_change_1d: '12.4',
        }),
      ],
    },
    {
      sector: 'energy',
      entries: [
        entry({
          entity_name: 'Brent_Crude',
          sector: 'energy',
          region: 'Europe',
          unit: 'barrel',
          price: '82.40',
          pct_change_1d: '-2.1',
          is_stale: true,
        }),
      ],
    },
  ],
};

const EMPTY_MAP: RiskMap = { generated_at: '2026-08-15T14:32:05Z', sectors: [] };

const meta = {
  title: 'Screens/Risk map',
  component: RiskMapPanel,
} satisfies Meta<typeof RiskMapPanel>;

export default meta;

type Story = StoryObj<typeof meta>;

/** The map with markers over the regions that moved. */
export const Map: Story = {
  args: { entries: BUSY_MAP.sectors.flatMap((group) => group.entries) },
};

/** Before any price has been collected. */
export const MapEmpty: Story = {
  args: { entries: [] },
};

/** The movers row, ranked by the size of the move. */
export const Movers: Story = {
  args: { entries: [] },
  render: () => <TopMovers entries={BUSY_MAP.sectors.flatMap((group) => group.entries)} />,
};

/** The movers row with nothing to rank yet. */
export const MoversEmpty: Story = {
  args: { entries: [] },
  render: () => <TopMovers entries={[]} />,
};

/** The right-hand summary column. */
export const Summary: Story = {
  args: { entries: [] },
  render: () => (
    <div className="w-80 space-y-8">
      <IndexSummary map={BUSY_MAP} />
      <ContributionBreakdown map={BUSY_MAP} />
    </div>
  ),
};

/** The summary column with nothing collected. */
export const SummaryEmpty: Story = {
  args: { entries: [] },
  render: () => (
    <div className="w-80 space-y-8">
      <IndexSummary map={EMPTY_MAP} />
      <ContributionBreakdown map={EMPTY_MAP} />
    </div>
  ),
};
