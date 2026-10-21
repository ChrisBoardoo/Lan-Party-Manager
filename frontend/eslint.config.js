// ESLint, flat config (1.4.1 — F-10 of the 2026-10-20 review). Three things it
// is here for: the rules of hooks (two pages returned before their hooks and
// nothing said so), unused code, and accessibility as warnings while the
// backlog (labels without htmlFor, icon buttons without a name) is worked off.
// `tsc` keeps the typing job; this doesn't type-check.
import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import globals from 'globals'

const warnAll = (rules) => Object.fromEntries(Object.keys(rules).map((name) => [name, 'warn']))

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'public/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser, ...globals.es2021 } },
    plugins: { 'react-hooks': reactHooks, 'jsx-a11y': jsxA11y },
    rules: {
      // Errors: what breaks at runtime or hides a bug.
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // Warnings for now: real, but 20+ sites each; fixed as pages are touched.
      ...warnAll(jsxA11y.flatConfigs.recommended.rules),
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // The code base uses `{}`-style empty catch blocks on purpose for optional loads.
      'no-empty': ['warn', { allowEmptyCatch: true }],
    },
  },
  {
    files: ['vite.config.ts', 'tailwind.config.js', 'postcss.config.js', 'eslint.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
)
