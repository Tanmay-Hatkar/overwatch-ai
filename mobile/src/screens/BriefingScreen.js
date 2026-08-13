import { useCallback, useState } from 'react'
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useFocusEffect } from '@react-navigation/native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { getMorningBriefing } from '../api'
import { color, font, radius, spacing } from '../theme'

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
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={12} style={styles.backButton}>
          <Text style={styles.backGlyph}>‹</Text>
        </Pressable>
        <Text style={styles.headerTitle}>Morning brief</Text>
        <View style={styles.backButton} />
      </View>

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
            <>
              <Text style={styles.body}>{briefing?.content}</Text>
              <View style={styles.statsRow}>
                {briefing?.overdue_count > 0 && (
                  <Text style={styles.stat}>{briefing.overdue_count} overdue</Text>
                )}
                {briefing?.today_count > 0 && (
                  <Text style={styles.stat}>{briefing.today_count} today</Text>
                )}
                {briefing?.floating_count > 0 && (
                  <Text style={styles.stat}>{briefing.floating_count} floating</Text>
                )}
              </View>
            </>
          )}
        </ScrollView>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: color.background },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.border,
  },
  backButton: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  backGlyph: { color: color.textPrimary, fontSize: 28, fontWeight: '400', marginTop: -2 },
  headerTitle: { color: color.textPrimary, fontSize: font.xl, fontWeight: '700' },
  content: { padding: spacing.xl },
  body: { color: color.textPrimary, fontSize: font.lg, lineHeight: 24 },
  error: { color: color.danger, fontSize: font.md },
  statsRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xl, flexWrap: 'wrap' },
  stat: {
    color: color.textSecondary,
    fontSize: font.xs,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
})
