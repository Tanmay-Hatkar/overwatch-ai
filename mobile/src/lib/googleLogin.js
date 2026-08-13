/**
 * googleLogin.js — native Google sign-in via system browser.
 *
 * Google blocks OAuth inside embedded/in-app webviews, so this opens the
 * system browser (WebBrowser.openAuthSessionAsync), runs the same backend
 * flow the web app uses (GET /auth/google/login?native=1), and captures the
 * session token from the deep-link redirect the backend issues:
 *   overwatch://auth?token=<jwt>   (see backend/app/routes/auth.py,
 *   _redirect_to_native — the redirect target is a hardcoded literal there,
 *   not negotiated, so this listens on that exact scheme+host rather than
 *   deriving it via Linking.createURL()).
 *
 * Requires a standalone/dev-client build (the "overwatch" scheme has to be
 * registered natively via app.json's `scheme`) — Expo Go can't receive this
 * redirect, since it owns its own exp:// scheme instead.
 */

import * as WebBrowser from 'expo-web-browser'
import * as Linking from 'expo-linking'
import { setStoredToken } from './auth'

const NATIVE_REDIRECT = 'overwatch://auth'

export async function googleLogin(apiBase) {
  const loginUrl = `${apiBase}/auth/google/login?native=1`
  const result = await WebBrowser.openAuthSessionAsync(loginUrl, NATIVE_REDIRECT)

  if (result.type !== 'success' || !result.url) {
    // User closed the browser or denied consent — not a hard error to surface.
    throw new Error('sign_in_cancelled')
  }

  const parsed = Linking.parse(result.url)
  const token = parsed.queryParams?.token
  const authError = parsed.queryParams?.auth_error

  if (!token) {
    throw new Error(typeof authError === 'string' ? authError : 'sign_in_failed')
  }

  await setStoredToken(token)
  return token
}
