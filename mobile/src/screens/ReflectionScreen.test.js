/**
 * ReflectionScreen.test.js — one scenario per file deliberately; see
 * chatScreenTestUtils.js for why.
 */
import { describe, it, expect, jest } from '@jest/globals'
import { render, waitFor } from '@testing-library/react-native'
import { NavigationContainer } from '@react-navigation/native'

jest.mock('../api', () => ({
  getEveningReflection: jest.fn(() =>
    Promise.resolve({
      content: 'You called mom and finished the report. The gym session is still open.',
      done_count: 2,
      open_count: 1,
      abandoned_count: 0,
      cached: false,
    }),
  ),
}))

import ReflectionScreen from './ReflectionScreen'

const navigation = { goBack: () => {} }

describe('ReflectionScreen', () => {
  it('renders the fetched content and stat pills', async () => {
    const screen = await render(
      <NavigationContainer>
        <ReflectionScreen navigation={navigation} />
      </NavigationContainer>,
    )

    await waitFor(() => {
      expect(
        screen.getByText('You called mom and finished the report. The gym session is still open.'),
      ).toBeTruthy()
      expect(screen.getByText('2 done')).toBeTruthy()
      expect(screen.getByText('1 still open')).toBeTruthy()
    })
  })
})
