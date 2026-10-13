import { useCallback, useMemo, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  SectionList,
  StyleSheet,
  Text,
  View,
} from 'react-native'
import { useFocusEffect } from '@react-navigation/native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Ionicons } from '@react-native-vector-icons/ionicons'
import {
  createCommitment,
  deleteCommitment,
  listCommitments,
  updateCommitment,
} from '../api'
import { useAuth } from '../contexts/AuthContext'
import { sectionizeCommitments } from '../lib/sections'
import { firstNameOf, greetingFor, pickUpNext } from '../lib/focus'
import { colorForSection } from '../lib/sectionColor'
import { syncCommitmentReminders } from '../lib/notifications'
import { reconcileRingAlarms } from '../lib/ringAlarm'
import TodoItem from '../components/TodoItem'
import UpNextCard from '../components/UpNextCard'
import AddEditTodoModal from '../components/AddEditTodoModal'
import ConfirmModal from '../components/ConfirmModal'
import { color, font, radius, spacing } from '../theme'

// Display titles for sectionizeCommitments()'s buckets. "Overdue" is the
// internal bucket name; on screen it's framed as a neutral fact, not a
// failure (PRD §5 principle 3).
const SECTION_TITLES = { Overdue: 'From earlier' }

export default function TodoListScreen({ navigation }) {
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
      // Reconcile the OS notification schedule with whatever's actually
      // in the list now -- best-effort, never blocks the UI on failure.
      syncCommitmentReminders(data)
      reconcileRingAlarms(data)
    } catch (err) {
      Alert.alert('Could not load todos', err.message || 'Try again.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  // Refetch every time this screen regains focus, not just on mount --
  // commitments created via ChatScreen need to show up on the way back.
  useFocusEffect(
    useCallback(() => {
      load()
    }, [load]),
  )

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
    setModalVisible(false)
    setPendingDelete(commitment)
  }

  async function handleDone(commitment) {
    if (commitment.status !== 'done') await handleToggle(commitment)
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

  const bySection = activeSection
    ? commitments.filter((c) => c.group_name === activeSection)
    : commitments
  const open = bySection.filter((c) => c.status === 'open')
  const done = bySection.filter((c) => c.status === 'done')
  const sections = sectionizeCommitments(open)
  if (done.length > 0) sections.push({ title: 'Done', data: done })

  const firstName = firstNameOf(user)
  const initial = (firstName || '?').charAt(0).toUpperCase()
  const now = new Date()
  const focus = activeSection ? null : pickUpNext(commitments, now)
  const today = now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={color.accent} />
      </View>
    )
  }

  const listHeader = (
    <View>
      {focus && (
        <UpNextCard
          focus={focus}
          now={now}
          onDone={handleDone}
          onMove={openEdit}
          onTalk={() => navigation.navigate('Chat')}
        />
      )}
      {knownSections.length > 0 && (
        <View style={styles.chipRow}>
          <SectionChip label="All" active={activeSection === null} onPress={() => setActiveSection(null)} />
          {knownSections.map((name) => (
            <SectionChip
              key={name}
              label={name}
              dotColor={colorForSection(name)}
              active={activeSection === name}
              onPress={() => setActiveSection(name)}
            />
          ))}
        </View>
      )}
    </View>
  )

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
        <View style={styles.headerText}>
          <Text style={styles.date}>{today}</Text>
          <Text style={styles.greeting} numberOfLines={2}>
            {greetingFor(now)}
            {firstName ? `, ${firstName}` : ''}
          </Text>
        </View>
        <View style={styles.headerActions}>
          <HeaderIcon icon="partly-sunny-outline" label="Morning brief" onPress={() => navigation.navigate('Briefing')} />
          <HeaderIcon icon="moon-outline" label="Evening reflection" onPress={() => navigation.navigate('Reflection')} />
          <Pressable
            style={({ pressed }) => [styles.avatar, pressed && styles.pressed]}
            onPress={() => setSignOutVisible(true)}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Account"
          >
            <Text style={styles.avatarText}>{initial}</Text>
          </Pressable>
        </View>
      </View>

      <SectionList
        sections={sections}
        keyExtractor={(item) => item.id}
        ListHeaderComponent={listHeader}
        stickySectionHeadersEnabled={false}
        renderItem={({ item }) => <TodoItem commitment={item} onToggle={handleToggle} onPress={openEdit} />}
        renderSectionHeader={({ section }) => (
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.sectionHeader}>{SECTION_TITLES[section.title] || section.title}</Text>
            <Text style={styles.sectionCount}>{section.data.length}</Text>
          </View>
        )}
        contentContainerStyle={[styles.listContent, { paddingBottom: 110 + insets.bottom }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor={color.accent} />}
        ListEmptyComponent={
          <View style={styles.emptyWrap}>
            <View style={styles.emptyGlyph}>
              <Ionicons name="sparkles-outline" size={22} color={color.accent} />
            </View>
            <Text style={styles.empty}>Nothing planned yet</Text>
            <Text style={styles.emptySub}>Tell Overwatch what you'll do today. It'll check in at the time you said.</Text>
          </View>
        }
      />

      <View style={[styles.captureBar, { paddingBottom: spacing.md + insets.bottom }]}>
        <Pressable
          style={({ pressed }) => [styles.captureInput, pressed && styles.capturePressed]}
          onPress={() => navigation.navigate('Chat')}
          accessibilityRole="button"
          accessibilityLabel="Chat with Overwatch"
        >
          <Ionicons name="chatbubble-ellipses" size={18} color={color.accent} />
          <Text style={styles.capturePlaceholder} numberOfLines={1}>
            Tell Overwatch what you'll do…
          </Text>
        </Pressable>
        <Pressable
          style={({ pressed }) => [styles.addButton, pressed && styles.pressed]}
          onPress={openCreate}
          accessibilityRole="button"
          accessibilityLabel="Add a todo manually"
        >
          <Ionicons name="add" size={24} color={color.textPrimary} />
        </Pressable>
      </View>

      <AddEditTodoModal
        visible={modalVisible}
        initial={editing}
        knownSections={knownSections}
        onSave={handleSave}
        onCancel={() => setModalVisible(false)}
        onDelete={handleDelete}
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

function SectionChip({ label, active, onPress, dotColor }) {
  return (
    <Pressable
      style={[styles.chip, active && styles.chipActive]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      accessibilityLabel={`Show ${label}`}
    >
      {dotColor && <View style={[styles.chipDot, { backgroundColor: dotColor }]} />}
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  )
}

function HeaderIcon({ icon, label, onPress }) {
  return (
    <Pressable
      style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
      onPress={onPress}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Ionicons name={icon} size={18} color={color.textSecondary} />
    </Pressable>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: color.background },
  center: { flex: 1, backgroundColor: color.background, alignItems: 'center', justifyContent: 'center' },
  pressed: { opacity: 0.7 },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xs,
    gap: spacing.md,
  },
  headerText: { flex: 1 },
  greeting: { color: color.textPrimary, fontSize: font.xxl + 2, fontWeight: '800', letterSpacing: -0.5, marginTop: 2 },
  date: {
    color: color.textMuted,
    fontSize: font.xs,
    fontWeight: '700',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  iconButton: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatar: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    backgroundColor: color.accentMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: '#fed7aa', fontSize: font.lg, fontWeight: '800' },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.lg },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md + 2,
    paddingVertical: spacing.sm - 1,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
  },
  chipActive: { backgroundColor: color.textPrimary, borderColor: color.textPrimary },
  chipDot: { width: 7, height: 7, borderRadius: radius.pill, marginRight: spacing.xs + 2 },
  chipText: { color: color.textSecondary, fontSize: font.sm + 1, fontWeight: '600' },
  chipTextActive: { color: color.background },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.sm,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
  },
  sectionHeader: { color: color.textSecondary, fontSize: font.md, fontWeight: '700' },
  sectionCount: { color: color.textMuted, fontSize: font.sm },
  listContent: { paddingHorizontal: spacing.lg },
  emptyWrap: { alignItems: 'center', marginTop: 72, paddingHorizontal: spacing.xxl },
  emptyGlyph: {
    width: 56,
    height: 56,
    borderRadius: radius.pill,
    backgroundColor: color.focusTint,
    borderWidth: 1,
    borderColor: color.focusBorder,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  empty: { color: color.textPrimary, fontSize: font.xl, fontWeight: '700' },
  emptySub: { color: color.textMuted, fontSize: font.md, marginTop: spacing.xs + 2, textAlign: 'center', lineHeight: 20 },
  captureBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    backgroundColor: color.background,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.border,
  },
  captureInput: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm + 2,
    height: 50,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    backgroundColor: color.surfaceRaised,
    borderWidth: 1,
    borderColor: color.borderStrong,
  },
  capturePressed: { backgroundColor: color.surface },
  capturePlaceholder: { color: color.textSecondary, fontSize: font.lg, flexShrink: 1 },
  addButton: {
    width: 50,
    height: 50,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
})
