import { useCallback, useState } from 'react'
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useFocusEffect } from '@react-navigation/native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { getEveningReflection } from '../api'
import ScreenHeader from '../components/ScreenHeader'
import DailyNote, { statsFor } from '../components/DailyNote'
import { color, font, spacing } from '../theme'

/**
 * ReflectionScreen — the evening reflection, generated + cached
 * server-side per calendar day. Same shape as BriefingScreen; content
 * authoring lives in backend/app/services/reflection_service.py's prompt.
 */
export default function ReflectionScreen({ navigation }) {
  const insets = useSafeAreaInsets()
  const [reflection, setReflection] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async (forceRegenerate = false) => {
    try {
      const data = await getEveningReflection({ forceRegenerate })
      setReflection(data)
      setError(null)
    } catch (err) {
      setError(err.message || 'Could not load your reflection.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useFocusEffect(
    useCallback(() => {
      load()
    }, [load]),
  )

  async function handleRefresh() {
    setRefreshing(true)
    await load(true)
  }

  return (
    <View style={styles.container}>
      <ScreenHeader title="Evening reflection" icon="moon-outline" onBack={() => navigation.goBack()} />

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={color.accent} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={[styles.content, { paddingBottom: spacing.xxl + insets.bottom }]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={color.accent} />}
        >
          {error ? (
            <Text style={styles.error}>{error}</Text>
          ) : (
            <DailyNote
              content={reflection?.content}
              stats={statsFor(reflection, [['done_count', 'done'], ['open_count', 'still open'], ['abandoned_count', 'let go']])}
              actionLabel="Renegotiate in chat"
              onAction={() => navigation.navigate('Chat')}
            />
          )}
        </ScrollView>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: color.background },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.xl },
  error: { color: color.danger, fontSize: font.md },
})
