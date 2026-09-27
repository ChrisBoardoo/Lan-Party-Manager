import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Gamepad2, Plus, Trash2, Check, X, Users, Download, Star, RotateCcw } from 'lucide-react'
import { gamesApi } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import {
  DEFAULT_LIBRARY_FILTERS, applyLibraryFilters, hasActiveFilters, parsePlayerBound,
} from '../lib/gameLibraryFilters'
import type { Game, GameLibraryEntry, GameLibraryFilters, GameWishlistEntry, GameImportResult } from '../types'
import SearchSelect, { SearchSelectOption } from './ui/SearchSelect'
import Button from './ui/Button'

// The profile "Games" section: a library (owned, with a max-player count) and a
// wishlist (wanted), both searched against the shared catalog with a fallback to
// add a custom title. Self-contained (own fetch, own catch) like MySetupCard/
// GearSection, so a disabled or failing feature never takes the rest of Profile
// down with it — Profile.tsx only decides *whether* to render this at all.
//
// The filter bar is saved on the account (PUT /games/me/filters), so it
// survives a reload and follows the member into the desktop app: loaded once
// with the lists, then saved shortly after each change.
const FILTERS_SAVE_DELAY_MS = 500

// Compared field by field, so the key doesn't depend on the order the API
// happens to return the fields in.
const filtersKey = (f: GameLibraryFilters) =>
  JSON.stringify([f.sort, f.min_players, f.max_players, f.playable_only, f.favorites_only])

