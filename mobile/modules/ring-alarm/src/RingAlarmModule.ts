import { NativeModule, requireNativeModule } from 'expo'

import { RingActionEvent, RingAlarmModuleEvents } from './RingAlarm.types'

declare class RingAlarmModule extends NativeModule<RingAlarmModuleEvents> {
  ring(
    id: number,
    commitmentId: string,
    title: string,
    body: string,
    atMillis: number
  ): Promise<void>
  cancelRing(id: number): Promise<void>
  checkFullScreenIntentPermission(): Promise<boolean>
  openFullScreenIntentSettings(): Promise<void>
  drainPendingRingActions(): Promise<RingActionEvent[]>
}

export default requireNativeModule<RingAlarmModule>('RingAlarm')
