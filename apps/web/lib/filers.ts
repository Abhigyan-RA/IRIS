/**
 * Turning a filer's registered name into the label a professional screen shows.
 *
 * Filings carry the full legal name, because that is what a registration requires:
 * "Point72 Asset Management LP", "Fidelity Management & Research Company LLC". A
 * dense table does not benefit from the legal form, and long names push the figures
 * that matter off the row. The desk convention, which the design references follow,
 * is to name the house and drop the paperwork.
 *
 * The registered name is never thrown away: callers show it as the accessible title
 * of the row, so the exact filed entity is always one hover or one screen reader stop
 * away. Shortening is presentation, not a change to the record.
 */

/**
 * Legal forms that add nothing on screen. Order matters only in that longer, more
 * specific spellings are matched before shorter ones.
 */
const LEGAL_FORMS = [
  'l.l.c.',
  'llc',
  'l.p.',
  'lp',
  'inc.',
  'inc',
  'ltd.',
  'ltd',
  'plc',
  'company',
  'co.',
];

/**
 * Words abbreviated the way a desk writes them.
 */
const ABBREVIATIONS: readonly (readonly [RegExp, string])[] = [
  [/\bmanagement\b/gi, 'Mgt'],
  [/\bmanagements\b/gi, 'Mgt'],
];

/**
 * Shorten a registered filer name to a professional screen label.
 *
 * @param registeredName - The name exactly as filed.
 * @returns The label to display. The input is returned unchanged when shortening
 * would leave nothing to name the fund by, because a row with no name is worse than
 * a row with a legal form in it.
 */
export function professionalFilerLabel(registeredName: string): string {
  let label = registeredName.trim();
  if (label === '') {
    return registeredName;
  }

  // Strip legal forms from the end, repeatedly: a name can carry more than one, as
  // in "D E Shaw & Co Inc", where only the last is paperwork.
  let stripped = true;
  while (stripped) {
    stripped = false;
    for (const form of LEGAL_FORMS) {
      const pattern = new RegExp(`[\\s,]+${escapeForPattern(form)}$`, 'i');
      const candidate = label.replace(pattern, '');
      // Keep the word when removing it would leave only a fragment, so a house
      // genuinely called "… Co" still reads as a name.
      if (candidate !== label && candidate.trim() !== '' && hasNameWord(candidate)) {
        label = candidate.trim();
        stripped = true;
        break;
      }
    }
  }

  for (const [pattern, replacement] of ABBREVIATIONS) {
    label = label.replace(pattern, replacement);
  }

  // A trailing separator can be left behind once a legal form is removed.
  label = label.replace(/[\s,&]+$/, '').trim();
  return label === '' ? registeredName : label;
}

/**
 * Whether a candidate label still contains a word that names the house.
 *
 * @param candidate - Label with a legal form removed.
 * @returns True when something nameable remains.
 */
function hasNameWord(candidate: string): boolean {
  return /[a-z0-9]/i.test(candidate.replace(/[\s,&.]/g, ''));
}

/**
 * Escape a literal for use inside a regular expression.
 *
 * @param literal - Text to match exactly.
 * @returns The escaped text.
 */
function escapeForPattern(literal: string): string {
  return literal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
