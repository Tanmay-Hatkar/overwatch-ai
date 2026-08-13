import { NativeModule, registerWebModule } from 'expo'

/** Home-screen widgets have no web equivalent -- every call is a no-op. */
class WidgetModule extends NativeModule<{}> {
  async configure(): Promise<void> {}
  async clear(): Promise<void> {}
  async refreshNow(): Promise<void> {}
}

export default registerWebModule(WidgetModule, 'WidgetModule')
