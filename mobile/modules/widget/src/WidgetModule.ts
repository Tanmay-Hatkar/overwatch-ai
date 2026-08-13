import { NativeModule, requireNativeModule } from 'expo'

declare class WidgetModule extends NativeModule<{}> {
  configure(baseUrl: string, token: string): Promise<void>
  clear(): Promise<void>
  refreshNow(): Promise<void>
}

export default requireNativeModule<WidgetModule>('Widget')
