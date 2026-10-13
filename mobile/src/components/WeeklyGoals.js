import { Pressable, StyleSheet, Text, View } from 'react-native'
import { Ionicons } from '@react-native-vector-icons/ionicons'
import { goalCheckInPrompt, goalFraction, goalStatusLine, weekLabel } from '../lib/goals'
import { color, font, radius, spacing } from '../theme'

/**
 * "This week" — weekly rate goals on the home screen (ADR-0026).
 *
 * Each goal is a count toward a weekly target with a one-tap +1, because
 * logging has to be cheaper than forgetting to. Late in the week, a goal
 * that isn't met shows the once-per-week check-in inline: keep going,
 * adjust the target, or call the week good (PRD §4.5). No streaks, no red.
 *
 * Props:
 *   goals     — GoalResponse[] from the API
 *   onLog     — (goal) => void, +1
 *   onOpen    — (goal) => void, open the edit sheet
 *   onDecide  — (goal, 'keep_going' | 'call_it_good') => void
 *   onAdd     — () => void, open the create sheet
 */
export default function WeeklyGoals({ goals, onLog, onOpen, onDecide, onAdd }) {
  if (!goals.length) {
    return (
      <Pressable
        style={({ pressed }) => [styles.emptyRow, pressed && styles.pressed]}
        onPress={onAdd}
        accessibilityRole="button"
        accessibilityLabel="Add a weekly goal"
      >
        <Ionicons name="repeat" size={16} color={color.textMuted} />
        <Text style={styles.emptyText}>Add a weekly goal, like 10 applications or gym 4×</Text>
      </Pressable>
    )
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.headerRow}>
        <Text style={styles.header}>This week</Text>
        <Text style={styles.week}>{weekLabel(goals)}</Text>
        <Pressable
          style={({ pressed }) => [styles.addIcon, pressed && styles.pressed]}
          onPress={onAdd}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel="Add a weekly goal"
        >
          <Ionicons name="add" size={18} color={color.textSecondary} />
        </Pressable>
      </View>
      {goals.map((goal) => (
        <GoalCard key={goal.id} goal={goal} onLog={onLog} onOpen={onOpen} onDecide={onDecide} />
      ))}
    </View>
  )
}

function GoalCard({ goal, onLog, onOpen, onDecide }) {
  const met = goal.state === 'met'
  const settled = goal.state === 'settled'
  const checkIn = goalCheckInPrompt(goal)

  return (
    <Pressable
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
      onPress={() => onOpen(goal)}
      accessibilityRole="button"
      accessibilityLabel={`${goal.text}, ${goal.done_this_week} of ${goal.target_count} this week. Edit`}
    >
      <View style={styles.topRow}>
        <View style={styles.titleCol}>
          <Text style={styles.title} numberOfLines={1}>
            {goal.text}
          </Text>
          <Text style={[styles.status, met && styles.statusMet]} numberOfLines={2}>
            {goalStatusLine(goal)}
          </Text>
        </View>
        <Text style={styles.count}>
          {goal.done_this_week}
          <Text style={styles.countTarget}>/{goal.target_count}</Text>
        </Text>
        <Pressable
          style={({ pressed }) => [styles.plus, (met || settled) && styles.plusQuiet, pressed && styles.pressed]}
          onPress={() => onLog(goal)}
          hitSlop={6}
          accessibilityRole="button"
          accessibilityLabel={`Log one for ${goal.text}`}
        >
          {met ? (
            <Ionicons name="checkmark" size={18} color={color.accent} />
          ) : (
            <Text style={[styles.plusText, settled && styles.plusTextQuiet]}>+1</Text>
          )}
        </Pressable>
      </View>

      <View style={styles.track}>
        <View
          style={[
            styles.fill,
            settled && styles.fillSettled,
            { width: `${Math.round(goalFraction(goal) * 100)}%` },
          ]}
        />
      </View>

      {checkIn && (
        <View style={styles.checkIn}>
          <Text style={styles.checkInText}>{checkIn}</Text>
          <View style={styles.checkInActions}>
            <CheckInButton label="Keep going" onPress={() => onDecide(goal, 'keep_going')} />
            <CheckInButton label="Adjust" onPress={() => onOpen(goal)} />
            <CheckInButton label="Call it good" primary onPress={() => onDecide(goal, 'call_it_good')} />
          </View>
        </View>
      )}
    </Pressable>
  )
}

function CheckInButton({ label, onPress, primary = false }) {
  return (
    <Pressable
      style={({ pressed }) => [styles.ciBtn, primary && styles.ciBtnPrimary, pressed && styles.pressed]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Text style={[styles.ciText, primary && styles.ciTextPrimary]}>{label}</Text>
    </Pressable>
  )
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.xl },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm },
  header: { color: color.textSecondary, fontSize: font.md, fontWeight: '700' },
  week: { color: color.textMuted, fontSize: font.sm },
  addIcon: {
    marginLeft: 'auto',
    width: 28,
    height: 28,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
  },
  card: {
    backgroundColor: color.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: spacing.md + 2,
    marginBottom: spacing.sm,
  },
  cardPressed: { backgroundColor: color.surfaceRaised },
  topRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  titleCol: { flex: 1 },
  title: { color: color.textPrimary, fontSize: font.lg, fontWeight: '700' },
  status: { color: color.textMuted, fontSize: font.sm, marginTop: 2 },
  statusMet: { color: color.textSecondary },
  count: { color: color.textPrimary, fontSize: font.xxl, fontWeight: '800', letterSpacing: -0.5 },
  countTarget: { color: color.textMuted, fontSize: font.lg, fontWeight: '600' },
  plus: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Met or called good: logging still works, it just stops asking for attention.
  plusQuiet: { backgroundColor: color.focusTint, borderWidth: 1, borderColor: color.focusBorder },
  plusText: { color: color.onAccent, fontSize: font.lg, fontWeight: '800' },
  plusTextQuiet: { color: color.accent },
  track: {
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: color.border,
    marginTop: spacing.md,
    overflow: 'hidden',
  },
  fill: { height: '100%', borderRadius: radius.pill, backgroundColor: color.accent },
  fillSettled: { backgroundColor: color.textMuted },
  checkIn: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: color.earlierTint,
    borderWidth: 1,
    borderColor: color.earlierBorder,
  },
  checkInText: { color: color.textPrimary, fontSize: font.md, lineHeight: 20 },
  checkInActions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md },
  ciBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm - 1,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: color.borderStrong,
  },
  ciBtnPrimary: { backgroundColor: color.textPrimary, borderColor: color.textPrimary },
  ciText: { color: color.textPrimary, fontSize: font.sm + 1, fontWeight: '600' },
  ciTextPrimary: { color: color.background },
  emptyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md - 2,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: color.borderStrong,
  },
  emptyText: { color: color.textMuted, fontSize: font.sm + 1, flexShrink: 1 },
  pressed: { opacity: 0.75 },
})
