import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  SectionList,
  StyleSheet,
  Text,
  View,
} from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import {
  createCommitment,
  deleteCommitment,
  listCommitments,
  updateCommitment,
} from '../api'
import { useAuth } from '../contexts/AuthContext'
import { sectionizeCommitments } from '../lib/sections'
import { colorForSection } from '../lib/sectionColor'
import TodoItem from '../components/TodoItem'
import AddEditTodoModal from '../components/AddEditTodoModal'
import ConfirmModal from '../components/ConfirmModal'
import { color, font, radius, spacing } from '../theme'

export default function TodoListScreen() {
  const { user, logout } = useAuth()
  const insets = useSafeAreaInsets()
  const [commitments, setCommitments] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editing, setEditing] = useState(null) // commitment being edited, or null for "new"
  const [activeSection, setActiveSection] = useState(null) // null = "All"
  const [pendingDelete, setPendingDelete] = useState(null) // commitment awaiting delete confirmation
  const [signOutVisible, setSignOutVisible] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await listCommitments()
      setCommitments(data)
    } catch (err) {
      Alert.alert('Could not load todos', err.message || 'Try again.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleRefresh() {
    setRefreshing(true)
    await load()
  }

  async function handleToggle(commitment) {
    const newStatus = commitment.status === 'done' ? 'open' : 'done'
    setCommitments((prev) =>
      prev.map((c) => (c.id === commitment.id ? { ...c, status: newStatus } : c)),
    )
    try {
      await updateCommitment(commitment.id, { status: newStatus })
    } catch (err) {
      Alert.alert("Couldn't update", err.message || 'Try again.')
      load()
    }
  }

  function handleDelete(commitment) {
    setPendingDelete(commitment)
  }

  async function confirmDelete() {
    const commitment = pendingDelete
    setPendingDelete(null)
    if (!commitment) return
    setCommitments((prev) => prev.filter((c) => c.id !== commitment.id))
    try {
      await deleteCommitment(commitment.id)
    } catch (err) {
      Alert.alert("Couldn't delete", err.message || 'Try again.')
      load()
    }
  }

  function openCreate() {
    setEditing(null)
    setModalVisible(true)
  }

  function openEdit(commitment) {
    setEditing(commitment)
    setModalVisible(true)
  }

  async function handleSave({ text, due_at, group_name }) {
    setModalVisible(false)
    try {
      if (editing) {
        await updateCommitment(editing.id, { text, due_at, group_name })
      } else {
        await createCommitment({ text, due_at, group_name })
      }
      await load()
    } catch (err) {
      Alert.alert("Couldn't save", err.message || 'Try again.')
    }
  }

  // Sections are user-defined and secondary to the date grouping below — a
  // filter row, not a restructure. Derived from whatever's in use so far,
  // not a fixed list; reused/created per-todo in AddEditTodoModal.
  const knownSections = useMemo(() => {
    const set = new Set(commitments.map((c) => c.group_name).filter(Boolean))
    return Array.from(set).sort()
  }, [commitments])

  // done/total per section, purely for the chip label (e.g. "Job Hunt · 2/5") —
  // a display computation over the existing flat tag, not a new entity.
  const sectionStats = useMemo(() => {
    const stats = {}
    for (const name of knownSections) stats[name] = { done: 0, total: 0 }
    for (const c of commitments) {
      if (!c.group_name || !stats[c.group_name]) continue
      stats[c.group_name].total += 1
      if (c.status === 'done') stats[c.group_name].done += 1
    }
    return stats
  }, [commitments, knownSections])

  const bySection = activeSection
    ? commitments.filter((c) => c.group_name === activeSection)
    : commitments
  const open = bySection.filter((c) => c.status === 'open')
  const done = bySection.filter((c) => c.status === 'done')
  const sections = sectionizeCommitments(open)
  if (done.length > 0) sections.push({ title: 'Done', data: done })

  const initial = (user?.email || '?').trim().charAt(0).toUpperCase()

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={color.accent} />
      </View>
    )
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.headerTitle}>Todos</Text>
        <Pressable
          style={({ pressed }) => [styles.avatar, pressed && styles.pressed]}
          onPress={() => setSignOutVisible(true)}
          hitSlop={8}
        >
          <Text style={styles.avatarText}>{initial}</Text>
        </Pressable>
      </View>

      {knownSections.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.chipRow}
          contentContainerStyle={styles.chipRowContent}
        >
          <SectionChip label="All" active={activeSection === null} onPress={() => setActiveSection(null)} />
          {knownSections.map((name) => (
            <SectionChip
              key={name}
              label={name}
              progress={sectionStats[name]}
              dotColor={colorForSection(name)}
              active={activeSection === name}
              onPress={() => setActiveSection(name)}
            />
          ))}
        </ScrollView>
      )}

      <SectionList
        sections={sections}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <TodoItem
            commitment={item}
            onToggle={handleToggle}
            onPress={openEdit}
            onDelete={handleDelete}
          />
        )}
        renderSectionHeader={({ section }) => (
          <Text style={styles.sectionHeader}>
            {section.title} ({section.data.length})
          </Text>
        )}
        contentContainerStyle={[styles.listContent, { paddingBottom: 120 + insets.bottom }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={color.accent} />}
        ListEmptyComponent={
          <View style={styles.emptyWrap}>
            <Text style={styles.emptyGlyph}>✓</Text>
            <Text style={styles.empty}>Nothing yet</Text>
            <Text style={styles.emptySub}>Tap + to add your first todo.</Text>
          </View>
        }
      />

      <Pressable
        style={({ pressed }) => [styles.fab, { bottom: 28 + insets.bottom }, pressed && styles.fabPressed]}
        onPress={openCreate}
      >
        <Text style={styles.fabText}>+</Text>
      </Pressable>

      <AddEditTodoModal
        visible={modalVisible}
        initial={editing}
        knownSections={knownSections}
        onSave={handleSave}
        onCancel={() => setModalVisible(false)}
      />

      <ConfirmModal
        visible={!!pendingDelete}
        title="Delete todo?"
        message={pendingDelete?.text}
        confirmLabel="Delete"
        destructive
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />

      <ConfirmModal
        visible={signOutVisible}
        title="Signed in"
        message={user?.email}
        confirmLabel="Sign out"
        destructive
        onConfirm={() => {
          setSignOutVisible(false)
          logout()
        }}
        onCancel={() => setSignOutVisible(false)}
      />
    </View>
  )
}

