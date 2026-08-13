/**
 * Deterministic color per section (group_name) tag, purely for visual
 * identity in chips/pills — no new data, no color picker to maintain.
 * Same name always yields the same hue, so a section reads as "the same
 * thing" across the filter row, the create form, and each todo's pill.
 *
 * Kept muted/desaturated so tags don't fight the accent orange used for
 * primary actions (FAB, active chip, Save button).
 */
export function colorForSection(name) {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash << 5) - hash + name.charCodeAt(i)
    hash |= 0
  }
  const hue = Math.abs(hash) % 360
  return `hsl(${hue}, 45%, 62%)`
}
