import { Pressable, StyleSheet, Text, View } from 'react-native'
import { color, font, radius, spacing } from '../theme'
import { colorForSection } from '../lib/sectionColor'

/**
 * Single commitment row. Ports the visual language of
 * frontend/src/components/CommitmentList.jsx's CommitmentItem (checkbox,
 * overdue red accent, lead-time badge, recurrence badge) but tap-to-edit
 * opens the edit modal instead of an inline contentEditable-style field —
 * RN has no DOM equivalent, and a modal is the more standard native pattern.
 */
export default function TodoItem({ commitment, onToggle, onPress, onDelete }) {
  const isDone = commitment.status === 'done'
  const dueInfo = formatDueAt(commitment.due_at, isDone)
  const hasRecurrence = commitment.recurrence && commitment.recurrence !== 'none'
  const hasLead = commitment.reminder_lead_minutes > 0
  const hasMeta = dueInfo || commitment.group_name || hasLead

  return (
    <Pressable
      onPress={() => onPress(commitment)}
      style={({ pressed }) => [
        styles.row,
        isDone && styles.rowDone,
        dueInfo?.overdue && !isDone && styles.rowOverdue,
        pressed && styles.rowPressed,
      ]}
    >
      <Pressable onPress={() => onToggle(commitment)} hitSlop={8} style={styles.checkbox}>
        <View style={[styles.checkboxInner, isDone && styles.checkboxChecked]}>
          {isDone && <Text style={styles.checkMark}>✓</Text>}
        </View>
      </Pressable>

      <View style={styles.textCol}>
        <View style={styles.titleRow}>
          <Text style={[styles.text, isDone && styles.textDone]} numberOfLines={2}>
            {commitment.text}
          </Text>
          {hasRecurrence && (
            <View style={styles.recurrenceBadge}>
              <Text style={styles.recurrenceBadgeText}>↻ {commitment.recurrence}</Text>
            </View>
          )}
        </View>

        {hasMeta && (
          <View style={styles.metaRow}>
            {dueInfo && (
              <Text style={[styles.dueLabel, dueInfo.overdue && !isDone && styles.dueLabelOverdue]}>
                {dueInfo.label}
              </Text>
            )}
            {hasLead && (
              <View style={styles.metaPill}>
                <Text style={styles.metaPillText}>🔔 {formatLead(commitment.reminder_lead_minutes)}</Text>
              </View>
            )}
            {commitment.group_name && (
              <View style={styles.metaPill}>
                <View style={[styles.metaPillDot, { backgroundColor: colorForSection(commitment.group_name) }]} />
                <Text style={styles.metaPillText}>{commitment.group_name}</Text>
              </View>
            )}
          </View>
        )}
      </View>

      <Pressable
        onPress={() => onDelete(commitment)}
        hitSlop={8}
        style={({ pressed }) => [styles.deleteBtn, pressed && styles.deleteBtnPressed]}
        accessibilityLabel={`Delete ${commitment.text}`}
      >
        <Text style={styles.deleteText}>×</Text>
      </Pressable>
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
  const overdue = !isDone && due < now
  const sameDay =
    due.getFullYear() === now.getFullYear() &&
    due.getMonth() === now.getMonth() &&
    due.getDate() === now.getDate()

  const time = due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  let label
  if (overdue) label = `overdue · ${time}`
  else if (sameDay) label = `due today · ${time}`
  else {
    const day = due.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
    label = `due ${day} · ${time}`
  }
  return { label, overdue }
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
  rowOverdue: { borderColor: color.overdueBorder, backgroundColor: color.overdueTint },
  checkbox: { padding: 2, marginTop: 1 },
  checkboxInner: {
    width: 21,
    height: 21,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: color.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: { backgroundColor: color.accent, borderColor: color.accent },
  checkMark: { color: color.onAccent, fontSize: 13, fontWeight: '700' },
  textCol: { flex: 1 },
  titleRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: spacing.xs + 2 },
  text: { color: color.textPrimary, fontSize: font.md + 1, flexShrink: 1 },
  textDone: { textDecorationLine: 'line-through', color: color.textSecondary },
  recurrenceBadge: {
    backgroundColor: color.accentMuted,
    paddingHorizontal: spacing.xs + 2,
    paddingVertical: 1,
    borderRadius: radius.sm,
  },
  recurrenceBadgeText: { fontSize: font.xs - 1, color: '#fdba74', fontWeight: '700' },
  metaRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: spacing.xs + 2, marginTop: spacing.xs + 2 },
  dueLabel: { fontSize: font.xs, color: color.textMuted },
  dueLabelOverdue: { color: color.danger, fontWeight: '600' },
  metaPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: color.surfaceRaised,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.xs + 2,
    paddingVertical: 1,
  },
  metaPillDot: { width: 6, height: 6, borderRadius: radius.pill, marginRight: 4 },
  metaPillText: { fontSize: font.xs - 1, color: color.textMuted },
  deleteBtn: {
    width: 26,
    height: 26,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deleteBtnPressed: { backgroundColor: color.surfaceRaised },
  deleteText: { color: color.textMuted, fontSize: 20, lineHeight: 22 },
})
