/**
 * push.js — Web Push subscription helpers.
 *
 * Encapsulates the messy interop between the Service Worker API, the
 * PushManager API, and our backend's subscription endpoints.
 */

import {
  getVapidPublicKey,
  subscribeToPush,
  unsubscribeFromPush,
} from '../api'

/** Convert a base64url string (VAPID public key shape) to Uint8Array. */
function urlBase64ToUint8Array(b64) {
  const padding = '='.repeat((4 - (b64.length % 4)) % 4)
  const base64 = (b64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const arr = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i)
  return arr
}

/** True if the runtime supports everything we need for Web Push. */
export function isPushSupported() {
  return (
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  )
}

/**
 * Returns the current PushSubscription if any, otherwise null. Does NOT
 * trigger a new subscription.
 */
export async function getCurrentSubscription() {
  if (!isPushSupported()) return null
  const reg = await navigator.serviceWorker.ready
  return await reg.pushManager.getSubscription()
}

/**
 * Ask the browser for notification permission, fetch the VAPID public key
 * from the backend, create a push subscription, and POST it to the backend.
 *
 * Returns the active PushSubscription.
 * Throws if the user denies permission or any step fails.
 */
export async function enablePush() {
  if (!isPushSupported()) {
    throw new Error("Your browser doesn't support Web Push.")
  }

  // Request notification permission first (idempotent if already granted)
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Notification permission was not granted.')
  }

  const reg = await navigator.serviceWorker.ready

  // Reuse existing subscription if present — saves a server round-trip
  let subscription = await reg.pushManager.getSubscription()
  if (subscription === null) {
    const { public_key: vapidPublicKey } = await getVapidPublicKey()
    subscription = await reg.pushManager.subscribe({
      userVisibleOnly: true, // required by Chrome; no silent pushes
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
    })
  }

  // Always re-POST to backend — the upsert handles dedupe + key refresh
  const payload = subscription.toJSON()
  await subscribeToPush({
    endpoint: payload.endpoint,
    keys: payload.keys,
  })

  return subscription
}

/**
 * Unsubscribe locally AND tell the backend to remove the stored subscription.
 */
export async function disablePush() {
  if (!isPushSupported()) return
  const reg = await navigator.serviceWorker.ready
  const subscription = await reg.pushManager.getSubscription()
  if (subscription === null) return

  const endpoint = subscription.endpoint
  await subscription.unsubscribe()
  try {
    await unsubscribeFromPush(endpoint)
  } catch {
    // Backend unsubscribe is best-effort; local unsubscribe already worked.
  }
}
