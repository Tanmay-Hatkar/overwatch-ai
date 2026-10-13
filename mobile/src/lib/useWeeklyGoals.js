import { useCallback, useState } from 'react'
import { Alert } from 'react-native'
import {
  createGoal,
  decideGoalWeek,
  deleteGoal,
  listGoals,
  logGoal,
  undoGoalLog,
  updateGoal,
} from '../api'
import { withOptimisticLog } from './goals'

/**
 * State + actions for weekly goals on the home screen (ADR-0026), kept out
 * of TodoListScreen so the screen only renders. Every mutation replaces
 * the goal with the server's answer, since the server owns the week state.
 *
 * Goals failing to load never blocks the todo list: the section just stays
 * empty until the next refresh.
 */
export function useWeeklyGoals() {
  const [goals, setGoals] = useState([])

  const replace = useCallback((updated) => {
    setGoals((prev) => prev.map((g) => (g.id === updated.id ? updated : g)))
  }, [])

  const load = useCallback(async () => {
    try {
      setGoals(await listGoals())
    } catch {
      // Best-effort: todos still render; pull-to-refresh retries.
    }
  }, [])

  // Runs a server call; on failure tells the user and reloads the truth.
  const attempt = useCallback(
    async (title, fn) => {
      try {
        return await fn()
      } catch (err) {
        Alert.alert(title, err.message || 'Try again.')
        load()
        return null
      }
    },
    [load],
  )

  const log = useCallback(
    async (goal) => {
      replace(withOptimisticLog(goal))
      const updated = await attempt("Couldn't log that", () => logGoal(goal.id))
      if (updated) replace(updated)
    },
    [attempt, replace],
  )

  const undo = useCallback(
    async (goal) => {
      const updated = await attempt("Couldn't undo", () => undoGoalLog(goal.id))
      if (updated) replace(updated)
    },
    [attempt, replace],
  )

  const decide = useCallback(
    async (goal, decision) => {
      const updated = await attempt("Couldn't save that", () => decideGoalWeek(goal.id, decision))
      if (updated) replace(updated)
    },
    [attempt, replace],
  )

  const save = useCallback(
    async (existing, fields) => {
      const updated = await attempt("Couldn't save goal", () =>
        existing ? updateGoal(existing.id, fields) : createGoal(fields),
      )
      if (!updated) return
      if (existing) replace(updated)
      else setGoals((prev) => [...prev, updated])
    },
    [attempt, replace],
  )

  const remove = useCallback(
    async (goal) => {
      setGoals((prev) => prev.filter((g) => g.id !== goal.id))
      await attempt("Couldn't delete goal", () => deleteGoal(goal.id))
    },
    [attempt],
  )

  return { goals, load, log, undo, decide, save, remove }
}
