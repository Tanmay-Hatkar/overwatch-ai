import { Pressable, StyleSheet, Text, View } from 'react-native'
import { Ionicons } from '@react-native-vector-icons/ionicons'
import { color, font, radius, spacing } from '../theme'
import { colorForSection } from '../lib/sectionColor'

/**
 * Single commitment row: checkbox, text, and a quiet meta line (time,
 * reminder lead, repeat, section). Tap the row to edit; delete lives in
 * the edit sheet rather than as an always-visible × on every row, so a
 * stray tap can't open a destructive dialog.
 *
 * A commitment whose time has passed reads "from earlier" in warm amber,
 * not "overdue" in alarm red (PRD §5 principle 3: recall, never judgment).
 */
export default function TodoItem({ commitment, onToggle, onPress }) {
  const isDone = commitment.status === 'done'
  const dueInfo = formatDueAt(commitment.due_at, isDone)
  const isEarlier = !!dueInfo?.earlier && !isDone
  const hasRecurrence = !!commitment.recurrence && commitment.recurrence !== 'none'
  const hasLead = commitment.reminder_lead_minutes > 0
  const hasSection = !!commitment.group_name
  const hasMeta = !!dueInfo || hasSection || hasLead || hasRecurrence

  return (
    <Pressable
      onPress={() => onPress(commitment)}
      accessibilityRole="button"
      accessibilityLabel={`Edit ${commitment.text}`}
      style={({ pressed }) => [
        styles.row,
        isDone && styles.rowDone,
        isEarlier && styles.rowEarlier,
        pressed && styles.rowPressed,
      ]}
    >
      <Pressable
        onPress={() => onToggle(commitment)}
        hitSlop={10}
        style={styles.checkbox}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: isDone }}
        accessibilityLabel={isDone ? `Mark ${commitment.text} not done` : `Mark ${commitment.text} done`}
      >
        <View style={[styles.checkboxInner, isDone && styles.checkboxChecked]}>
          {isDone && <Ionicons name="checkmark" size={14} color={color.onAccent} />}
        </View>
      </Pressable>

      <View style={styles.textCol}>
        <Text style={[styles.text, isDone && styles.textDone]} numberOfLines={2}>
          {commitment.text}
        </Text>

        {hasMeta && (
          <View style={styles.metaRow}>
            {!!dueInfo && (
              <Text style={[styles.dueLabel, isEarlier && styles.dueLabelEarlier]}>{dueInfo.label}</Text>
            )}
            {hasLead && (
              <View style={styles.metaItem}>
                <Ionicons name="notifications-outline" size={11} color={color.textMuted} />
                <Text style={styles.metaText}>{formatLead(commitment.reminder_lead_minutes)}</Text>
              </View>
            )}
            {hasRecurrence && (
              <View style={styles.metaItem}>
                <Ionicons name="repeat" size={12} color={color.textMuted} />
                <Text style={styles.metaText}>{commitment.recurrence}</Text>
              </View>
            )}
            {hasSection && (
              <View style={styles.metaItem}>
                <View style={[styles.sectionDot, { backgroundColor: colorForSection(commitment.group_name) }]} />
                <Text style={styles.metaText}>{commitment.group_name}</Text>
              </View>
            )}
          </View>
        )}
      </View>
    </Pressable>
  )
}

function formatLead(minutes) {
  if (minutes >= 60 && minutes % 60 === 0) return `${minutes / 60} hr before`
  return `${minutes} min before`
}

function formatDueAt(dueAt, isDone) {
  if (!dueAt) return null
  const due = new Date(dueAt)
  const now = new Date()
  const earlier = !isDone && due < now
  const sameDay =
    due.getFullYear() === now.getFullYear() &&
    due.getMonth() === now.getMonth() &&
    due.getDate() === now.getDate()

  const time = due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (earlier) return { label: sameDay ? `from earlier · ${time}` : `from ${shortDay(due)}`, earlier }
  if (sameDay) return { label: `today · ${time}`, earlier }
  return { label: `${shortDay(due)} · ${time}`, earlier }
}

function shortDay(date) {
  return date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md + 2,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.lg,
    marginBottom: spacing.sm,
  },
  rowPressed: { backgroundColor: color.surfaceRaised },
  rowDone: { opacity: 0.5 },
  rowEarlier: { borderColor: color.earlierBorder, backgroundColor: color.earlierTint },
  checkbox: { paddingTop: 1 },
  checkboxInner: {
    width: 22,
    height: 22,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: color.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: { backgroundColor: color.accent, borderColor: color.accent },
  textCol: { flex: 1 },
  text: { color: color.textPrimary, fontSize: font.lg, lineHeight: 21 },
  textDone: { textDecorationLine: 'line-through', color: color.textSecondary },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    columnGap: spacing.md,
    rowGap: spacing.xs,
    marginTop: spacing.xs + 2,
  },
  dueLabel: { fontSize: font.sm, color: color.textMuted },
  dueLabelEarlier: { color: color.earlier, fontWeight: '600' },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { fontSize: font.sm, color: color.textMuted },
  sectionDot: { width: 7, height: 7, borderRadius: radius.pill },
})
