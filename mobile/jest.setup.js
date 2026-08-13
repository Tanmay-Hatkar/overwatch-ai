/**
 * jest.setup.js — global test-environment mocks, loaded via package.json's
 * jest.setupFiles before each test file runs.
 *
 * react-native-safe-area-context's own published jest mock
 * (react-native-safe-area-context/jest/mock.tsx) ships as a default export
 * (`export default {...}`), which doesn't line up with this project's named
 * imports (`import { useSafeAreaInsets } from '...'`) once run through our
 * Babel/CJS interop -- named lookups come back undefined. Every screen uses
 * this hook (TodoListScreen, ChatScreen, and more to come), so it's mocked
 * once here globally rather than per test file.
 */
jest.mock('react-native-safe-area-context', () => {
  const insets = { top: 0, right: 0, bottom: 0, left: 0 }
  const frame = { x: 0, y: 0, width: 320, height: 640 }
  return {
    SafeAreaProvider: ({ children }) => children,
    useSafeAreaInsets: () => insets,
    useSafeAreaFrame: () => frame,
    initialWindowMetrics: { insets, frame },
  }
})
