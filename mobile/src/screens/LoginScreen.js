import { useState } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'
import { useAuth } from '../contexts/AuthContext'
import { color, font, radius, spacing } from '../theme'

export default function LoginScreen() {
  const { login, error, loading } = useAuth()
  const [signingIn, setSigningIn] = useState(false)

  async function handleLogin() {
    setSigningIn(true)
    try {
      await login()
    } finally {
      setSigningIn(false)
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.wordmark}>Overwatch</Text>
      <Text style={styles.tagline}>Say what you'll do. Get pulled back to it.</Text>

      <Pressable style={styles.button} onPress={handleLogin} disabled={signingIn || loading}>
        {signingIn ? (
          <ActivityIndicator color={color.onAccent} />
        ) : (
          <Text style={styles.buttonText}>Sign in with Google</Text>
        )}
      </Pressable>

      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: color.background,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  wordmark: { color: color.textPrimary, fontSize: 28, fontWeight: '700', marginBottom: spacing.sm },
  tagline: { color: color.textSecondary, fontSize: font.md, marginBottom: 40, textAlign: 'center' },
  button: {
    backgroundColor: color.accent,
    paddingVertical: spacing.md + 2,
    paddingHorizontal: spacing.xxl,
    borderRadius: radius.md,
    minWidth: 220,
    alignItems: 'center',
  },
  buttonText: { color: color.onAccent, fontSize: font.lg, fontWeight: '700' },
  error: { color: color.danger, fontSize: font.sm + 1, marginTop: spacing.xl, textAlign: 'center' },
})
