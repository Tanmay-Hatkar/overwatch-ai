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
