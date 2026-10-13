import { useCallback, useState } from 'react'
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useFocusEffect } from '@react-navigation/native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { getMorningBriefing } from '../api'
import ScreenHeader from '../components/ScreenHeader'
import DailyNote, { statsFor } from '../components/DailyNote'
import { color, font, spacing } from '../theme'

/**
 * BriefingScreen — the morning brief, generated + cached server-side per
 * calendar day. Purely a display screen; all content authoring already
 * lives in backend/app/services/briefing_service.py's prompt (plain prose,
 * no markdown/bullets, already written in a spoken register).
 */
export default function BriefingScreen({ navigation }) {
  const insets = useSafeAreaInsets()
  const [briefing, setBriefing] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async (forceRegenerate = false) => {
    try {
      const data = await getMorningBriefing({ forceRegenerate })
      setBriefing(data)
      setError(null)
    } catch (err) {
      setError(err.message || 'Could not load your briefing.')
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
      <ScreenHeader title="Morning brief" icon="partly-sunny-outline" onBack={() => navigation.goBack()} />

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
              content={briefing?.content}
              stats={statsFor(briefing, [['today_count', 'today'], ['overdue_count', 'from earlier'], ['floating_count', 'anytime']])}
              actionLabel="Plan the day in chat"
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
