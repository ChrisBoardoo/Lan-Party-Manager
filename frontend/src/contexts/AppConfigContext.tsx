import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { DEFAULT_CHAT_RULES, type ChatWindowRules } from '../lib/eventDates'
import { settingsApi } from '../lib/api'
import { useAuth } from './AuthContext'

// Currency symbols the admin can pick from — keep in sync with the backend
// ALLOWED_CURRENCIES set in router_settings.py.
export const CURRENCIES = ['€', '$', '£'] as const
export const DEFAULT_CURRENCY = '€'

interface AppConfigContextType {
  currency: string
  treasuryEnabled: boolean
  sponsorsEnabled: boolean
  prizesEnabled: boolean
  planningEnabled: boolean
  gearEnabled: boolean
  groceriesEnabled: boolean
  recapEnabled: boolean
  setupEnabled: boolean
  streamsEnabled: boolean
  checklistEnabled: boolean
  merchSizeEnabled: boolean
  minigamesEnabled: boolean
  gamesEnabled: boolean
  cravingChatEnabled: boolean
  chatRules: ChatWindowRules
  trophiesEnabled: boolean
  lolStatsEnabled: boolean
  xpEnabled: boolean
  /** The monthly contract: on only with XP on (the server checks both). */
  questsEnabled: boolean
  cardsEnabled: boolean
  /** False until the first /public-config response lands. Route guards for opt-in
   *  features must wait for this: their flags start false, so deciding before the
   *  config arrives bounces a legitimate deep link straight back to the hub. */
  configLoaded: boolean
  refreshConfig: () => Promise<void>
}

const AppConfigContext = createContext<AppConfigContextType | null>(null)

export function AppConfigProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [currency, setCurrency] = useState(DEFAULT_CURRENCY)
  // Treasury/Live default on (admin opts out); Sponsors/Prizes/Planning default off (opt-in).
  const [treasuryEnabled, setTreasuryEnabled] = useState(true)
  const [sponsorsEnabled, setSponsorsEnabled] = useState(false)
  const [prizesEnabled, setPrizesEnabled] = useState(false)
  const [planningEnabled, setPlanningEnabled] = useState(false)
  const [gearEnabled, setGearEnabled] = useState(false)
  const [groceriesEnabled, setGroceriesEnabled] = useState(false)
  const [recapEnabled, setRecapEnabled] = useState(false)
  const [setupEnabled, setSetupEnabled] = useState(false)
  const [streamsEnabled, setStreamsEnabled] = useState(true)
  const [checklistEnabled, setChecklistEnabled] = useState(false)
  const [merchSizeEnabled, setMerchSizeEnabled] = useState(true)
  const [minigamesEnabled, setMinigamesEnabled] = useState(false)
  const [gamesEnabled, setGamesEnabled] = useState(false)
  const [cravingChatEnabled, setCravingChatEnabled] = useState(true)
  const [chatRules, setChatRules] = useState<ChatWindowRules>(DEFAULT_CHAT_RULES)
  const [trophiesEnabled, setTrophiesEnabled] = useState(false)
  const [lolStatsEnabled, setLolStatsEnabled] = useState(false)
  const [xpEnabled, setXpEnabled] = useState(false)
  const [questsEnabled, setQuestsEnabled] = useState(false)
  const [cardsEnabled, setCardsEnabled] = useState(false)
  const [configLoaded, setConfigLoaded] = useState(false)

  const refreshConfig = useCallback(async () => {
    try {
      const data = await settingsApi.getPublicConfig()
      setCurrency(data.currency || DEFAULT_CURRENCY)
      setTreasuryEnabled(data.treasury_enabled)
      setSponsorsEnabled(data.sponsors_enabled)
      setPrizesEnabled(data.prizes_enabled)
      setPlanningEnabled(data.planning_enabled)
      setGearEnabled(data.gear_enabled)
      setGroceriesEnabled(data.groceries_enabled)
      setRecapEnabled(data.recap_enabled)
      setSetupEnabled(data.setup_enabled)
      setStreamsEnabled(data.streams_enabled)
      setChecklistEnabled(data.checklist_enabled)
      setMerchSizeEnabled(data.merch_size_enabled)
      setMinigamesEnabled(data.minigames_enabled)
      setGamesEnabled(data.games_enabled)
      setCravingChatEnabled(data.craving_chat_enabled)
      setChatRules({
        daysBefore: data.craving_chat_open_days_before ?? DEFAULT_CHAT_RULES.daysBefore,
        daysAfter: data.craving_chat_close_days_after ?? DEFAULT_CHAT_RULES.daysAfter,
        alwaysOpen: !!data.craving_chat_always_open,
      })
      setTrophiesEnabled(data.trophies_enabled)
      setLolStatsEnabled(data.lol_stats_enabled)
      setXpEnabled(data.xp_enabled)
      setQuestsEnabled(!!data.quests_enabled)
      setCardsEnabled(data.cards_enabled)
    } catch {
      setCurrency(DEFAULT_CURRENCY)
      setTreasuryEnabled(true)
      setSponsorsEnabled(false)
      setPrizesEnabled(false)
      setPlanningEnabled(false)
      setGearEnabled(false)
      setGroceriesEnabled(false)
      setRecapEnabled(false)
      setSetupEnabled(false)
      setStreamsEnabled(true)
      setChecklistEnabled(false)
      setMerchSizeEnabled(true)
      setMinigamesEnabled(false)
      setGamesEnabled(false)
      setCravingChatEnabled(true)
      setTrophiesEnabled(false)
      setLolStatsEnabled(false)
      setXpEnabled(false)
      setQuestsEnabled(false)
      setCardsEnabled(false)
    } finally {
      // Set even on failure: a guard that waits forever is worse than one that
      // falls back to defaults and lets the user move.
      setConfigLoaded(true)
    }
  }, [])

  // The endpoint requires an authenticated user, so (re)load whenever the
  // logged-in user changes. Falls back to defaults on the login screen.
  useEffect(() => {
    if (user) refreshConfig()
  }, [user, refreshConfig])

  return (
    <AppConfigContext.Provider value={{ currency, treasuryEnabled, sponsorsEnabled, prizesEnabled, planningEnabled, gearEnabled, groceriesEnabled, recapEnabled, setupEnabled, streamsEnabled, checklistEnabled, merchSizeEnabled, minigamesEnabled, gamesEnabled, cravingChatEnabled, chatRules, trophiesEnabled, lolStatsEnabled, xpEnabled, questsEnabled, cardsEnabled, configLoaded, refreshConfig }}>
      {children}
    </AppConfigContext.Provider>
  )
}

export const useAppConfig = () => {
  const ctx = useContext(AppConfigContext)
  if (!ctx) throw new Error('useAppConfig must be inside AppConfigProvider')
  return ctx
}
