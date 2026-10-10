/** Persian/Arabic digit and decimal-separator helpers.
 *
 * Telegram's Persian keyboard and the Vazirmatn font produce Persian
 * digits (۰-۹) and the Arabic decimal separator (٫). JavaScript's
 * Number() cannot parse these — it returns NaN. Every numeric input
 * that comes from the user must be normalised first.
 */

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";

/** Convert Persian + Arabic digits to ASCII and replace Arabic decimal
 *  separator (٫) with a dot. Trims surrounding whitespace. */
export function normalizeDigits(input: string): string {
  let out = input.trim();
  for (let i = 0; i < 10; i++) {
    out = out.replaceAll(PERSIAN_DIGITS[i], String(i));
    out = out.replaceAll(ARABIC_DIGITS[i], String(i));
  }
  out = out.replaceAll("٫", ".").replaceAll("،", ".");
  return out;
}

/** Parse a possibly-Persian numeric string into a float, or NaN. */
export function parseNumber(input: string): number {
  return Number(normalizeDigits(input));
}

/** Parse and return null when the result is NaN (for optional fields). */
export function parseOptionalNumber(input: string): number | null {
  const n = parseNumber(input);
  return Number.isNaN(n) ? null : n;
}
