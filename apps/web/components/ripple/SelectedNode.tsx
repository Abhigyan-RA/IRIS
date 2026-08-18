import type { ReactNode } from 'react';
import type { Ripple, Trend } from '../../lib/api';
import { Sparkline } from '../charts/Sparkline';
import { Delta } from '../primitives/Delta';
import { Panel, SectionLabel } from '../primitives/Panel';

/**
 * Props for {@link SelectedNode}.
 */
export interface SelectedNodeProps {
  /** Price history for the selected entity, or null when none is recorded. */
  trend: Trend | null;
  /** Name of the entity, used when there is no history to name it. */
  commodity: string;
}

/**
 * The selected entity: its latest price, its recent trend, and where it came from.
 *
 * @param props - The history and the entity name.
 * @returns The panel.
 */
export function SelectedNode({ trend, commodity }: SelectedNodeProps): ReactNode {
  if (trend === null) {
    return (
      <section aria-labelledby="selected-heading" className="space-y-3">
        <SectionLabel tone="primary">
          <span id="selected-heading">Selected node</span>
        </SectionLabel>
        <h1 className="text-title text-ink">{commodity}</h1>
        <p className="text-sm text-ink-faint">
          No price has been recorded for this entity yet, so only its supply-chain relationships are
          shown.
        </p>
      </section>
    );
  }

  const values = trend.points.map((point) => Number.parseFloat(point.price));
  const isRising = (values.at(-1) ?? 0) >= (values[0] ?? 0);

  return (
    <section aria-labelledby="selected-heading" className="space-y-4">
      <SectionLabel tone="primary">
        <span id="selected-heading">Selected node</span>
      </SectionLabel>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-title text-ink">{trend.entity_name}</h1>
        <Delta value={trend.change_pct_over_window} period={`${String(trend.days)}d`} />
      </div>

      <p className="tabular text-xl text-ink">
        {trend.latest_price} {trend.currency}
        <span className="text-ink-muted"> / {trend.unit}</span>
      </p>

      <div className="space-y-2 border-t border-hairline pt-4">
        <p className="text-label text-ink-muted uppercase">{trend.days}-day exchange value</p>
        <Sparkline
          values={values}
          width={280}
          height={80}
          strokeClassName={isRising ? 'stroke-rise' : 'stroke-fall'}
          label={`${trend.entity_name}, ${String(trend.days)} day trend, ${
            isRising ? 'rising' : 'falling'
          }`}
        />
      </div>

      <p className="border-t border-hairline pt-4 text-xs text-ink-faint">
        Data from{' '}
        <a
          href={trend.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="underline decoration-hairline-strong hover:text-accent"
        >
          {trend.source_name}
        </a>
        . Last point recorded {trend.points.at(-1)?.recorded_at ?? 'unknown'}.
      </p>
    </section>
  );
}

/**
 * Props for {@link PropagationReport}.
 */
export interface PropagationReportProps {
  /** The traversal result, which carries the explanation when one was produced. */
  ripple: Ripple;
}

/**
 * The plain-language reading of what the chain means.
 *
 * The explanation is written by the model from the relationships found in the graph.
 * When none was produced, the panel is left out entirely rather than shown empty:
 * the industries listed beside it are the substance, and an empty box implies
 * something is missing when nothing is.
 *
 * @param props - The traversal result.
 * @returns The report, or nothing.
 */
export function PropagationReport({ ripple }: PropagationReportProps): ReactNode {
  if (ripple.explanation === null || ripple.explanation.trim() === '') {
    return null;
  }

  return (
    <Panel className="border-accent p-4">
      <p className="text-label text-accent uppercase">Propagation report</p>
      <p className="mt-2 text-sm leading-relaxed text-ink">{ripple.explanation}</p>
      {ripple.affected_industries.length > 0 && (
        <p className="mt-3 text-xs text-ink-faint">
          Grounded in {ripple.links.length} recorded{' '}
          {ripple.links.length === 1 ? 'relationship' : 'relationships'} reaching{' '}
          {ripple.affected_industries.length}{' '}
          {ripple.affected_industries.length === 1 ? 'industry' : 'industries'}.
        </p>
      )}
    </Panel>
  );
}
