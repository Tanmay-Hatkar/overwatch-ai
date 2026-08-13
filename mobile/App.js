import { useEffect } from 'react'
import { ActivityIndicator, StyleSheet, View } from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { NavigationContainer, DefaultTheme } from '@react-navigation/native'
import { createNativeStackNavigator } from '@react-navigation/native-stack'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { AuthProvider, useAuth } from './src/contexts/AuthContext'
import LoginScreen from './src/screens/LoginScreen'
import TodoListScreen from './src/screens/TodoListScreen'
import ChatScreen from './src/screens/ChatScreen'
import BriefingScreen from './src/screens/BriefingScreen'
import ReflectionScreen from './src/screens/ReflectionScreen'
import { ensureNotificationPermission, initNotificationActions } from './src/lib/notifications'
import { initRingActionListener } from './src/lib/ringAlarm'
import { color } from './src/theme'

const darkTheme = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, background: color.background },
}

const Stack = createNativeStackNavigator()

function Root() {
  const { user, loading } = useAuth()

  // Register the Snooze/Done response listener + ask for permission once
  // signed in. Best-effort: notifications never block the rest of the app.
  useEffect(() => {
    if (!user) return
    let unsubscribe
    ensureNotificationPermission()
    initNotificationActions().then((unsub) => {
      unsubscribe = unsub
    })
    const unsubscribeRing = initRingActionListener()
    return () => {
      unsubscribe?.()
      unsubscribeRing?.()
    }
  }, [user])

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={color.accent} />
      </View>
    )
  }

  if (!user) return <LoginScreen />

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Todos" component={TodoListScreen} />
      <Stack.Screen name="Chat" component={ChatScreen} options={{ animation: 'slide_from_bottom' }} />
      <Stack.Screen name="Briefing" component={BriefingScreen} options={{ animation: 'slide_from_bottom' }} />
      <Stack.Screen name="Reflection" component={ReflectionScreen} options={{ animation: 'slide_from_bottom' }} />
    </Stack.Navigator>
  )
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <NavigationContainer theme={darkTheme}>
          <StatusBar style="light" />
          <Root />
        </NavigationContainer>
      </AuthProvider>
    </SafeAreaProvider>
  )
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: color.background, alignItems: 'center', justifyContent: 'center' },
})
