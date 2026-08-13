/**
 * chatScreenTestUtils.js — shared helpers for the ChatScreen.*.test.js
 * files (deliberately one `it()`/one render() per file, not grouped in a
 * single test file with several `it()` blocks -- see the comment atop any
 * of those files for why: this RNTL version's underlying `test-renderer`
 * doesn't cleanly support multiple render() calls in one test file in
 * this environment, jest's per-file module isolation is the only
 * reliable boundary).
 *
 * NOT a *.test.js file itself, so jest doesn't try to run it as a suite.
 */
import { fireEvent, act } from '@testing-library/react-native'

export const navigation = { goBack: () => {}, navigate: () => {} }

export async function sendViaInput(screen, text) {
  // Each step gets its own act() flush -- Pressable's responder wiring
  // needs a settled tick after a text-state change (and again after any
  // intervening re-render, e.g. a prior exchange adding message bubbles)
  // before it reliably picks up a subsequent press in this renderer;
  // without this, fireEvent.press silently no-ops.
  await act(async () => {
    fireEvent.changeText(screen.getByPlaceholderText('Talk to Overwatch…'), text)
  })
  await act(async () => {})
  await act(async () => {
    fireEvent.press(screen.getByTestId('chat-send-button'))
  })
}
