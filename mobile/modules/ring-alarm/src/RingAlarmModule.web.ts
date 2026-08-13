import { NativeModule, registerWebModule } from 'expo'

import { RingActionEvent, RingAlarmModuleEvents } from './RingAlarm.types'

/** No web equivalent of a full-screen-intent alarm exists — every call is a no-op. */
class RingAlarmModule extends NativeModule<RingAlarmModuleEvents> {
  async ring(): Promise<void> {}
  async cancelRing(): Promise<void> {}
  async checkFullScreenIntentPermission(): Promise<boolean> {
    return true
  }
  async openFullScreenIntentSettings(): Promise<void> {}
  async drainPendingRingActions(): Promise<RingActionEvent[]> {
    return []
  }
}

export default registerWebModule(RingAlarmModule, 'RingAlarmModule')
