import { useEffect, useState } from 'react'
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import DateTimePicker from '@react-native-community/datetimepicker'
import { color, font, radius, spacing } from '../theme'
import { colorForSection } from '../lib/sectionColor'

/**
 * Structured create/edit form for a single commitment.
 *
 * Structured (title + optional due date/time) rather than natural-language
 * capture on purpose — NL/voice input is explicitly out of scope for this
 * pass (that's the talkback-system follow-up), so this is the only way to
 * create a commitment for now. Mirrors CommitmentCreate/CommitmentUpdate's
 * shape (text, due_at, group_name) from backend/app/models/commitment.py.
 *
 * Section (group_name) is user-defined and secondary — pick a previously
 * used one or type a new one inline. Not a fixed enum: reusing
 * `knownSections` (derived from existing todos) is how "reuse it" works,
 * no separate section-management screen.
 *
 * Wrapped in KeyboardAvoidingView + a ScrollView so the on-screen keyboard
 * doesn't cover the Save button or section row when the text input is
 * focused — the sheet scrolls instead of being pushed off-screen.
 */
export default function AddEditTodoModal({ visible, initial, knownSections, onSave, onCancel }) {
  const [text, setText] = useState('')
  const [hasDueDate, setHasDueDate] = useState(false)
  const [dueAt, setDueAt] = useState(new Date())
  const [pickerMode, setPickerMode] = useState(null) // 'date' | 'time' | null
  const [section, setSection] = useState('')
  const [addingSection, setAddingSection] = useState(false)
  const [newSectionText, setNewSectionText] = useState('')
  const insets = useSafeAreaInsets()

  useEffect(() => {
    if (!visible) return
    if (initial) {
      setText(initial.text)
      setHasDueDate(!!initial.due_at)
      setDueAt(initial.due_at ? new Date(initial.due_at) : new Date())
      setSection(initial.group_name || '')
    } else {
      setText('')
      setHasDueDate(false)
      setDueAt(new Date())
      setSection('')
    }
    setAddingSection(false)
    setNewSectionText('')
  }, [visible, initial])

  function handleSave() {
    const trimmed = text.trim()
    if (!trimmed) return
    onSave({
      text: trimmed,
      due_at: hasDueDate ? dueAt.toISOString() : null,
      group_name: section,
    })
  }

  function confirmNewSection() {
    const trimmed = newSectionText.trim()
    if (trimmed) setSection(trimmed)
    setAddingSection(false)
    setNewSectionText('')
  }

  function onPickerChange(event, selected) {
    const mode = pickerMode
    setPickerMode(null)
    if (event.type === 'dismissed' || !selected) return
    const next = new Date(dueAt)
    if (mode === 'date') {
      next.setFullYear(selected.getFullYear(), selected.getMonth(), selected.getDate())
    } else {
      next.setHours(selected.getHours(), selected.getMinutes())
    }
    setDueAt(next)
  }

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onCancel}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <Pressable style={styles.backdrop} onPress={onCancel}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <View style={styles.handle} />
            <ScrollView
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
              contentContainerStyle={{ paddingBottom: spacing.lg + insets.bottom }}
            >
              <Text style={styles.title}>{initial ? 'Edit todo' : 'New todo'}</Text>

              <TextInput
                value={text}
                onChangeText={setText}
                placeholder="What do you need to do?"
                placeholderTextColor={color.textMuted}
                style={styles.input}
                autoFocus
                multiline
              />

              <View style={styles.dueRow}>
                <Text style={styles.dueLabel}>Due date</Text>
                <Switch
                  value={hasDueDate}
                  onValueChange={setHasDueDate}
                  trackColor={{ true: color.accentMuted, false: color.border }}
                  thumbColor={hasDueDate ? color.accent : '#9a9aa2'}
                />
              </View>

              {hasDueDate && (
                <View style={styles.dueButtons}>
                  <Pressable style={styles.dueBtn} onPress={() => setPickerMode('date')}>
                    <Text style={styles.dueBtnText}>
                      {dueAt.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}
                    </Text>
                  </Pressable>
                  <Pressable style={styles.dueBtn} onPress={() => setPickerMode('time')}>
                    <Text style={styles.dueBtnText}>
                      {dueAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                    </Text>
                  </Pressable>
                </View>
              )}

              {pickerMode && (
                <DateTimePicker
                  value={dueAt}
                  mode={pickerMode}
                  is24Hour={false}
                  display={Platform.OS === 'ios' ? 'spinner' : 'default'}
                  onChange={onPickerChange}
                />
              )}

              <Text style={[styles.dueLabel, styles.sectionLabel]}>Section</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.sectionRow}>
                <Pressable
                  style={[styles.sectionChip, section === '' && !addingSection && styles.sectionChipActive]}
                  onPress={() => {
                    setSection('')
                    setAddingSection(false)
                  }}
                >
                  <Text style={[styles.sectionChipText, section === '' && !addingSection && styles.sectionChipTextActive]}>
                    None
                  </Text>
                </Pressable>
                {knownSections?.map((name) => (
                  <Pressable
                    key={name}
                    style={[styles.sectionChip, section === name && styles.sectionChipActive]}
                    onPress={() => {
                      setSection(name)
                      setAddingSection(false)
                    }}
                  >
                    <View
                      style={[
                        styles.sectionChipDot,
                        { backgroundColor: colorForSection(name) },
                        section === name && styles.sectionChipDotActive,
                      ]}
                    />
                    <Text style={[styles.sectionChipText, section === name && styles.sectionChipTextActive]}>
                      {name}
                    </Text>
                  </Pressable>
                ))}
                <Pressable
                  style={[styles.sectionChip, addingSection && styles.sectionChipActive]}
                  onPress={() => setAddingSection(true)}
                >
                  <Text style={[styles.sectionChipText, addingSection && styles.sectionChipTextActive]}>
                    + New
                  </Text>
                </Pressable>
              </ScrollView>

              {addingSection && (
                <TextInput
                  value={newSectionText}
                  onChangeText={setNewSectionText}
                  placeholder="Section name"
                  placeholderTextColor={color.textMuted}
                  style={styles.newSectionInput}
                  autoFocus
                  onSubmitEditing={confirmNewSection}
                  onBlur={confirmNewSection}
                  returnKeyType="done"
                />
              )}

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
                    !text.trim() && styles.saveBtnDisabled,
                    pressed && text.trim() && styles.pressed,
                  ]}
                  onPress={handleSave}
                  disabled={!text.trim()}
                >
                  <Text style={styles.saveText}>Save</Text>
                </Pressable>
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      </KeyboardAvoidingView>
    </Modal>
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
    minHeight: 60,
    textAlignVertical: 'top',
  },
  dueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.lg,
  },
  dueLabel: { color: color.textSecondary, fontSize: font.md },
  dueButtons: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  dueBtn: {
    flex: 1,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm + 2,
    alignItems: 'center',
  },
  dueBtnText: { color: color.textPrimary, fontSize: font.sm + 1 },
  sectionLabel: { marginTop: spacing.lg + 2, marginBottom: spacing.sm },
  sectionRow: { flexGrow: 0 },
  sectionChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.xl,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    marginRight: spacing.sm,
  },
  sectionChipActive: { backgroundColor: color.accent, borderColor: color.accent },
  sectionChipDot: { width: 7, height: 7, borderRadius: radius.pill, marginRight: spacing.xs + 1 },
  sectionChipDotActive: { borderWidth: 1, borderColor: color.onAccent },
  sectionChipText: { color: color.textSecondary, fontSize: font.sm, fontWeight: '600' },
  sectionChipTextActive: { color: color.onAccent },
  newSectionInput: {
    color: color.textPrimary,
    fontSize: font.md,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.accent,
    borderRadius: radius.sm,
    padding: spacing.sm + 2,
    marginTop: spacing.sm,
  },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xxl - 2 },
  pressed: { opacity: 0.8 },
  actionBtn: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.md, alignItems: 'center' },
  cancelBtn: { backgroundColor: color.surface, borderWidth: 1, borderColor: color.border },
  cancelText: { color: color.textSecondary, fontSize: font.md, fontWeight: '600' },
  saveBtn: { backgroundColor: color.accent },
  saveBtnDisabled: { opacity: 0.4 },
  saveText: { color: color.onAccent, fontSize: font.md, fontWeight: '700' },
})
