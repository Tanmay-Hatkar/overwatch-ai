import { useEffect, useState } from 'react'
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Ionicons } from '@react-native-vector-icons/ionicons'
import { color, font, radius, spacing } from '../theme'

// Mirrors the backend's GoalCreate bounds (settings.goal_max_target).
const MIN_TARGET = 1
const MAX_TARGET = 100
const DEFAULT_TARGET = 5

/**
 * Create/edit sheet for a weekly goal (ADR-0026). Same sheet language as
 * AddEditTodoModal. Chat is the faster way in ("10 applications a week");
 * this is the manual path and the place to adjust or undo.
 *
 * Props:
 *   visible, initial (GoalResponse | null), onSave({text, target_count}),
 *   onCancel, onUndo(goal), onDelete(goal)
 */
export default function GoalModal({ visible, initial, onSave, onCancel, onUndo, onDelete }) {
  const [text, setText] = useState('')
  const [target, setTarget] = useState(DEFAULT_TARGET)
  const insets = useSafeAreaInsets()

  useEffect(() => {
    if (!visible) return
    setText(initial ? initial.text : '')
    setTarget(initial ? initial.target_count : DEFAULT_TARGET)
  }, [visible, initial])

  const clamp = (n) => Math.max(MIN_TARGET, Math.min(MAX_TARGET, n))
  const canSave = text.trim().length > 0

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onCancel}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <Pressable style={styles.backdrop} onPress={onCancel}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <View style={styles.handle} />
            <ScrollView
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
              contentContainerStyle={{ paddingBottom: spacing.lg + insets.bottom }}
            >
              <Text style={styles.title}>{initial ? 'Weekly goal' : 'New weekly goal'}</Text>

              <TextInput
                value={text}
                onChangeText={setText}
                placeholder="What are you counting? e.g. Job applications"
                placeholderTextColor={color.textMuted}
                style={styles.input}
                autoFocus={!initial}
                maxLength={200}
                accessibilityLabel="Goal name"
              />

              <Text style={styles.label}>Times per week</Text>
              <View style={styles.stepper}>
                <StepButton icon="remove" label="Fewer" onPress={() => setTarget((t) => clamp(t - 1))} />
                <Text style={styles.target} accessibilityLabel={`${target} times per week`}>
                  {target}
                </Text>
                <StepButton icon="add" label="More" onPress={() => setTarget((t) => clamp(t + 1))} />
              </View>
              <Text style={styles.hint}>
                Counts reset every Monday. No streaks, no carryover. A rough week just ends.
              </Text>

              <View style={styles.actions}>
                <Pressable
                  style={({ pressed }) => [styles.actionBtn, styles.cancelBtn, pressed && styles.pressed]}
                  onPress={onCancel}
                >
                  <Text style={styles.cancelText}>Cancel</Text>
                </Pressable>
                <Pressable
                  style={({ pressed }) => [
                    styles.actionBtn,
                    styles.saveBtn,
                    !canSave && styles.saveBtnDisabled,
                    pressed && canSave && styles.pressed,
                  ]}
                  onPress={() => canSave && onSave({ text: text.trim(), target_count: target })}
                  disabled={!canSave}
                >
                  <Text style={styles.saveText}>Save</Text>
                </Pressable>
              </View>

              {initial && (
                <View style={styles.footer}>
                  {initial.done_this_week > 0 && (
                    <Pressable
                      style={({ pressed }) => [styles.footerBtn, pressed && styles.pressed]}
                      onPress={() => onUndo(initial)}
                      accessibilityRole="button"
                      accessibilityLabel="Undo the last logged one"
                    >
                      <Ionicons name="arrow-undo-outline" size={15} color={color.textSecondary} />
                      <Text style={styles.undoText}>Undo last +1</Text>
                    </Pressable>
                  )}
                  <Pressable
                    style={({ pressed }) => [styles.footerBtn, pressed && styles.pressed]}
                    onPress={() => onDelete(initial)}
                    accessibilityRole="button"
                    accessibilityLabel={`Delete ${initial.text}`}
                  >
                    <Text style={styles.deleteText}>Delete goal</Text>
                  </Pressable>
                </View>
              )}
            </ScrollView>
          </Pressable>
        </Pressable>
      </KeyboardAvoidingView>
    </Modal>
  )
}

function StepButton({ icon, label, onPress }) {
  return (
    <Pressable
      style={({ pressed }) => [styles.stepBtn, pressed && styles.pressed]}
      onPress={onPress}
      hitSlop={6}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Ionicons name={icon} size={20} color={color.textPrimary} />
    </Pressable>
  )
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  backdrop: { flex: 1, backgroundColor: color.backdrop, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: color.surfaceRaised,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    borderWidth: 1,
    borderColor: color.border,
    borderBottomWidth: 0,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.sm,
    maxHeight: '88%',
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: radius.pill,
    backgroundColor: color.borderStrong,
    marginBottom: spacing.md,
  },
  title: { color: color.textPrimary, fontSize: font.xl, fontWeight: '700', marginBottom: spacing.lg },
  input: {
    color: color.textPrimary,
    fontSize: font.lg,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  label: { color: color.textSecondary, fontSize: font.md, marginTop: spacing.xl },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: spacing.xl, marginTop: spacing.sm },
  stepBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  target: {
    color: color.textPrimary,
    fontSize: font.display,
    fontWeight: '800',
    minWidth: 48,
    textAlign: 'center',
  },
  hint: { color: color.textMuted, fontSize: font.sm, marginTop: spacing.md, lineHeight: 18 },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xxl - 2 },
  pressed: { opacity: 0.8 },
  actionBtn: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.md, alignItems: 'center' },
  cancelBtn: { backgroundColor: color.surface, borderWidth: 1, borderColor: color.border },
  cancelText: { color: color.textSecondary, fontSize: font.md, fontWeight: '600' },
  saveBtn: { backgroundColor: color.accent },
  saveBtnDisabled: { opacity: 0.4 },
  saveText: { color: color.onAccent, fontSize: font.md, fontWeight: '700' },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.xl,
    marginTop: spacing.lg,
  },
  footerBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: spacing.sm },
  undoText: { color: color.textSecondary, fontSize: font.md, fontWeight: '600' },
  deleteText: { color: color.danger, fontSize: font.md, fontWeight: '600' },
})
