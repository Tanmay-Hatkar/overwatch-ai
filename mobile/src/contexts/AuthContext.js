import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { getCurrentUser, logout as apiLogout, startGoogleLogin } from '../api'

/**
 * AuthContext — single source of truth for "who is signed in?"
 *
 * Ports frontend/src/contexts/AuthContext.jsx's shape 1:1 (user, loading,
 * error, login, logout, refresh) so the mental model carries over even
 * though the underlying storage/transport differs (SecureStore + bearer
 * token instead of a cookie).
 */

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const u = await getCurrentUser()
      setUser(u)
    } catch {
      // Background "am I signed in?" check failed (e.g. flaky network) —
      // not an actionable error, just show the login screen.
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } catch {
      // ignore — still clear local state even if the backend call fails
    }
    setUser(null)
  }, [])

  const login = useCallback(async () => {
    setError(null)
    try {
      await startGoogleLogin()
      await refresh()
    } catch (err) {
      if (err.message !== 'sign_in_cancelled') {
        setError(mapAuthError(err.message))
      }
    }
  }, [refresh])

  const value = { user, loading, error, login, logout, refresh }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

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
