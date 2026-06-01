/*
 * sw.js — Minimal service worker for PWA installability.
 *
 * What this DOES:
 *   - Makes the site installable on Android, Desktop Chrome/Edge.
 *   - Allows "Add to Home Screen" on iOS (partial support).
 *   - Survives across page loads.
 *
 * What this DOES NOT do (yet):
 *   - Offline caching. (Future slice: cache-first strategy for static assets.)
 *   - Background sync. (Needs server-side support.)
 *   - Push notifications when the tab is closed. (Requires VAPID + backend.)
 *
 * Keep this file at the root scope (/sw.js) so it controls the whole app.
 */

self.addEventListener('install', () => {
  // skipWaiting → new service worker becomes active immediately on next load,
  // rather than waiting for all tabs to close. Fine for our use case since
  // we don't ship breaking SW changes.
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  // claim() → take control of any uncontrolled clients (open tabs) right away.
  event.waitUntil(self.clients.claim())
})

self.addEventListener('fetch', () => {
  // No-op fetch handler. Browsers require ANY fetch handler to consider the
  // PWA "installable," so we register one even though it just lets requests
  // pass through to the network unchanged.
})
