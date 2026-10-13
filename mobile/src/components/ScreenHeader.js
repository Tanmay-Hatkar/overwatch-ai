import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Ionicons } from '@react-native-vector-icons/ionicons'
import { color, font, spacing } from '../theme'

/**
 * Shared top bar for pushed screens (Chat, Briefing, Reflection): a back
 * chevron, a centred title, and an optional leading icon. One copy instead
 * of three hand-rolled `‹` glyph headers.
 *
 * Props:
 *   title    — screen title
 *   icon     — optional Ionicons name shown before the title
 *   onBack   — back handler (usually navigation.goBack)
 */
export default function ScreenHeader({ title, icon, onBack }) {
  const insets = useSafeAreaInsets()
  return (
    <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
      <Pressable
        onPress={onBack}
        hitSlop={12}
        style={({ pressed }) => [styles.side, pressed && styles.pressed]}
        accessibilityRole="button"
        accessibilityLabel="Back"
      >
        <Ionicons name="chevron-back" size={24} color={color.textPrimary} />
      </Pressable>
      <View style={styles.titleRow}>
        {!!icon && <Ionicons name={icon} size={17} color={color.accent} />}
        <Text style={styles.title} accessibilityRole="header">
          {title}
        </Text>
      </View>
      <View style={styles.side} />
    </View>
  )
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.border,
  },
  side: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  pressed: { opacity: 0.6 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm - 2 },
  title: { color: color.textPrimary, fontSize: font.xl, fontWeight: '700' },
})
