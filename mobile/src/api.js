/**
 * api.js — backend API client.
 *
 * Thin wrappers around fetch() for each endpoint. Ports frontend/src/api.js's
 * conventions (retry-on-network-error for GETs, 401 surfaced specially,
 * 204 -> null) but always uses bearer-token auth — unlike the web app there's
 * no cookie fallback here, since a native app never had a cookie jar shared
 * with the OAuth browser session in the first place.
 */

import Constants from 'expo-constants'
import { getStoredToken, setStoredToken, clearStoredToken } from './lib/auth'
import { googleLogin } from './lib/googleLogin'
import { getDeviceTimezone } from './lib/timezone'

const API_BASE = Constants.expoConfig?.extra?.apiBaseUrl ?? ''

export function apiBase() {
  return API_BASE
}

async function apiFetch(path, options = {}) {
  const token = await getStoredToken()
  const authHeader = token ? { Authorization: `Bearer ${token}` } : {}

  const method = (options.method || 'GET').toUpperCase()
  const maxAttempts = method === 'GET' ? 3 : 1

  let lastErr
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
          ...authHeader,
          ...(options.headers || {}),
        },
      })

      if (!response.ok) {
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
      const isNetworkError = err instanceof TypeError
      if (!isNetworkError || attempt === maxAttempts) throw err
      lastErr = err
      await new Promise((resolve) => setTimeout(resolve, attempt * 400))
    }
  }
  throw lastErr
}

// ---------------------------------------------------------------------------
// Commitments (todos)
// ---------------------------------------------------------------------------

export async function listCommitments(statusFilter = null) {
  const params = statusFilter ? `?status_filter=${statusFilter}` : ''
  return apiFetch(`/commitments${params}`)
}

export async function createCommitment({ text, due_at = null, group_name = '' }) {
  return apiFetch('/commitments', {
    method: 'POST',
    body: JSON.stringify({ text, due_at, group_name }),
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
// Chat (AI capture — the primary way commitments should be created; see
// frontend/src/components/ChatBar.jsx for the reference web implementation
// this mirrors, incl. clarify_kind/clarify_options for tap-only chips)
// ---------------------------------------------------------------------------

export async function sendChatMessage(message, history = [], timezone = getDeviceTimezone()) {
  return apiFetch('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, history, timezone }),
  })
}

export async function getChatHistory(limit = 50) {
  return apiFetch(`/chat/history?limit=${limit}`)
}

export async function clearChatHistory() {
  return apiFetch('/chat/history', { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// Briefings & reflections
// ---------------------------------------------------------------------------

export async function getMorningBriefing({ forceRegenerate = false, timezone = getDeviceTimezone() } = {}) {
  const params = new URLSearchParams()
  if (forceRegenerate) params.set('force_regenerate', 'true')
  if (timezone) params.set('timezone', timezone)
  const qs = params.toString()
  return apiFetch(`/briefings/today${qs ? `?${qs}` : ''}`)
}

export async function getEveningReflection({ forceRegenerate = false, timezone = getDeviceTimezone() } = {}) {
  const params = new URLSearchParams()
  if (forceRegenerate) params.set('force_regenerate', 'true')
  if (timezone) params.set('timezone', timezone)
  const qs = params.toString()
  return apiFetch(`/reflections/today${qs ? `?${qs}` : ''}`)
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/** Fetch the current signed-in user. Returns null (not throw) on 401. */
export async function getCurrentUser() {
  try {
    return await apiFetch('/auth/me')
  } catch (err) {
    if (err.status === 401) return null
    throw err
  }
}

/** Open the system browser, complete Google sign-in, store the token. */
export async function startGoogleLogin() {
  return googleLogin(API_BASE)
}

/** Clear the session — server-side cookie cleanup (harmless no-op for
 * bearer callers) plus the locally stored token. */
export async function logout() {
  try {
    await apiFetch('/auth/logout', { method: 'POST' })
  } finally {
    await clearStoredToken()
  }
}

export { getStoredToken, setStoredToken, clearStoredToken }
