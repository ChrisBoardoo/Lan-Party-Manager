import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// vitest.config's `test.globals` is left off (matches the rest of the repo's
// explicit-import style), so @testing-library/react's usual auto-cleanup
// (which hooks the `afterEach` *global*) never fires on its own — without
// this, every test's rendered output piles up in the same jsdom `document`
// and later tests see earlier tests' elements too.
afterEach(() => {
  cleanup()
})
