import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'android', 'ios', '.expo']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      react.configs.flat.recommended,
      react.configs.flat['jsx-runtime'], // automatic JSX runtime — no `import React` needed
      reactHooks.configs['recommended-latest'],
    ],
    languageOptions: {
      ...react.configs.flat.recommended.languageOptions,
      globals: { ...globals.node, __DEV__: 'readonly', fetch: 'readonly' },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    rules: {
      // This project (matching frontend/'s existing convention) uses plain
      // duck-typed JS components — no prop-types package, no TypeScript.
      'react/prop-types': 'off',
      // Raw apostrophes in JSX text are common and safe; escaping them
      // (&apos;) only hurts readability for zero functional benefit.
      'react/no-unescaped-entities': 'off',
    },
  },
])
