/**
 * auth.js — secure bearer-token storage.
 *
 * The backend's native OAuth flow (see backend/app/routes/auth.py) issues a
 * session JWT and deep-links it back to the app rather than setting a
 * cookie, since there's no shared cookie jar between a system-browser OAuth
 * flow and the app. This mirrors frontend/src/lib/native.js's approach for
 * the Capacitor app, using SecureStore instead of Capacitor Preferences.
 */

import * as SecureStore from 'expo-secure-store'

const TOKEN_KEY = 'ow.session.token'

/** Read the stored bearer token. Returns null if never signed in. */
export async function getStoredToken() {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY)
  } catch {
    return null
  }
}

/** Persist the bearer token in secure storage. */
export async function setStoredToken(token) {
  await SecureStore.setItemAsync(TOKEN_KEY, token)
}

/** Remove the stored bearer token (logout). */
export async function clearStoredToken() {
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY)
  } catch {
    // nothing to clear
  }
}
