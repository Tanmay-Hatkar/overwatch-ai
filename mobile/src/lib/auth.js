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
import { configureWidget, clearWidget } from './widget'

const TOKEN_KEY = 'ow.session.token'

/** Read the stored bearer token. Returns null if never signed in. */
export async function getStoredToken() {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY)
  } catch {
    return null
  }
}

/**
 * Persist the bearer token in secure storage. Also mirrors it into the
 * home-screen widget's own native config store (ADR-0020). Awaited (not
 * fire-and-forget) so the mirror is done before this function returns --
 * configureWidget()/Widget.configure() still catch their own errors
 * internally, so a widget-config failure here can't reject this call or
 * block sign-in.
 */
export async function setStoredToken(token) {
  await SecureStore.setItemAsync(TOKEN_KEY, token)
  await configureWidget(token)
}

/**
 * Remove the stored bearer token (logout). Also clears the widget's config
 * -- awaited so logout can't return with the widget still holding a stale
 * token (a fire-and-forget call here previously left a real window where
 * the widget kept fetching/displaying the logged-out user's commitments).
 */
export async function clearStoredToken() {
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY)
  } catch {
    // nothing to clear
  }
  await clearWidget()
}
