/*
 * sw.js — Service worker for PWA + Web Push notifications.
 *
 * Handlers:
 *   - install / activate    PWA installability + take control quickly
 *   - fetch                 no-op (no caching strategy yet)
 *   - push                  show a notification when the backend pushes
 *   - notificationclick     focus an existing tab or open one
 *
 * The push event runs even when the browser tab is CLOSED. That's the
 * whole point — we want reminders to reach the user wherever they are.
 */

self.addEventListener('install', () => {
  // New service worker becomes active immediately.
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  // Take control of any uncontrolled clients (open tabs) right away.
  event.waitUntil(self.clients.claim())
})

self.addEventListener('fetch', () => {
  // No-op pass-through. Browsers require ANY fetch handler to consider
  // the PWA "installable."
})

self.addEventListener('push', (event) => {
  let payload = { title: 'Overwatch', body: 'You have a reminder.', tag: null }
  if (event.data) {
    try {
      payload = { ...payload, ...event.data.json() }
    } catch {
      payload.body = event.data.text()
    }
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      tag: payload.tag || undefined,
      icon: '/icon-192.svg',
      badge: '/icon-192.svg',
      requireInteraction: true,
      data: { url: '/' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const targetUrl = (event.notification.data && event.notification.data.url) || '/'

  event.waitUntil(
    (async () => {
      const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      const existing = clients.find((c) => c.url.includes(self.location.host))
      if (existing) {
        await existing.focus()
        return
      }
      await self.clients.openWindow(targetUrl)
    })(),
  )
})