function SectionChip({ label, active, onPress, dotColor, progress }) {
  return (
    <Pressable style={[styles.chip, active && styles.chipActive]} onPress={onPress}>
      {dotColor && <View style={[styles.chipDot, { backgroundColor: dotColor }]} />}
      <Text style={[styles.chipText, active && styles.chipTextActive]}>
        {label}
        {progress && progress.total > 0 ? ` · ${progress.done}/${progress.total}` : ''}
      </Text>
    </Pressable>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: color.background },
  center: { flex: 1, backgroundColor: color.background, alignItems: 'center', justifyContent: 'center' },
  pressed: { opacity: 0.7 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.border,
  },
  headerTitle: { color: color.textPrimary, fontSize: font.xxl, fontWeight: '700', letterSpacing: -0.3 },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: radius.pill,
    backgroundColor: color.surfaceRaised,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: color.accent, fontSize: font.md, fontWeight: '700' },
  sectionHeader: {
    color: color.textMuted,
    fontSize: font.xs - 1,
    fontWeight: '700',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    marginTop: spacing.lg + 2,
    marginBottom: spacing.sm,
  },
  chipRow: { maxHeight: 44, marginTop: spacing.md, marginBottom: spacing.xs },
  chipRowContent: { paddingHorizontal: spacing.lg, gap: spacing.sm },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md + 2,
    paddingVertical: spacing.sm - 1,
    borderRadius: radius.xl,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    marginRight: spacing.sm,
  },
  chipActive: { backgroundColor: color.accent, borderColor: color.accent },
  chipDot: { width: 7, height: 7, borderRadius: radius.pill, marginRight: spacing.xs + 1 },
  chipText: { color: color.textSecondary, fontSize: font.sm + 1, fontWeight: '600' },
  chipTextActive: { color: color.onAccent },
  listContent: { paddingHorizontal: spacing.lg },
  emptyWrap: { alignItems: 'center', marginTop: 80 },
  emptyGlyph: {
    color: color.textMuted,
    fontSize: 22,
    width: 52,
    height: 52,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: color.border,
    backgroundColor: color.surface,
    textAlign: 'center',
    textAlignVertical: 'center',
    lineHeight: 52,
    marginBottom: spacing.lg,
  },
  empty: { color: color.textSecondary, fontSize: font.lg, fontWeight: '600' },
  emptySub: { color: color.textMuted, fontSize: font.sm + 1, marginTop: spacing.xs },
  fab: {
    position: 'absolute',
    right: spacing.xl,
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: color.accent,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  fabPressed: { backgroundColor: color.accentPressed },
  fabText: { color: color.onAccent, fontSize: 28, fontWeight: '600', lineHeight: 30 },
})
