import { useAuth } from '../contexts/AuthContext'

/**
 * Full-page sign-in screen. Shown when /auth/me returns 401.
 *
 * Visual: matches the app's dark + orange aesthetic. Single CTA: "Sign in
 * with Google." If an auth_error= came back in the URL, we show the
 * friendly message above the button.
 */
export default function LoginScreen() {
  const { login, error } = useAuth()

  return (
    <div className="min-h-screen bg-[#0f0f0f] text-[#f5f5f5] flex items-center justify-center px-6">
      <div className="max-w-sm w-full text-center">
        <h1 className="text-4xl font-bold text-orange-500 mb-2 tracking-tight">
          Overwatch
        </h1>
        <p className="text-zinc-500 text-sm mb-12">Things you said you'd do.</p>

        {error && (
          <p className="mb-6 text-sm text-red-400 bg-red-900/20 border border-red-900/40 rounded-lg p-3">
            {error}
          </p>
        )}

        <button
          onClick={login}
          className="w-full flex items-center justify-center gap-3 px-5 py-3 bg-white hover:bg-zinc-100 text-zinc-900 font-medium rounded-lg transition-colors"
        >
          <GoogleIcon />
          Sign in with Google
        </button>

        <p className="text-[11px] text-zinc-600 mt-8 leading-relaxed">
          We use your Google account only to identify you. Your data stays in
          your Overwatch — no one else can see it.
        </p>
      </div>
    </div>
  )
}

/** Google "G" logo inline so we don't pull in an icon dependency. */
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z"
      />
      <path
        fill="#34A853"
        d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z"
      />
      <path
        fill="#FBBC05"
        d="M11.69 28.18c-.44-1.32-.69-2.73-.69-4.18s.25-2.86.69-4.18v-5.7H4.34A21.99 21.99 0 0 0 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z"
      />
      <path
        fill="#EA4335"
        d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7C13.42 14.62 18.27 10.75 24 10.75z"
      />
    </svg>
  )
}
