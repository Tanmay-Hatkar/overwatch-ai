/**
 * BriefingScreen.test.js — one scenario per file deliberately; see
 * chatScreenTestUtils.js for why (react-test-renderer container reuse
 * across successive render() calls in one file doesn't work cleanly in
 * this environment).
 */
import { describe, it, expect, jest } from '@jest/globals'
import { render, waitFor } from '@testing-library/react-native'
import { NavigationContainer } from '@react-navigation/native'

jest.mock('../api', () => ({
  getMorningBriefing: jest.fn(() =>
    Promise.resolve({
      content: 'You have two things today — the standup at 9:30 and the Vosyn report by 5pm.',
      today_count: 2,
      overdue_count: 1,
      floating_count: 0,
      cached: false,
    }),
  ),
}))

import BriefingScreen from './BriefingScreen'

const navigation = { goBack: () => {} }

describe('BriefingScreen', () => {
  it('renders the fetched content and stat pills', async () => {
    const screen = await render(
      <NavigationContainer>
        <BriefingScreen navigation={navigation} />
      </NavigationContainer>,
    )

    await waitFor(() => {
      expect(
        screen.getByText('You have two things today — the standup at 9:30 and the Vosyn report by 5pm.'),
      ).toBeTruthy()
      expect(screen.getByText('2 today')).toBeTruthy()
      expect(screen.getByText('1 overdue')).toBeTruthy()
    })
  })
})
