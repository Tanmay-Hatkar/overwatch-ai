/**
 * api.js — Backend API client.
 *
 * Thin wrappers around fetch() for each endpoint. Returns parsed JSON
 * (or null for 204 No Content). Throws on non-2xx responses so callers
 * can catch + display errors.
 *
 * Uses relative paths (/commitments). Vite's dev server proxies them
 * to http://localhost:8000 (configured in vite.config.js).
 */

async function jsonOrThrow(response) {
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }
  if (response.status === 204) return null
  return await response.json()
}

export async function listCommitments(statusFilter = null) {
  const params = statusFilter ? `?status_filter=${statusFilter}` : ''
  const response = await fetch(`/commitments${params}`)
  return jsonOrThrow(response)
}

export async function createCommitment(text, dueAt = null) {
  const response = await fetch('/commitments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, due_at: dueAt }),
  })
  return jsonOrThrow(response)
}

export async function parseCommitment(message) {
  const response = await fetch('/commitments/parse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  return jsonOrThrow(response)
}

export async function updateCommitment(id, changes) {
  const response = await fetch(`/commitments/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  })
  return jsonOrThrow(response)
}

export async function deleteCommitment(id) {
  const response = await fetch(`/commitments/${id}`, { method: 'DELETE' })
  return jsonOrThrow(response)
}

// ---------------------------------------------------------------------------
// Briefings
// ---------------------------------------------------------------------------

export async function getTodayBriefing(force = false) {
  const url = force ? '/briefings/today?force_regenerate=true' : '/briefings/today'
  const response = await fetch(url)
  return jsonOrThrow(response)
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

export async function getTodayStats() {
  const response = await fetch('/stats/today')
  return jsonOrThrow(response)
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

export async function getTodayEvents() {
  const response = await fetch('/calendar/today')
  return jsonOrThrow(response)
}

export async function getWeekEvents() {
  const response = await fetch('/calendar/week')
  return jsonOrThrow(response)
}

// ---------------------------------------------------------------------------
// Web Push subscriptions
// ---------------------------------------------------------------------------

export async function getVapidPublicKey() {
  const response = await fetch('/push/vapid-public-key')
  return jsonOrThrow(response)
}

export async function subscribeToPush(subscription) {
  const response = await fetch('/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(subscription),
  })
  return jsonOrThrow(response)
}

export async function unsubscribeFromPush(endpoint) {
  const response = await fetch('/push/unsubscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endpoint }),
  })
  return jsonOrThrow(response)
}

export async function sendTestPush() {
  const response = await fetch('/push/test', { method: 'POST' })
  return jsonOrThrow(response)
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export async function sendChat(message, history = []) {
  const response = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })
  return jsonOrThrow(response)
}
