import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { getCurrentUser, logout as apiLogout, startGoogleLogin } from '../api'

/**
 * AuthContext — single source of truth for "who is signed in?"
 *
 * Shape:
 *   user     UserResponse | null   The signed-in user, or null if not signed in
 *   loading  boolean                True while the initial /auth/me check is in flight
 *   error    string | null         Last auth-related error (e.g. callback failures)
 *   login    () => void             Kick off the Google OAuth flow
 *   logout   () => Promise<void>    Clear the session and revert to LoginScreen
 *   refresh  () => Promise<void>    Force-re-check (useful after callback redirect)
 *
 * Mounted once at the App root. The initial effect calls /auth/me to
 * detect whether the user already has a valid cookie. After the callback
 * redirects back to /, this same check picks up the new session.
 */

const AuthContext = createContext(null)

/** Read `?auth_error=...` from the URL once on mount. */
function readUrlAuthError() {
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.search)
  const err = params.get('auth_error')
  if (err) {
    // Clean up the URL so refreshing doesn't keep showing the error
    params.delete('auth_error')
    const next = params.toString()
    const url =
      window.location.pathname + (next ? `?${next}` : '') + window.location.hash
    window.history.replaceState({}, '', url)
  }
  return err
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const u = await getCurrentUser()
      setUser(u)
    } catch (err) {
      // Network error or 5xx — surface but don't crash the app
      setError(err.message)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const urlError = readUrlAuthError()
    if (urlError) setError(mapAuthError(urlError))
    refresh()
  }, [refresh])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } catch {
      // ignore — even if the backend call fails we still want to clear local state
    }
    setUser(null)
  }, [])

  const value = { user, loading, error, login: startGoogleLogin, logout, refresh }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** Hook for any component that needs auth state. */
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth must be used inside <AuthProvider>')
  }
  return ctx
}

/** Translate the backend's auth_error codes into friendly messages. */
function mapAuthError(code) {
  switch (code) {
    case 'google_denied':
      return "You declined the Google sign-in. Try again when you're ready."
    case 'state_mismatch':
      return 'Sign-in took too long and the security token expired. Try again.'
    case 'missing_code_or_state':
      return "Sign-in didn't complete. Try again."
    case 'oauth_exchange_failed':
      return "We couldn't verify your Google account. Try again in a moment."
    default:
      return 'Sign-in failed. Try again.'
  }
}
