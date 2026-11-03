import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MediaItem } from '../types'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('axios', () => ({
  default: {
    create: () => ({
      get,
      post: vi.fn(),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    }),
  },
}))

import { mediaApi } from './api'

const items = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => ({ id: from + i }) as MediaItem)

describe('mediaApi.getAll', () => {
  beforeEach(() => get.mockReset())

  it('pages past the backend default of 50 instead of losing the oldest items', async () => {
    get.mockResolvedValueOnce({ data: items(1, 200) }).mockResolvedValueOnce({ data: items(201, 230) })

    const all = await mediaApi.getAll()

    expect(all).toHaveLength(230)
    expect(get.mock.calls.map((c) => c[1].params)).toEqual([
      { limit: 200, offset: 0 },
      { limit: 200, offset: 200 },
    ])
  })

  it('never returns an item twice when an upload shifts the pages', async () => {
    get.mockResolvedValueOnce({ data: items(1, 200) }).mockResolvedValueOnce({ data: items(200, 205) })

    const all = await mediaApi.getAll()

    expect(all.map((m) => m.id)).toEqual(items(1, 205).map((m) => m.id))
  })

  it('keeps the event filter on every page', async () => {
    get.mockResolvedValueOnce({ data: items(1, 3) })

    await mediaApi.getAll(7)

    expect(get).toHaveBeenCalledWith('/media/', { params: { limit: 200, offset: 0, event_id: 7 } })
  })
})

describe('mediaApi.getRecent', () => {
  it('asks the backend for just what the Hub shows', async () => {
    get.mockReset().mockResolvedValueOnce({ data: items(1, 8) })

    expect(await mediaApi.getRecent(8)).toHaveLength(8)
    expect(get).toHaveBeenCalledWith('/media/', { params: { limit: 8 } })
  })
})
