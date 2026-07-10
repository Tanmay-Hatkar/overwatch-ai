/**
 * setup.js — Vitest global setup, loaded via vite.config.js's test.setupFiles.
 *
 * Registers jest-dom's DOM matchers (toBeInTheDocument, etc.) for every
 * test file so individual tests don't need to import them.
 */
import '@testing-library/jest-dom/vitest'
