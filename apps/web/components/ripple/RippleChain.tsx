import type { ReactNode } from 'react';
import type { Ripple } from '../../lib/api';
import { Panel, SectionLabel } from '../primitives/Panel';

/**
 * Group the chain into the layers a reader thinks in: the raw material, what it is
 * made into, and the industries that then depend on it.
 *
 * A force-directed drawing looks impressive and is hard to read: nodes move between
 * renders, labels overlap, and nothing can be reached by keyboard. Layers are
 * legible, stable, and navigable, and they carry the same information.
 *
 * @param ripple - The traversal result from the API.
 * @returns One group per layer, in downstream order, each with its members.
 */
export function chainLayers(ripple: Ripple): { kind: string; members: string[] }[] {
  const byKind = new Map<string, Set<string>>();

  for (const node of ripple.nodes) {
    if (node.name === ripple.commodity) {
      continue;
    }
    const members = byKind.get(node.kind) ?? new Set<string>();
    members.add(node.name);
    byKind.set(node.kind, members);
  }

  // Components sit between a raw material and the industry that uses it, so they are
  // shown in that order regardless of the order the graph returned them in.
  const order = ['Component', 'Industry', 'Company', 'Commodity'];
  return [...byKind.entries()]
    .sort(([left], [right]) => order.indexOf(left) - order.indexOf(right))
    .map(([kind, members]) => ({ kind, members: [...members].sort() }));
}

/**
 * Props for {@link RippleChain}.
 */
export interface RippleChainProps {
  /** The traversal result to draw. */
  ripple: Ripple;
}

/**
 * What a commodity feeds into, drawn as layers.
 *
 * @param props - The traversal result.
 * @returns The chain.
 */
export function RippleChain({ ripple }: RippleChainProps): ReactNode {
  const layers = chainLayers(ripple);

  return (
    <section aria-labelledby="chain-heading" className="space-y-3">
      <SectionLabel tone="primary">
        <span id="chain-heading">Propagation map</span>
      </SectionLabel>

      {layers.length === 0 ? (
        <Panel className="p-6">
          <p className="text-sm text-ink-faint">
            Nothing downstream of {ripple.commodity} is mapped yet. Relationships are added to the
            graph as they are confirmed, so this is a gap in coverage rather than a claim that
            nothing is affected.
          </p>
        </Panel>
      ) : (
        <Panel className="p-6">
          <ol className="flex flex-wrap items-start gap-6">
            <li className="space-y-2">
              <p className="text-label text-ink-muted uppercase">Commodity</p>
              <span className="inline-block rounded-card border border-accent px-3 py-2 text-sm text-accent">
                {ripple.commodity}
              </span>
            </li>

            {layers.map((layer) => (
              <li key={layer.kind} className="space-y-2">
                <p className="text-label text-ink-muted uppercase">{layer.kind}</p>
                <ul className="space-y-2">
                  {layer.members.map((member) => (
                    <li key={member}>
                      <span className="inline-block rounded-card border border-hairline-strong bg-panel-raised px-3 py-2 text-sm text-ink">
                        {member}
                      </span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </Panel>
      )}
    </section>
  );
}

/**
 * Props for {@link RippleLinks}.
 */
export interface RippleLinksProps {
  /** The traversal result to list. */
  ripple: Ripple;
}

/**
 * Every step in the chain, written out.
 *
 * The layered drawing shows what is connected; this says how, including the share of
 * an industry's cost a commodity accounts for where the graph records it. It is also
 * what a screen-reader user reads instead of the drawing.
 *
 * @param props - The traversal result.
 * @returns The list of steps.
 */
export function RippleLinks({ ripple }: RippleLinksProps): ReactNode {
  if (ripple.links.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="links-heading" className="space-y-3">
      <SectionLabel>
        <span id="links-heading">Relationships</span>
      </SectionLabel>

      <Panel className="divide-y divide-hairline">
        {ripple.links.map((link) => (
          <p
            key={`${link.source}-${link.relationship}-${link.target}`}
            className="flex flex-wrap items-baseline gap-2 p-3 text-sm"
          >
            <span className="text-ink">{link.source}</span>
            <span className="text-ink-faint">
              {link.relationship.toLowerCase().replace(/_/g, ' ')}
            </span>
            <span className="text-ink">{link.target}</span>
            {link.weight !== null && (
              <span className="tabular ml-auto text-ink-muted">
                {Math.round(link.weight * 100)}% of input cost
              </span>
            )}
          </p>
        ))}
      </Panel>
    </section>
  );
}
