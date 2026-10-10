import { Pressable, StyleSheet, Text, View } from 'react-native'
import { Ionicons } from '@react-native-vector-icons/ionicons'
import { relativeTime } from '../lib/focus'
import { color, font, radius, spacing } from '../theme'

/**
 * The home screen's focus card — "what should I start right now?"
 *
 * `kind: 'upcoming'` shows the soonest commitment with a countdown and the
 * reminder line the parser wrote for it (ADR-0021). `kind: 'earlier'` is
 * the gentle restart path: something slipped, so the card asks "still on?"
 * and offers to move it — never a red "overdue" (PRD §5 principle 3).
 *
 * Props:
 *   focus     — result of pickUpNext(): { commitment, kind }
 *   now       — Date used for the relative time (injected for tests)
 *   onDone    — mark the commitment done
 *   onMove    — open the edit sheet to change its time
 *   onTalk    — open chat to talk it through
 */
export default function UpNextCard({ focus, now = new Date(), onDone, onMove, onTalk }) {
  const { commitment, kind } = focus
  const due = new Date(commitment.due_at)
  const time = due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const isEarlier = kind === 'earlier'

  return (
    <View style={[styles.card, isEarlier && styles.cardEarlier]}>
      <View style={styles.eyebrowRow}>
        <Ionicons
          name={isEarlier ? 'time-outline' : 'flash-outline'}
          size={13}
          color={isEarlier ? color.earlier : color.accent}
        />
        <Text style={[styles.eyebrow, isEarlier && styles.eyebrowEarlier]}>
          {isEarlier ? 'STILL ON?' : 'UP NEXT'}
        </Text>
        <Text style={styles.when}>
          {time} · {relativeTime(due, now)}
        </Text>
      </View>

      <Text style={styles.title} numberOfLines={3}>
        {commitment.text}
      </Text>
      {!!commitment.reminder_phrase && !isEarlier && (
        <Text style={styles.phrase} numberOfLines={2}>
          {commitment.reminder_phrase}
        </Text>
      )}
      {isEarlier && (
        <Text style={styles.phrase}>This slipped by. Still the plan, or has the day changed?</Text>
      )}

      <View style={styles.actions}>
        <Pressable
          style={({ pressed }) => [styles.primary, pressed && styles.pressed]}
          onPress={() => onDone(commitment)}
          accessibilityRole="button"
          accessibilityLabel={`Mark ${commitment.text} done`}
        >
          <Ionicons name="checkmark" size={16} color={color.onAccent} />
          <Text style={styles.primaryText}>Done</Text>
        </Pressable>
        <Pressable
          style={({ pressed }) => [styles.secondary, pressed && styles.pressed]}
          onPress={() => onMove(commitment)}
          accessibilityRole="button"
          accessibilityLabel={`Move ${commitment.text}`}
        >
          <Text style={styles.secondaryText}>Move it</Text>
        </Pressable>
        <Pressable
          style={({ pressed }) => [styles.ghost, pressed && styles.pressed]}
          onPress={onTalk}
          accessibilityRole="button"
          accessibilityLabel="Talk it through in chat"
          hitSlop={6}
        >
          <Ionicons name="chatbubble-ellipses-outline" size={18} color={color.textSecondary} />
        </Pressable>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  card: {
    marginTop: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: color.focusTint,
    borderWidth: 1,
    borderColor: color.focusBorder,
  },
  cardEarlier: { backgroundColor: color.earlierTint, borderColor: color.earlierBorder },
  eyebrowRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  eyebrow: { color: color.accent, fontSize: font.xs, fontWeight: '800', letterSpacing: 1.2 },
  eyebrowEarlier: { color: color.earlier },
  when: { color: color.textSecondary, fontSize: font.sm, marginLeft: 'auto' },
  title: {
    color: color.textPrimary,
    fontSize: font.xxl - 2,
    fontWeight: '700',
    lineHeight: 26,
    marginTop: spacing.md,
    letterSpacing: -0.2,
  },
  phrase: { color: color.textSecondary, fontSize: font.md, lineHeight: 20, marginTop: spacing.xs + 2 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.lg },
  primary: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: color.accent,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
  },
  primaryText: { color: color.onAccent, fontWeight: '700', fontSize: font.md },
  secondary: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: color.borderStrong,
  },
  secondaryText: { color: color.textPrimary, fontWeight: '600', fontSize: font.md },
  ghost: {
    marginLeft: 'auto',
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.surfaceRaised,
  },
  pressed: { opacity: 0.75 },
})