export default function GamesLibraryCard() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [catalog, setCatalog] = useState<Game[]>([])
  const [library, setLibrary] = useState<GameLibraryEntry[]>([])
  const [wishlist, setWishlist] = useState<GameWishlistEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [libName, setLibName] = useState('')
  const [libMax, setLibMax] = useState('')
  const [wishName, setWishName] = useState('')

  const [editingMaxFor, setEditingMaxFor] = useState<number | null>(null)
  const [maxDraft, setMaxDraft] = useState('')

  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<GameImportResult | null>(null)

  const [sortDir, setSortDir] = useState<'asc' | 'desc' | null>(null)
  const [minPlayersFilter, setMinPlayersFilter] = useState('')
  const [maxPlayersFilter, setMaxPlayersFilter] = useState('')
  const [playableOnly, setPlayableOnly] = useState(false)
  const [favoritesOnly, setFavoritesOnly] = useState(false)

  // Whether the saved filters were loaded, what the server holds, and a change
  // not sent yet. Refs, not state: none of them should re-render anything, and
  // the unmount flush needs them.
  const filtersLoaded = useRef(false)
  const savedFiltersKey = useRef('')
  const pendingFilters = useRef<GameLibraryFilters | null>(null)

  // Reloads both the catalog and my lists — a custom addition creates a new
  // catalog row, so the autocomplete needs to see it too (e.g. adding the same
  // custom title to both the library and the wishlist in one sitting).
  const load = () => {
    gamesApi.catalog().then(setCatalog).catch(() => setCatalog([]))
    gamesApi.getMe()
      .then((me) => { setLibrary(me.library); setWishlist(me.wishlist) })
      .catch(() => { setLibrary([]); setWishlist([]) })
  }

  // Filters are only restored here, on first load — `load()` runs after every
  // edit and must not snap the bar back while the member is using it.
  useEffect(() => {
    setLoading(true)
    Promise.all([
      gamesApi.catalog().then(setCatalog).catch(() => setCatalog([])),
      gamesApi.getMe()
        .then((me) => {
          setLibrary(me.library)
          setWishlist(me.wishlist)
          // `??`: a backend older than this card sends no filters — that must
          // not throw into the catch below and blank the library.
          const f = me.filters ?? DEFAULT_LIBRARY_FILTERS
          setSortDir(f.sort)
          setMinPlayersFilter(f.min_players != null ? String(f.min_players) : '')
          setMaxPlayersFilter(f.max_players != null ? String(f.max_players) : '')
          setPlayableOnly(f.playable_only)
          setFavoritesOnly(f.favorites_only)
          savedFiltersKey.current = filtersKey(f)
          filtersLoaded.current = true
        })
        .catch(() => { setLibrary([]); setWishlist([]) }),
    ]).finally(() => setLoading(false))
  }, [])

  const filters: GameLibraryFilters = useMemo(() => ({
    sort: sortDir,
    min_players: parsePlayerBound(minPlayersFilter),
    max_players: parsePlayerBound(maxPlayersFilter),
    playable_only: playableOnly,
    favorites_only: favoritesOnly,
  }), [sortDir, minPlayersFilter, maxPlayersFilter, playableOnly, favoritesOnly])

  const flushFilters = useCallback(() => {
    const next = pendingFilters.current
    if (!next) return
    pendingFilters.current = null
    savedFiltersKey.current = filtersKey(next)
    // A lost save only costs the preference, never the page — forget what we
    // thought was saved so the next change retries.
    gamesApi.saveFilters(next).catch(() => { savedFiltersKey.current = '' })
  }, [])

  // Debounced so typing "12" in a player-count box is one save, not two. Until
  // the saved filters are loaded nothing is saved at all — the defaults the bar
  // starts with must never overwrite what the member saved, and if that load
  // fails the bar just works unsaved for this visit.
  useEffect(() => {
    if (!filtersLoaded.current) return
    if (filtersKey(filters) === savedFiltersKey.current) {
      pendingFilters.current = null
      return
    }
    pendingFilters.current = filters
    const timer = setTimeout(flushFilters, FILTERS_SAVE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [filters, flushFilters])

  // Leaving the profile right after a change still saves it.
  useEffect(() => flushFilters, [flushFilters])

  const resetFilters = () => {
    setSortDir(null)
    setMinPlayersFilter('')
    setMaxPlayersFilter('')
    setPlayableOnly(false)
    setFavoritesOnly(false)
  }

  const catalogOptions: SearchSelectOption[] = useMemo(
    () => catalog.map((g) => ({ id: g.id, label: g.name, sublabel: g.genre ?? undefined })),
    [catalog],
  )

  // Client-side only — the library is per-user and rarely large enough to need
  // a server round-trip, and this keeps the filters instant as they're tweaked.
  const displayedLibrary = useMemo(() => applyLibraryFilters(library, filters), [library, filters])

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try { await fn(); load() } finally { setBusy(false) }
  }

  const addToLibrary = () => {
    if (!libName.trim()) return
    run(async () => {
      await gamesApi.addToLibrary({
        name: libName.trim(),
        max_players_override: libMax.trim() ? parseInt(libMax, 10) : null,
      })
      setLibName(''); setLibMax('')
    })
  }

  const handleLibSelect = (opt: SearchSelectOption) => {
    setLibName(opt.label)
    const g = catalog.find((c) => c.id === opt.id)
    if (g?.default_max_players) setLibMax(String(g.default_max_players))
  }

  const addToWishlist = () => {
    if (!wishName.trim()) return
    run(async () => {
      await gamesApi.addToWishlist({ name: wishName.trim() })
      setWishName('')
    })
  }

  // Optimistic: the star flips at once and flips back if the save fails —
  // reloading the whole card for a toggle would feel sluggish.
  const toggleFavorite = async (row: GameLibraryEntry) => {
    const next = !row.is_favorite
    const setStar = (value: boolean) =>
      setLibrary((rows) => rows.map((r) => (r.game_id === row.game_id ? { ...r, is_favorite: value } : r)))
    setStar(next)
    try {
      await gamesApi.setFavorite(row.game_id, next)
    } catch {
      setStar(!next)
    }
  }

  const startEditMax = (row: GameLibraryEntry) => {
    setEditingMaxFor(row.game_id)
    setMaxDraft(row.max_players != null ? String(row.max_players) : '')
  }

  const saveMax = (gameId: number) => {
    const value = maxDraft.trim() ? parseInt(maxDraft, 10) : null
    run(async () => {
      await gamesApi.updateLibraryEntry(gameId, { max_players_override: value })
      setEditingMaxFor(null)
    })
  }

  const importFromSteam = async () => {
    setImporting(true)
    setImportResult(null)
    try {
      const result = await gamesApi.importSteam()
      setImportResult(result)
      if (result.games_visible) load()
    } finally {
      setImporting(false)
    }
  }

  if (loading) return null

  return (
    <section className="mt-8 border border-border bg-card p-6">
      <p className="font-mono-label text-accent flex items-center gap-1.5 mb-6">
        <Gamepad2 size={12} strokeWidth={1.5} /> {t('games.sectionTitle')}
      </p>

      {/* Library */}
      <div className="mb-8">
        <div className="flex items-center justify-between gap-3 mb-1">
          <p className="text-sm font-medium text-foreground">{t('games.libraryTitle')}</p>
          {user?.steam_username && (
            <Button size="sm" variant="outline" onClick={importFromSteam} disabled={importing}>
              <Download size={13} /> {importing ? t('common.loading') : t('games.importSteamButton')}
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-3">{t('games.libraryHint')}</p>

        {importResult && (
          importResult.games_visible ? (
            <p className="text-xs text-muted-foreground mb-3">
              {t('games.importSteamSummary', {
                imported: importResult.imported,
                already: importResult.already_owned,
              })}
            </p>
          ) : (
            <p className="text-xs text-red-400 mb-3">{t('games.importSteamPrivate')}</p>
          )
        )}

        {library.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 mb-3">
            <div className="flex items-center gap-1">
              <span className="font-mono-label text-[10px] text-muted-foreground">{t('games.sortLabel')}</span>
              <button
                onClick={() => setSortDir(sortDir === 'asc' ? null : 'asc')}
                title={t('games.sortAscLabel')}
                className={`px-2 py-1 border font-mono-label text-xs transition-colors ${
                  sortDir === 'asc' ? 'border-accent bg-accent text-accent-foreground' : 'border-border text-muted-foreground hover:border-border-hover'
                }`}
              >
                A→Z
              </button>
              <button
                onClick={() => setSortDir(sortDir === 'desc' ? null : 'desc')}
                title={t('games.sortDescLabel')}
                className={`px-2 py-1 border font-mono-label text-xs transition-colors ${
                  sortDir === 'desc' ? 'border-accent bg-accent text-accent-foreground' : 'border-border text-muted-foreground hover:border-border-hover'
                }`}
              >
                Z→A
              </button>
            </div>

            <div className="flex items-center gap-1">
              <Users size={12} className="text-muted-foreground" />
              <input
                type="number" min={1} max={999}
                value={minPlayersFilter}
                onChange={(e) => setMinPlayersFilter(e.target.value)}
                placeholder={t('games.minPlayersPlaceholder')}
                className="w-14 bg-muted border border-border px-2 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
              />
              <span className="text-muted-foreground text-xs">–</span>
              <input
                type="number" min={1} max={999}
                value={maxPlayersFilter}
                onChange={(e) => setMaxPlayersFilter(e.target.value)}
                placeholder={t('games.maxPlayersPlaceholder')}
                className="w-14 bg-muted border border-border px-2 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
              />
            </div>

            <label className="flex items-center gap-1.5 cursor-pointer text-xs text-muted-foreground" title={t('games.playableOnlyHint')}>
              <input
                type="checkbox"
                checked={playableOnly}
                onChange={(e) => setPlayableOnly(e.target.checked)}
                className="accent-accent"
              />
              {t('games.playableOnlyLabel')}
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer text-xs text-muted-foreground" title={t('games.favoritesOnlyHint')}>
              <input
                type="checkbox"
                checked={favoritesOnly}
                onChange={(e) => setFavoritesOnly(e.target.checked)}
                className="accent-accent"
              />
              {t('games.favoritesOnlyLabel')}
            </label>

            {hasActiveFilters(filters) && (
              <button
                onClick={resetFilters}
                className="flex items-center gap-1 font-mono-label text-xs text-muted-foreground hover:text-foreground"
              >
                <RotateCcw size={12} /> {t('games.resetFilters')}
              </button>
            )}
          </div>
        )}

        <div className="border border-border bg-background">
          {library.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">{t('games.libraryEmpty')}</p>
          ) : displayedLibrary.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">{t('games.libraryFilterEmpty')}</p>
          ) : (
            displayedLibrary.map((row) => (
              <div key={row.game_id} className="flex items-center justify-between px-4 py-3 border-b border-border last:border-0">
                <div className="min-w-0">
                  <span className="text-sm font-medium text-foreground">{row.name}</span>
                  {row.genre && (
                    <span className="ml-2 font-mono-label text-[10px] text-muted-foreground">{row.genre}</span>
                  )}
                  {row.is_custom && (
                    <span className="ml-2 font-mono-label text-[10px] text-accent">{t('games.customBadge')}</span>
                  )}
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <button
                    onClick={() => toggleFavorite(row)}
                    title={t(row.is_favorite ? 'games.favoriteRemove' : 'games.favoriteAdd')}
                    aria-pressed={row.is_favorite}
                    className={row.is_favorite ? 'text-accent hover:text-foreground' : 'text-muted-foreground hover:text-accent'}
                  >
                    <Star size={13} fill={row.is_favorite ? 'currentColor' : 'none'} />
                  </button>
                  {editingMaxFor === row.game_id ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="number" min={1} max={999} autoFocus
                        value={maxDraft}
                        onChange={(e) => setMaxDraft(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && saveMax(row.game_id)}
                        className="w-16 bg-muted border border-border px-2 py-1 text-sm text-foreground focus:border-accent outline-none"
                      />
                      <button onClick={() => saveMax(row.game_id)} disabled={busy} className="text-muted-foreground hover:text-accent">
                        <Check size={13} />
                      </button>
                      <button onClick={() => setEditingMaxFor(null)} className="text-muted-foreground hover:text-foreground">
                        <X size={13} />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => startEditMax(row)}
                      title={t('games.maxPlayersLabel')}
                      className="font-mono-label text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                    >
                      <Users size={12} /> {row.max_players ?? '—'}
                    </button>
                  )}
                  <button
                    onClick={() => run(() => gamesApi.removeFromLibrary(row.game_id))}
                    disabled={busy}
                    className="text-muted-foreground hover:text-red-400"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <SearchSelect
            className="flex-1 min-w-[200px]"
            options={catalogOptions}
            value={libName}
            onChange={setLibName}
            onSelect={handleLibSelect}
            onAddCustom={(text) => setLibName(text)}
            addLabel={(text) => t('games.addCustom', { name: text })}
            placeholder={t('games.namePlaceholder')}
          />
          <input
            type="number" min={1} max={999}
            value={libMax}
            onChange={(e) => setLibMax(e.target.value)}
            placeholder={t('games.maxPlayersPlaceholder')}
            className="w-24 bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
          />
          <Button size="sm" onClick={addToLibrary} disabled={busy || !libName.trim()}>
            <Plus size={13} /> {t('games.addButton')}
          </Button>
        </div>
      </div>

      {/* Wishlist */}
      <div>
        <p className="text-sm font-medium text-foreground mb-1">{t('games.wishlistTitle')}</p>
        <p className="text-xs text-muted-foreground mb-3">{t('games.wishlistHint')}</p>

        <div className="border border-border bg-background">
          {wishlist.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">{t('games.wishlistEmpty')}</p>
          ) : (
            wishlist.map((row) => (
              <div key={row.game_id} className="flex items-center justify-between px-4 py-3 border-b border-border last:border-0">
                <div className="min-w-0">
                  <span className="text-sm font-medium text-foreground">{row.name}</span>
                  {row.genre && (
                    <span className="ml-2 font-mono-label text-[10px] text-muted-foreground">{row.genre}</span>
                  )}
                </div>
                <button
                  onClick={() => run(() => gamesApi.removeFromWishlist(row.game_id))}
                  disabled={busy}
                  className="text-muted-foreground hover:text-red-400 flex-shrink-0"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <SearchSelect
            className="flex-1 min-w-[200px]"
            options={catalogOptions}
            value={wishName}
            onChange={setWishName}
            onSelect={(opt) => setWishName(opt.label)}
            onAddCustom={(text) => setWishName(text)}
            addLabel={(text) => t('games.addCustom', { name: text })}
            placeholder={t('games.namePlaceholder')}
          />
          <Button size="sm" onClick={addToWishlist} disabled={busy || !wishName.trim()}>
            <Plus size={13} /> {t('games.addButton')}
          </Button>
        </div>
      </div>
    </section>
  )
}
