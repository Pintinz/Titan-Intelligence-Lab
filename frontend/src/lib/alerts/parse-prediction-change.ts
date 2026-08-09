/** `notify_watchers` (prediction_cache_service.py) writes a fixed real template — "The
 * prediction for {subject_ref} changed to {value}." — no market name or previous confidence/
 * probability exists anywhere on the alert event, so this only ever recovers the new value.
 * Returns null (never a guess) if the body doesn't match the known template, so a future backend
 * copy change degrades to the honest raw-body fallback instead of misparsing. */
export function parsePredictionChangeValue(body: string): string | null {
  const match = body.match(/changed to (.+)\.$/)
  return match ? match[1] : null
}
