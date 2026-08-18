import type { ReactNode } from 'react';

/**
 * Props for {@link Panel}.
 */
export interface PanelProps {
  /** Content of the panel. */
  children: ReactNode;
  /** Extra classes for layout, such as a column span or a fixed height. */
  className?: string;
}

/**
 * The surface everything in this interface sits on.
 *
 * One component rather than repeated utility classes, so the border, radius, and
 * background stay identical across five screens. When the design changes, this is
 * the only place to edit.
 *
 * @param props - Content and optional layout classes.
 * @returns The panel.
 */
export function Panel({ children, className = '' }: PanelProps): ReactNode {
  return (
    <div className={`rounded-card border border-hairline bg-panel ${className}`}>{children}</div>
  );
}

/**
 * Props for {@link SectionLabel}.
 */
export interface SectionLabelProps {
  /** The label text. Rendered upper case by the style, not by the caller. */
  children: ReactNode;
  /**
   * Whether this titles a primary panel. Primary titles are in the accent colour
   * and secondary ones in muted grey, which is how the design separates "this panel
   * is the point of the screen" from "this is a supporting list".
   */
  tone?: 'primary' | 'secondary';
  /** Extra classes for spacing. */
  className?: string;
}

/**
 * A small upper-case heading above a panel or a group.
 *
 * @param props - The text, its prominence, and optional spacing classes.
 * @returns The heading.
 */
export function SectionLabel({
  children,
  tone = 'secondary',
  className = '',
}: SectionLabelProps): ReactNode {
  const colour = tone === 'primary' ? 'text-accent' : 'text-ink-muted';
  return (
    <h2 className={`text-label font-semibold uppercase ${colour} ${className}`}>{children}</h2>
  );
}
