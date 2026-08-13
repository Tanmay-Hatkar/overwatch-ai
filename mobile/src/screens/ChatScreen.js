import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { sendChatMessage, getChatHistory } from '../api'
import { color, font, radius, spacing } from '../theme'

const MAX_HISTORY_TURNS = 20
const HISTORY_FOR_PROMPT = 10

/**
 * ChatScreen — the primary AI capture surface. Natural language (typed for
 * now; voice is a later addition) is the only channel that reliably fills
 * due_at/recurrence/reminder_phrase correctly — the structured form on
 * TodoListScreen only fills what's explicitly typed into fields.
 *
 * Ports frontend/src/components/ChatBar.jsx's logic: server-backed history
 * (cross-device) with instant local state for optimistic UI, and structured
 * clarify — a clarify reply with clarify_options (confirm_recurring /
 * confirm_target, a yes/no or pick-one-of-a-few question) renders as
 * tap-only chips instead of forcing the user to type a free-text answer.
 */
export default function ChatScreen({ navigation }) {
  const insets = useSafeAreaInsets()
  const [history, setHistory] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const listRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    getChatHistory()
      .then((turns) => {
        if (!cancelled && Array.isArray(turns)) {
          setHistory(turns.slice(-MAX_HISTORY_TURNS).map((t) => ({ ...t, id: makeId() })))
        }
      })
      .catch(() => {
        // Offline / not signed in yet — start with empty history rather
        // than blocking the screen; the user can still send a message.
      })
      .finally(() => setLoadingHistory(false))
    return () => {
      cancelled = true
    }
  }, [])

  const scrollToEnd = useCallback(() => {
    requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }))
  }, [])

  useEffect(() => {
    if (history.length > 0) scrollToEnd()
  }, [history.length, scrollToEnd])

  async function sendMessage(text) {
    const trimmed = text.trim()
    if (!trimmed || busy) return

    const userTurn = { id: makeId(), role: 'user', content: trimmed }
    const nextHistory = [...history, userTurn].slice(-MAX_HISTORY_TURNS)
    setHistory(nextHistory)
    setInput('')
    setBusy(true)

    try {
      const promptHistory = nextHistory
        .slice(-HISTORY_FOR_PROMPT - 1, -1)
        .map(({ role, content }) => ({ role, content }))
      const result = await sendChatMessage(trimmed, promptHistory)

      const assistantTurn = {
        id: makeId(),
        role: 'assistant',
        content: result.reply,
        clarifyKind: result.intent === 'clarify' ? result.clarify_kind : undefined,
        clarifyOptions: result.intent === 'clarify' ? result.clarify_options : undefined,
        commitmentCreated: result.intent === 'add_commitment' && result.commitment ? result.commitment.text : undefined,
      }
      setHistory((prev) => [...prev, assistantTurn].slice(-MAX_HISTORY_TURNS))
    } catch (err) {
      const message = err.message?.includes('503')
        ? "I'm having trouble thinking right now. Try again in a moment."
        : err.message || 'Something went wrong.'
      setHistory((prev) =>
        [...prev, { id: makeId(), role: 'assistant', content: message, error: true }].slice(
          -MAX_HISTORY_TURNS,
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={insets.top}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => navigation.goBack()} hitSlop={12} style={styles.backButton}>
          <Text style={styles.backGlyph}>‹</Text>
        </Pressable>
        <Text style={styles.headerTitle}>Chat</Text>
        <View style={styles.backButton} />
      </View>

      {loadingHistory ? (
        <View style={styles.center}>
          <ActivityIndicator color={color.accent} />
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={history}
          keyExtractor={(turn) => turn.id}
          renderItem={({ item, index }) => (
            <ChatBubble
              turn={item}
              isLatest={index === history.length - 1}
              onChipTap={sendMessage}
              disabled={busy}
            />
          )}
          contentContainerStyle={styles.listContent}
          onContentSizeChange={scrollToEnd}
          ListEmptyComponent={
            <View style={styles.emptyWrap}>
              <Text style={styles.emptyGlyph}>💬</Text>
              <Text style={styles.empty}>Tell Overwatch what you said you'd do</Text>
              <Text style={styles.emptySub}>"call mom tomorrow at 3pm", "gym 4 times a week"…</Text>
            </View>
          }
        />
      )}

      {busy && (
        <View style={styles.typingRow}>
          <ActivityIndicator size="small" color={color.textMuted} />
          <Text style={styles.typingText}>thinking…</Text>
        </View>
      )}

      <View style={[styles.inputRow, { paddingBottom: spacing.md + insets.bottom }]}>
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="Talk to Overwatch…"
          placeholderTextColor={color.textMuted}
          style={styles.input}
          editable={!busy}
          multiline
          onSubmitEditing={() => sendMessage(input)}
          blurOnSubmit={false}
        />
        <Pressable
          testID="chat-send-button"
          onPress={() => sendMessage(input)}
          disabled={busy || !input.trim()}
          style={({ pressed }) => [
            styles.sendButton,
            (busy || !input.trim()) && styles.sendButtonDisabled,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.sendButtonText}>{busy ? '…' : 'Send'}</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  )
}

let idCounter = 0
function makeId() {
  idCounter += 1
  return `t${Date.now()}-${idCounter}`
}

/**
 * Renders one turn. When the latest assistant turn is a 'clarify' with
 * clarify_options (confirm_recurring / confirm_target), shows tap-only
 * chips instead of leaving the user to type a free-text answer. Tapping a
 * chip sends its exact label as the next message via onChipTap — same
 * pipeline as typing it, no new endpoint. 'time'/'open' clarify_kinds have
 * no fixed options and fall back to the plain bubble, same as today.
 */
function ChatBubble({ turn, isLatest, onChipTap, disabled }) {
  const isUser = turn.role === 'user'
  const showChips = isLatest && !isUser && turn.clarifyOptions && turn.clarifyOptions.length > 0

  return (
    <View style={[styles.bubbleRow, isUser ? styles.bubbleRowUser : styles.bubbleRowAssistant]}>
      <View
        style={[
          styles.bubble,
          isUser ? styles.bubbleUser : turn.error ? styles.bubbleError : styles.bubbleAssistant,
        ]}
      >
        <Text style={[styles.bubbleText, isUser && styles.bubbleTextUser]}>{turn.content}</Text>
      </View>
      {turn.commitmentCreated && (
        <Text style={styles.createdTag}>✓ Added: {turn.commitmentCreated}</Text>
      )}
      {showChips && (
        <View style={styles.chipRow}>
          {turn.clarifyOptions.map((option) => (
            <Pressable
              key={option}
              testID={`clarify-chip-${option}`}
              disabled={disabled}
              onPress={() => onChipTap(option)}
              style={({ pressed }) => [
                styles.clarifyChip,
                disabled && styles.clarifyChipDisabled,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.clarifyChipText}>{option}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: color.background },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  pressed: { opacity: 0.7 },
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
  listContent: { padding: spacing.lg, paddingBottom: spacing.xl, flexGrow: 1 },
  emptyWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: 80 },
  emptyGlyph: { fontSize: 36, marginBottom: spacing.lg },
  empty: { color: color.textSecondary, fontSize: font.lg, fontWeight: '600', textAlign: 'center' },
  emptySub: { color: color.textMuted, fontSize: font.sm + 1, marginTop: spacing.xs, textAlign: 'center' },
  bubbleRow: { marginBottom: spacing.md, maxWidth: '85%' },
  bubbleRowUser: { alignSelf: 'flex-end', alignItems: 'flex-end' },
  bubbleRowAssistant: { alignSelf: 'flex-start', alignItems: 'flex-start' },
  bubble: { paddingHorizontal: spacing.md + 2, paddingVertical: spacing.sm + 2, borderRadius: radius.lg },
  bubbleUser: { backgroundColor: color.accentMuted, borderWidth: 1, borderColor: color.accent },
  bubbleAssistant: { backgroundColor: color.surface, borderWidth: 1, borderColor: color.border },
  bubbleError: { backgroundColor: 'rgba(239, 68, 68, 0.1)', borderWidth: 1, borderColor: color.dangerStrong },
  bubbleText: { color: color.textPrimary, fontSize: font.md, lineHeight: 20 },
  bubbleTextUser: { color: color.textPrimary },
  createdTag: { color: color.accent, fontSize: font.xs, fontWeight: '600', marginTop: spacing.xs, marginLeft: spacing.xs },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm },
  clarifyChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm - 1,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(249, 115, 22, 0.1)',
    borderWidth: 1,
    borderColor: color.accent,
  },
  clarifyChipDisabled: { opacity: 0.5 },
  clarifyChipText: { color: color.accent, fontSize: font.sm + 1, fontWeight: '600' },
  typingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.xs },
  typingText: { color: color.textMuted, fontSize: font.sm },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.border,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.border,
    borderRadius: radius.lg,
    color: color.textPrimary,
    fontSize: font.md,
  },
  sendButton: {
    height: 44,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: color.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: { backgroundColor: color.surfaceRaised },
  sendButtonText: { color: color.onAccent, fontSize: font.md, fontWeight: '700' },
})
