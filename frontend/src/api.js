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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

/**
 * Wrapped fetch with credentials and a stable base URL prefix.
 * All callers should go through this rather than raw fetch() so that
 * cookie behavior + base URL stay consistent.
 */
async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
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
  const path = force ? '/briefings/today?force_regenerate=true' : '/briefings/today'
  return apiFetch(path)
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

export async function getTodayStats() {
  return apiFetch('/stats/today')
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

export async function getTodayEvents() {
  return apiFetch('/calendar/today')
}

export async function getWeekEvents() {
  return apiFetch('/calendar/week')
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
    body: JSON.stringify({ message, history }),
  })
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

/** Navigate the whole window to Google's OAuth consent screen. */
export function startGoogleLogin() {
  window.location.href = `${API_BASE}/auth/google/login`
}

/** Clear the session cookie on the server. */
export async function logout() {
  return apiFetch('/auth/logout', { method: 'POST' })
}
