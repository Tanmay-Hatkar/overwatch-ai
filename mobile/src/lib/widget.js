/**
 * widget.js — Home-screen widget (ADR-0020).
 *
 * The widget itself (Glance UI + WorkManager periodic refresh) lives
 * entirely in the native module at modules/widget and runs independently
 * of JS once configured. This file is the thin JS-side handoff: whenever
 * auth.js stores or clears the session token, mirror it (plus the API base
 * URL) into the widget's own native config store so its background worker
 * can call the backend without JS being alive.
 *
 * Android-only. No-op everywhere else -- home-screen widgets have no web
 * equivalent, and the module's web stub also just no-ops.
 */
import { Platform } from 'react-native'
import Constants from 'expo-constants'
import Widget from '../../modules/widget'

const API_BASE = Constants.expoConfig?.extra?.apiBaseUrl ?? ''

function isSupported() {
  return Platform.OS === 'android'
}

/** Push the signed-in token (+ API base URL) to the widget. Best-effort. */
export async function configureWidget(token) {
  if (!isSupported() || !token) return
  try {
    await Widget.configure(API_BASE, token)
  } catch {
    // best-effort -- a widget config miss shouldn't break sign-in
  }
}

/** Clear the widget's config on sign-out so it falls back to the auth-error frame. */
export async function clearWidget() {
  if (!isSupported()) return
  try {
    await Widget.clear()
  } catch {
    // best-effort
  }
}
