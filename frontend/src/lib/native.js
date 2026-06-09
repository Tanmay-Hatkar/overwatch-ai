/**
 * native.js — Capacitor (native app) helpers.
 *
 * On the web these are mostly no-ops; on the native Android app they handle
 * the token-based auth flow that replaces cookies (Google blocks OAuth inside
 * embedded webviews, so the app opens the system browser and receives the
 * session token back via a deep link).
 *
 * Token storage uses @capacitor/preferences (native key-value store). The
 * stored token is sent as `Authorization: Bearer <token>` on every API call.
 */

import { Capacitor } from '@capacitor/core'
import { App } from '@capacitor/app'
import { Browser } from '@capacitor/browser'
import { Preferences } from '@capacitor/preferences'

const TOKEN_KEY = 'ow.session.token'

/** True when running inside the native (Capacitor) app, false on the web. */
export function isNative() {
  return Capacitor.isNativePlatform()
}

/** Read the stored bearer token (native only). Returns null on web/absent. */
export async function getStoredToken() {
  if (!isNative()) return null
  try {
    const { value } = await Preferences.get({ key: TOKEN_KEY })
    return value || null
  } catch {
    return null
  }
}

/** Persist the bearer token in native secure storage. */
export async function setStoredToken(token) {
  await Preferences.set({ key: TOKEN_KEY, value: token })
}

/** Remove the stored bearer token (native logout). */
export async function clearStoredToken() {
  try {
    await Preferences.remove({ key: TOKEN_KEY })
  } catch {
    // ignore — nothing to clear
  }
}

/**
 * Native Google sign-in.
 *
 * Opens the backend login URL (native mode) in the system browser — NOT the
 * embedded webview, which Google rejects. The backend runs the normal OAuth
 * flow and deep-links back to `overwatch://auth?token=...`. We listen for
 * that deep link, capture the token, store it, and resolve.
 *
 * @param {string} apiBase  The backend base URL (VITE_API_BASE_URL).
 * @returns {Promise<string>} Resolves with the stored token on success.
 */
export function nativeGoogleLogin(apiBase) {
  return new Promise((resolve, reject) => {
    let listener

    const cleanup = async () => {
      if (listener) {
        try {
          await listener.remove()
        } catch {
          // ignore
        }
        listener = null
      }
      try {
        await Browser.close()
      } catch {
        // browser may already be closed
      }
    }

    App.addListener('appUrlOpen', async (event) => {
      // event.url e.g. overwatch://auth?token=XXX  or  ?auth_error=YYY
      if (!event?.url || !event.url.startsWith('overwatch://')) return
      try {
        const parsed = new URL(event.url)
        const token = parsed.searchParams.get('token')
        const err = parsed.searchParams.get('auth_error')
        await cleanup()
        if (token) {
          await setStoredToken(token)
          resolve(token)
        } else {
          reject(new Error(err || 'sign_in_failed'))
        }
      } catch (e) {
        await cleanup()
        reject(e)
      }
    }).then((h) => {
      listener = h
    })

    Browser.open({ url: `${apiBase}/auth/google/login?native=1` }).catch(async (e) => {
      await cleanup()
      reject(e)
    })
  })
}
