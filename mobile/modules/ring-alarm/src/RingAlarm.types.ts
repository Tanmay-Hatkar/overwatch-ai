export type RingActionEvent = {
  id: number
  commitmentId: string
  action: string
}

export type RingAlarmModuleEvents = {
  ringAction: (event: RingActionEvent) => void
}
