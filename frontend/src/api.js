/**
 * api.js — Backend API client.
 *
 * Thin wrappers around fetch() for each endpoint. Returns parsed JSON
 * (or null for 204 No Content). Throws on non-2xx responses so callers
 * can catch + display errors.
 *
 * Uses relative paths (/commitments). Vite's dev server proxies them
 * to http://localhost:8000 (configured in vite.config.js). In production
 * (Vercel), VITE_API_BASE_URL points at the Railway backend URL.
 *
 * Every request sends credentials (cookies) so the session JWT travels
 * with each call.
 */

import { isNative, getStoredToken, setStoredToken, clearStoredToken, nativeGoogleLogin } from './lib/native'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

/** Export the base so the native login flow can build the login URL. */
export function apiBase() {
  return API_BASE
}

/**
 * The browser's IANA timezone (e.g. "America/Toronto"), or undefined if
 * Intl isn't available (very old browser). Used anywhere the backend needs
 * to know what "today" means for this user — chat, briefings, reflections —
 * rather than defaulting to UTC, which is wrong for most users most of the
 * day (see ADR-0023's follow-up on the UTC date-bucketing bug).
 */
function getBrowserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone
  } catch {
    return undefined
  }
}

/**
 * Wrapped fetch with a stable base URL prefix.
 *
 * Web: relies on the session cookie (credentials: 'include').
 * Native: there are no cookies in the webview, so we attach the stored
 * session token as `Authorization: Bearer <token>`.
 */
async function apiFetch(path, options = {}) {
  const authHeader = {}
  if (isNative()) {
    const token = await getStoredToken()
    if (token) authHeader.Authorization = `Bearer ${token}`
  }

  // Retry transient NETWORK failures (browser "Failed to fetch" — a one-off
  // dropped connection, a blip during a redeploy, etc.). Only safe, idempotent
  // GETs are retried so we never accidentally double-create on a POST/PATCH.
  // HTTP error responses (401/404/500) are NOT retried — those are real.
  const method = (options.method || 'GET').toUpperCase()
  const maxAttempts = method === 'GET' ? 3 : 1

  let lastErr
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        credentials: 'include',
        ...options,
        headers: {
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
          ...authHeader,
          ...(options.headers || {}),
        },
      })

      if (!response.ok) {
        // Surface 401 specially — callers can react with "redirect to login".
        if (response.status === 401) {
          const err = new Error('Not signed in')
          err.status = 401
          throw err
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      if (response.status === 204) return null
      return await response.json()
    } catch (err) {
      // fetch() throws a TypeError only for network-level failures; the HTTP
      // errors thrown above are plain Errors. Retry only the former.
      const isNetworkError = err instanceof TypeError
      if (!isNetworkError || attempt === maxAttempts) throw err
      lastErr = err
      await new Promise((resolve) => setTimeout(resolve, attempt * 400)) // 400ms, 800ms
    }
  }
  throw lastErr
}

// ---------------------------------------------------------------------------
// Commitments
// ---------------------------------------------------------------------------

export async function listCommitments(statusFilter = null) {
  const params = statusFilter ? `?status_filter=${statusFilter}` : ''
  return apiFetch(`/commitments${params}`)
}

export async function createCommitment(text, dueAt = null) {
  return apiFetch('/commitments', {
    method: 'POST',
    body: JSON.stringify({ text, due_at: dueAt }),
  })
}

export async function parseCommitment(message) {
  return apiFetch('/commitments/parse', {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
}

export async function updateCommitment(id, changes) {
  return apiFetch(`/commitments/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  })
}

export async function deleteCommitment(id) {
  return apiFetch(`/commitments/${id}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// Briefings
// ---------------------------------------------------------------------------

export async function getTodayBriefing(force = false) {
  const params = new URLSearchParams()
  if (force) params.set('force_regenerate', 'true')
  const tz = getBrowserTimezone()
  if (tz) params.set('timezone', tz)
  const qs = params.toString()
  return apiFetch(`/briefings/today${qs ? `?${qs}` : ''}`)
}

// ---------------------------------------------------------------------------
// Reflections
// ---------------------------------------------------------------------------

export async function getTodayReflection(force = false) {
  const params = new URLSearchParams()
  if (force) params.set('force_regenerate', 'true')
  const tz = getBrowserTimezone()
  if (tz) params.set('timezone', tz)
  const qs = params.toString()
  return apiFetch(`/reflections/today${qs ? `?${qs}` : ''}`)
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

/** Whether the signed-in user has linked their Google Calendar. */
export async function getCalendarConnection() {
  return apiFetch('/calendar/connection')
}

/** Disconnect the user's Google Calendar (deletes stored tokens). */
export async function disconnectCalendar() {
  return apiFetch('/calendar/disconnect', { method: 'POST' })
}

/**
 * Full URL that kicks off the Google Calendar OAuth flow. This is a
 * top-level navigation (window.location), NOT a fetch — Google redirects
 * the browser through its consent screen and back to the backend callback,
 * which then redirects to the frontend with ?calendar=connected.
 */
export function googleCalendarConnectUrl() {
  return `${API_BASE}/calendar/connect/google`
}

// ---------------------------------------------------------------------------
// Web Push subscriptions
// ---------------------------------------------------------------------------

export async function getVapidPublicKey() {
  return apiFetch('/push/vapid-public-key')
}

export async function subscribeToPush(subscription) {
  return apiFetch('/push/subscribe', {
    method: 'POST',
    body: JSON.stringify(subscription),
  })
}

export async function unsubscribeFromPush(endpoint) {
  return apiFetch('/push/unsubscribe', {
    method: 'POST',
    body: JSON.stringify({ endpoint }),
  })
}

export async function sendTestPush() {
  return apiFetch('/push/test', { method: 'POST' })
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export async function sendChat(message, history = []) {
  return apiFetch('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, history, timezone: getBrowserTimezone() }),
  })
}

/** Load the signed-in user's recent conversation turns (oldest-first). */
export async function getChatHistory(limit = 50) {
  return apiFetch(`/chat/history?limit=${limit}`)
}

/** Delete all of the signed-in user's conversation history. */
export async function clearChatHistory() {
  return apiFetch('/chat/history', { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/**
 * Fetch the current signed-in user. Returns null (not throw) on 401 so
 * callers can distinguish "not signed in" from a real error.
 */
export async function getCurrentUser() {
  try {
    return await apiFetch('/auth/me')
  } catch (err) {
    if (err.status === 401) return null
    throw err
  }
}

/**
 * Start sign-in.
 *
 * Web: navigate the window to Google's OAuth consent screen (cookie flow).
 * Native: open the system browser, capture the deep-linked token, store it.
 * Returns a promise on native (resolves after token capture); on web it
 * navigates away and never resolves.
 */
export async function startGoogleLogin() {
  if (isNative()) {
    await nativeGoogleLogin(API_BASE)
    return
  }
  window.location.href = `${API_BASE}/auth/google/login`
}

/** Clear the session — server cookie (web) and/or stored token (native). */
export async function logout() {
  try {
    await apiFetch('/auth/logout', { method: 'POST' })
  } finally {
    if (isNative()) await clearStoredToken()
  }
}

// Re-export so callers (AuthContext) can manage native token state directly.
export { isNative, getStoredToken, setStoredToken, clearStoredToken }
