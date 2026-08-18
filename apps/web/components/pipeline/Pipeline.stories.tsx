import type { Meta, StoryObj } from '@storybook/react-vite';
import type { HealthEvent } from '../../lib/api';
import { AuditLog } from './AuditLog';
import { CollectorHealth } from './CollectorHealth';

function event(overrides: Partial<HealthEvent> = {}): HealthEvent {
  return {
    scraper_id: 'fbx_scraper',
    source_name: 'data.freightos.com',
    event_type: 'success',
    message: '[OK] 12 rows returned with all required fields',
    occurred_at: '2026-08-15T03:05:00Z',
    ...overrides,
  };
}

/** A complete repair, which is the sequence this screen exists to show. */
const REPAIR_SEQUENCE: HealthEvent[] = [
  event({
    event_type: 'self_heal_resolved',
    occurred_at: '2026-08-15T03:03:20Z',
    message: '[RESOLVED] collection resumed: 12 rows returned with all required fields',
  }),
  event({
    event_type: 'self_heal_triggered',
    occurred_at: '2026-08-15T03:02:00Z',
    message: '[AUTO-HEALING] repair requested for: price',
  }),
  event({
    event_type: 'dom_shift_detected',
    occurred_at: '2026-08-15T03:00:12Z',
    message: '[WARNING] data.freightos.com looks different: no rows returned',
  }),
  event({
    scraper_id: 'oilprice_scraper',
    source_name: 'oilprice.com',
    event_type: 'self_heal_failed',
    occurred_at: '2026-08-15T02:41:45Z',
    message: '[FAILED] price still missing after repair: no rows returned',
  }),
  event({
    scraper_id: 'lme_copper_scraper',
    source_name: 'investing.com',
    occurred_at: '2026-08-15T02:15:02Z',
    message: '[OK] 1 rows returned with all required fields',
  }),
];

const meta = {
  title: 'Screens/Pipeline health',
  component: AuditLog,
} satisfies Meta<typeof AuditLog>;

export default meta;

type Story = StoryObj<typeof meta>;

/** A collector breaking, repairing itself, and resuming. */
export const RepairSequence: Story = {
  args: { events: REPAIR_SEQUENCE },
};

/** Everything running normally. */
export const AllHealthy: Story = {
  args: {
    events: [event(), event({ scraper_id: 'lme_copper_scraper', source_name: 'investing.com' })],
  },
};

/** Nothing has run yet. */
export const Empty: Story = {
  args: { events: [] },
};

/** The collector summary derived from the same feed. */
export const CollectorSummary: Story = {
  args: { events: [] },
  render: () => (
    <div className="w-80">
      <CollectorHealth events={REPAIR_SEQUENCE} />
    </div>
  ),
};

/** The collector summary with nothing reported. */
export const CollectorSummaryEmpty: Story = {
  args: { events: [] },
  render: () => (
    <div className="w-80">
      <CollectorHealth events={[]} />
    </div>
  ),
};
