import { ActivityIndicator, StyleSheet, View } from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { NavigationContainer, DefaultTheme } from '@react-navigation/native'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { AuthProvider, useAuth } from './src/contexts/AuthContext'
import LoginScreen from './src/screens/LoginScreen'
import TodoListScreen from './src/screens/TodoListScreen'
import { color } from './src/theme'

const darkTheme = {
  ...DefaultTheme,
  colors: { ...DefaultTheme.colors, background: color.background },
}

function Root() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={color.accent} />
      </View>
    )
  }

  return user ? <TodoListScreen /> : <LoginScreen />
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
