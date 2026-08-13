/**
 * timezone.js — the device's IANA timezone name, sent to the backend so it
 * resolves "today"/"tonight"/relative times against the user's actual clock
 * instead of the server's (see backend/app/services/timezone_utils.py).
 *
 * Hermes has supported Intl.DateTimeFormat's resolvedOptions().timeZone
 * since RN's Intl polyfill landed (no extra native module needed). Falls
 * back to null (server defaults to UTC) if anything about that is
 * unavailable — never throws, matching resolve_timezone()'s own "missing
 * is fine" contract on the backend.
 */
export function getDeviceTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null
  } catch {
    return null
  }
}
