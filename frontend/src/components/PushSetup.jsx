import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { sendTestPush } from '../api'
import { disablePush, enablePush, getCurrentSubscription, isPushSupported } from '../lib/push'

/**
 * PushSetup — small inline UI to enable / disable / test Web Push.
 *
 * States (in priority order):
 *   - unsupported:   browser can't do Web Push → render nothing
 *   - denied:        user blocked notifications → render help text
 *   - subscribed:    already enabled → "send test push" + "turn off" links
 *   - default:       not subscribed yet → "Enable push reminders" button
 *
 * Web Push fires even when the tab is closed, unlike the in-tab reminders
 * hook. This is the "follow you off-tab" mechanic.
 */
export default function PushSetup() {
  const [supported, setSupported] = useState(false)
  const [permission, setPermission] = useState('default')
  const [hasSubscription, setHasSubscription] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function init() {
      const sup = isPushSupported()
      if (!sup) {
        if (!cancelled) setSupported(false)
        return
      }
      if (!cancelled) {
        setSupported(true)
        setPermission(Notification.permission)
      }
      try {
        const sub = await getCurrentSubscription()
        if (!cancelled) setHasSubscription(sub !== null)
      } catch {
        if (!cancelled) setHasSubscription(false)
      }
    }
    init()
    return () => {
      cancelled = true
    }
  }, [])

  async function handleEnable() {
    setBusy(true)
    try {
      await enablePush()
      setHasSubscription(true)
      setPermission('granted')
      toast.success('Push reminders enabled.')
    } catch (err) {
      toast.error(err.message || 'Could not enable push.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDisable() {
    setBusy(true)
    try {
      await disablePush()
      setHasSubscription(false)
      toast.success('Push reminders turned off.')
    } catch (err) {
      toast.error(err.message || 'Could not turn off push.')
    } finally {
      setBusy(false)
    }
  }

  async function handleTest() {
    setBusy(true)
    try {
      const result = await sendTestPush()
      toast.success(`Test push sent to ${result.delivered} device(s).`)
    } catch (err) {
      toast.error(err.message || 'Test push failed.')
    } finally {
      setBusy(false)
    }
  }

  if (!supported) return null

  if (permission === 'denied') {
    return (
      <p className="text-[11px] text-zinc-600 mb-3">
        Push reminders blocked by browser. Click the lock icon in the address bar to allow notifications.
      </p>
    )
  }

  if (hasSubscription) {
    return (
      <div className="mb-3 flex items-center gap-3 text-[11px] text-zinc-500">
        <span>Push reminders enabled.</span>
        <button
          onClick={handleTest}
          disabled={busy}
          className="text-orange-500 hover:underline disabled:opacity-50"
        >
          send test
        </button>
        <button
          onClick={handleDisable}
          disabled={busy}
          className="text-zinc-600 hover:text-red-500 disabled:opacity-50"
        >
          turn off
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={handleEnable}
      disabled={busy}
      className="mb-3 text-[11px] text-zinc-500 hover:text-orange-500 transition-colors disabled:opacity-50"
    >
      {busy ? 'Enabling…' : 'Enable push reminders (fires even when tab closed) →'}
    </button>
  )
}
