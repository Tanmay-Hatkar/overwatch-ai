import { Modal, Pressable, StyleSheet, Text, View } from 'react-native'
import { color, font, radius, spacing } from '../theme'

/**
 * Themed replacement for `Alert.alert` confirmations.
 *
 * The native Android AlertDialog rendered with a large dead gap between the
 * message and the action row (visually "chopped") and didn't match the
 * app's dark/orange language. This is a fixed-height sheet instead, so
 * short messages don't leave stray empty space.
 */
export default function ConfirmModal({
  visible,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  onConfirm,
  onCancel,
}) {
  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onCancel}>
      <Pressable style={styles.backdrop} onPress={onCancel}>
        <Pressable style={styles.card} onPress={() => {}}>
          <Text style={styles.title}>{title}</Text>
          {message ? <Text style={styles.message}>{message}</Text> : null}

          <View style={styles.actions}>
            <Pressable
              style={({ pressed }) => [styles.actionBtn, styles.cancelBtn, pressed && styles.pressed]}
              onPress={onCancel}
            >
              <Text style={styles.cancelText}>{cancelLabel}</Text>
            </Pressable>
            <Pressable
              style={({ pressed }) => [
                styles.actionBtn,
                destructive ? styles.dangerBtn : styles.confirmBtn,
                pressed && styles.pressed,
              ]}
              onPress={onConfirm}
            >
              <Text style={destructive ? styles.dangerText : styles.confirmText}>{confirmLabel}</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  )
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: color.backdrop,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  card: {
    width: '100%',
    maxWidth: 340,
    backgroundColor: color.surfaceRaised,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: color.border,
    padding: spacing.xl,
  },
  title: { color: color.textPrimary, fontSize: font.xl, fontWeight: '700' },
  message: { color: color.textSecondary, fontSize: font.md, marginTop: spacing.sm, lineHeight: 20 },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xl },
  actionBtn: {
    flex: 1,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    alignItems: 'center',
  },
  pressed: { opacity: 0.75 },
  cancelBtn: { backgroundColor: color.surface, borderWidth: 1, borderColor: color.border },
  cancelText: { color: color.textSecondary, fontSize: font.md, fontWeight: '600' },
  confirmBtn: { backgroundColor: color.accent },
  confirmText: { color: color.onAccent, fontSize: font.md, fontWeight: '700' },
  dangerBtn: { backgroundColor: color.dangerStrong },
  dangerText: { color: '#fff', fontSize: font.md, fontWeight: '700' },
})
