/**
 * settings.js — localStorage-backed user preferences.
 *
 * Centralized so anywhere in the app can read/write settings via these
 * functions instead of touching localStorage keys directly. Makes it
 * easy to rename keys later or migrate to a backend later.
 *
 * Settings are read on demand. There's no global subscription — components
 * that need live updates should read on render (cheap) or via a custom event.
 */

const KEYS = {
  pollIntervalMs: 'overwatch.settings.pollIntervalMs',
  // Tier-2 ring escalation (ADR-0019). Android-only in practice (ringAlarm.js
  // gates on isNative()), but the preference itself is stored the same way
  // as everything else so it survives reinstalls-with-backup and is easy to
  // inspect/reset alongside other settings.
  ringEscalationEnabled: 'overwatch.settings.ringEscalationEnabled',
}

const DEFAULTS = {
  pollIntervalMs: 30 * 1000, // 30 seconds
  // Default ON: this app has exactly one real user today (the founder), who
  // explicitly asked for "the phone actually rings" behavior — see ADR-0019.
  // Revisit the default once there are users who didn't ask for this.
  ringEscalationEnabled: true,
}

/** Read a single setting with fallback to default. */
export function getSetting(key) {
  const raw = localStorage.getItem(KEYS[key])
  if (raw === null) return DEFAULTS[key]
  try {
    return JSON.parse(raw)
  } catch {
    return DEFAULTS[key]
  }
}

/** Write a single setting. Fires a window event so listeners can react. */
export function setSetting(key, value) {
  localStorage.setItem(KEYS[key], JSON.stringify(value))
  window.dispatchEvent(new CustomEvent('overwatch-settings-changed', { detail: { key, value } }))
}

/** Read all settings as a flat object. */
export function getAllSettings() {
  return Object.keys(KEYS).reduce((acc, k) => {
    acc[k] = getSetting(k)
    return acc
  }, {})
}

export const POLL_INTERVAL_PRESETS = [
  { label: '10s (testing)', value: 10 * 1000 },
  { label: '30s (default)', value: 30 * 1000 },
  { label: '1 min', value: 60 * 1000 },
  { label: '5 min', value: 5 * 60 * 1000 },
]
