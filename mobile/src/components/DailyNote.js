import { Pressable, StyleSheet, Text, View } from 'react-native'
import { Ionicons } from '@react-native-vector-icons/ionicons'
import { color, font, radius, spacing } from '../theme'

/**
 * The body shared by the morning brief and evening reflection: a date
 * line, the LLM-written prose (already plain, spoken-register text), a
 * row of quiet count pills, and one next step that hands off to chat —
 * the brief is a planning prompt, the reflection a renegotiation prompt,
 * and chat is where either actually happens.
 *
 * Props:
 *   content     — prose to show
 *   stats       — array of strings, e.g. ['2 today', '1 from earlier']
 *   actionLabel — call-to-action text
 *   onAction    — called when the call-to-action is tapped
 */
export default function DailyNote({ content, stats, actionLabel, onAction }) {
  const today = new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
  return (
    <View>
      <Text style={styles.date}>{today}</Text>
      <Text style={styles.body}>{content}</Text>

      {stats.length > 0 && (
        <View style={styles.statsRow}>
          {stats.map((s) => (
            <Text key={s} style={styles.stat}>
              {s}
            </Text>
          ))}
        </View>
      )}

      <Pressable
        style={({ pressed }) => [styles.action, pressed && styles.pressed]}
        onPress={onAction}
        accessibilityRole="button"
      >
        <Ionicons name="chatbubble-ellipses" size={18} color={color.onAccent} />
        <Text style={styles.actionText}>{actionLabel}</Text>
      </Pressable>
    </View>
  )
}

/**
 * Build the count pills from a briefing/reflection payload, skipping zeros.
 *
 * @param {object | null} data - the API payload
 * @param {Array<[string, string]>} pairs - [field, label] in display order
 * @returns {string[]} e.g. ['2 today', '1 from earlier']
 */
export function statsFor(data, pairs) {
  return pairs.filter(([key]) => data?.[key] > 0).map(([key, label]) => `${data[key]} ${label}`)
}

const styles = StyleSheet.create({
  date: {
    color: color.textMuted,
    fontSize: font.xs,
    fontWeight: '700',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    marginBottom: spacing.md,
  },
  body: { color: color.textPrimary, fontSize: font.xl, lineHeight: 27 },
  statsRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xl, flexWrap: 'wrap' },
  stat: {
    color: color.textSecondary,
    fontSize: font.sm,
    fontWeight: '600',
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 1,
    overflow: 'hidden',
  },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    marginTop: spacing.xxl,
    paddingVertical: spacing.md + 2,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
  },
  actionText: { color: color.onAccent, fontSize: font.lg, fontWeight: '700' },
  pressed: { opacity: 0.8 },
})
