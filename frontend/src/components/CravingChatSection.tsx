import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Send, Smile, ChevronDown, X, CornerUpLeft, Pencil, Trash2, Pin, PinOff, Search } from 'lucide-react'
import { chatApi } from '../lib/api'
import { useCravingChat } from '../hooks/useCravingChat'
import { useAuth } from '../contexts/AuthContext'
import type { ChatMention, ChatMessage, EventAttendee, PinnedMessage } from '../types'
import { timeAgo, parseUtc } from '../lib/formatDate'
import ExternalLink from './ui/ExternalLink'

// WhatsApp-style per-sender name color (bubble background stays uniform —
// only the username label above each message is colorized) — crew feedback
// asked for this explicitly and said it's fine to step outside the app's
// normal orange-accent-only palette for it. Admins keep the real accent
// color instead of a hashed one, same idea as the [ADMIN] role tag elsewhere.
const USER_COLORS = ['#34d399', '#60a5fa', '#a78bfa', '#f472b6', '#fbbf24', '#22d3ee', '#fb923c', '#4ade80']

// A quick-pick row alongside the free-text OS-picker input — covers the
// common cases in one click for anyone who doesn't know/want the Win+. /
// Ctrl+Cmd+Space shortcut, without giving up the free-text option entirely.
const QUICK_REACTIONS = ['👍', '😀', '🤣', '😢', '😮', '❤️']

// Trailing punctuation (".", ",", a closing paren someone typed after the
// link, …) is peeled off a matched URL so "check https://x.com/y." doesn't
// swallow the period into the href.
const URL_SRC = 'https?:\\/\\/[^\\s<]+'
const TRAILING_PUNCT_RE = /[.,!?;:'")\]]+$/

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// "<3" is the one shorthand kept outside the colon-code convention below —
// short enough (2 chars, no letters) that a discovery UI would be overkill,
// so it just converts on sight like before.
const RAW_EMOTES: [RegExp, string][] = [[/<3/g, '❤️']]

// Discord/Slack-style ":code:" shortcodes — discoverable in the composer by
// typing ":" (see EMOTE_SUGGESTIONS wiring below), matched case-insensitively
// here so ":xd:", ":Xd:" and ":XD:" all resolve without separate entries per
// case. Order is the same order suggestions appear in the autocomplete
// dropdown, so keep the most-used ones near the top.
const EMOTE_CODES: { code: string; emoji: string }[] = [
  { code: 'smile', emoji: '🙂' },
  { code: 'lol', emoji: '😂' },
  { code: 'rofl', emoji: '🤣' },
  { code: 'xd', emoji: '😆' },
  { code: 'wink', emoji: '😉' },
  { code: 'love', emoji: '😍' },
  { code: 'cry', emoji: '😭' },
  { code: 'sad', emoji: '🙁' },
  { code: 'angry', emoji: '😠' },
  { code: 'fire', emoji: '🔥' },
  { code: 'clap', emoji: '👏' },
  { code: 'eyes', emoji: '👀' },
  { code: 'gg', emoji: '🎮' },
]

function replaceEmoticons(text: string): string {
  let result = RAW_EMOTES.reduce((acc, [re, emoji]) => acc.replace(re, emoji), text)
  for (const { code, emoji } of EMOTE_CODES) {
    result = result.replace(new RegExp(`:${code}:`, 'gi'), emoji)
  }
  return result
}

// One combined pass, not two independent ones: URLs and @mentions are split
// out of the same text with a single alternation so neither pass can eat
// into a match the other one would also have claimed. @mentions are only
// ever highlighted against `mentions` — the server-confirmed list this exact
// message actually resolved (see router_chat.py's _resolve_mentions) — never
// a blind client-side regex, so a stray "@notarealuser" never lights up.
// Case-insensitive throughout: the server matches mentions case-insensitively
// too (so "@crosswax" in the raw text still needs to highlight even though
// the resolved username is "CrossWax"), and it's a harmless bonus for URLs.
export function renderMessageContent(text: string, mentions: ChatMention[]) {
  // Longest-first so a shorter mentioned username can't shadow a match that
  // should have consumed a longer one sharing the same prefix.
  const names = [...new Set(mentions.map((m) => m.username))].sort((a, b) => b.length - a.length)
  const mentionSrc = names.map((n) => `@${escapeRegExp(n)}(?=$|\\s|[.,!?;:])`).join('|')
  const combinedRe = new RegExp(`(${URL_SRC}${mentionSrc ? `|${mentionSrc}` : ''})`, 'gi')

  return text.split(combinedRe).map((part, i) => {
    if (i % 2 === 0) return replaceEmoticons(part)
    if (/^https?:\/\//i.test(part)) {
      // ExternalLink, not a plain <a target="_blank">: inside the desktop
      // app's embedded iframe, target="_blank" has nowhere to open into
      // (Tauri spawns no window for it) and the click is a silent no-op —
      // see desktopapp/src-tauri/src/main.rs's open_external doc comment.
      // ExternalLink already handles both cases (real anchor in a browser
      // tab, routes through the shell's system-browser opener when embedded).
      const trailing = part.match(TRAILING_PUNCT_RE)?.[0] ?? ''
      const url = trailing ? part.slice(0, -trailing.length) : part
      return (
        <span key={i}>
          <ExternalLink href={url} className="underline decoration-white/50 hover:decoration-white break-all">
            {url}
          </ExternalLink>
          {trailing}
        </span>
      )
    }
    return (
      // A deliberate, one-off exception to md/13.uxui/UXUI.md's orange-accent-only
      // palette — explicitly asked for a distinct gold (#DBB844) so an
      // @mention reads as its own kind of highlight, not just "another
      // accent-colored thing" competing visually with the rest of the UI.
      <span key={i} className="font-bold text-[#DBB844] bg-[#DBB844]/15 rounded-sm px-0.5">
        {part}
      </span>
    )
  })
}

export function colorForUser(userId: number, isAdmin: boolean): string {
  if (isAdmin) return '#FF3D00'
  let hash = 0
  for (let i = 0; i < String(userId).length; i++) hash = (hash * 31 + userId) | 0
  return USER_COLORS[Math.abs(hash) % USER_COLORS.length]
}

const EDIT_WINDOW_MS = 10 * 60 * 1000

// A minimal "WhatsApp Web"-style room: one bubble list, newest at the
// bottom, own messages right-aligned, everyone else's left-aligned. Reply
// (with a quoted blockquote), a 10-minute self-edit window, and a single
// free-text emoji reaction per person (typed via the OS's own emoji picker —
// Win+. / Ctrl+Cmd+Space work in any plain text input) round out what crew
// feedback asked for after the first live test — see md/2.features/Craving_chat_v2.md.
// Self-contained (own fetch, own error handling) so a closed/disabled room
// never takes the rest of the Hub down — same convention as
// GroceriesSection/GearSection.
interface Props {
  eventId: number
  /** The event's own attendees (already loaded on every LanEvent — see
   *  router_events.py's _enrich) — scopes the @mention autocomplete to
   *  "people actually in this chat room" instead of every user in the
   *  system. Threaded down as a prop rather than fetched here, same
   *  convention as GroceriesSection's `attendees` prop. */
  attendees: EventAttendee[]
  /** Tailwind height class(es) for the message-list box. Defaults to the
   *  compact size used inline on the Hub; CravingChatPage.tsx (the
   *  standalone page) passes a taller, viewport-relative one instead — kept
   *  as a prop rather than two copies of this component so both stay in
   *  sync automatically. */
  heightClassName?: string
}

const MAX_MENTION_SUGGESTIONS = 6
const MAX_EMOTE_SUGGESTIONS = 8

const TYPING_EXPIRE_MS = 4000
const TYPING_SEND_THROTTLE_MS = 2000

export default function CravingChatSection({ eventId, attendees, heightClassName = 'h-[460px]' }: Props) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [closed, setClosed] = useState(false)
  const [openMenuId, setOpenMenuId] = useState<number | null>(null)
  const [reactingId, setReactingId] = useState<number | null>(null)
  const [replyingTo, setReplyingTo] = useState<ChatMessage | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [pinned, setPinned] = useState<PinnedMessage | null>(null)
  // user_id -> username, for everyone currently shown as "typing…". Entries
  // expire on their own (see the timer below) since the backend only ever
  // relays a "typing" ping, never an explicit "stopped".
  const [typingUsers, setTypingUsers] = useState<Record<number, string>>({})
  const typingTimers = useRef<Record<number, number>>({})
  const lastTypingSentAt = useRef(0)
  // Fragment typed after an in-progress "@" (e.g. "Cr" while typing
  // "@CrossWax") — null when the composer isn't mid-mention. Kept separate
  // from `draft` itself since it's derived from cursor position, not just
  // the text content.
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const [mentionIndex, setMentionIndex] = useState(0)
  // Same idea as mentionQuery, but for an in-progress ":fragment" — the hint
  // dropdown opens the instant ":" is typed (fragment === "") so the
  // available commands are discoverable, then narrows as letters follow.
  const [emoteQuery, setEmoteQuery] = useState<string | null>(null)
  const [emoteIndex, setEmoteIndex] = useState(0)
  // Client-side only, over whatever's already loaded (HISTORY_LIMIT = 200
  // messages server-side) — a short-lived, small-history room has no need
  // for a real backend search engine (see md/2.features/craving_chat_suggestions.md).
  const [searchQuery, setSearchQuery] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLInputElement>(null)

  const mentionMatches =
    mentionQuery === null
      ? []
      : attendees
          .filter((a) => a.user_id !== user?.id && a.username.toLowerCase().startsWith(mentionQuery.toLowerCase()))
          .slice(0, MAX_MENTION_SUGGESTIONS)

  const emoteMatches =
    emoteQuery === null
      ? []
      : EMOTE_CODES.filter((em) => em.code.startsWith(emoteQuery.toLowerCase())).slice(0, MAX_EMOTE_SUGGESTIONS)

  const normalizedSearch = searchQuery.trim().toLowerCase()
  const displayedMessages = normalizedSearch
    ? messages.filter(
        (m) => m.content.toLowerCase().includes(normalizedSearch) || m.username.toLowerCase().includes(normalizedSearch)
      )
    : messages

  useEffect(() => {
    setLoading(true)
    chatApi.getMessages(eventId)
      .then(setMessages)
      .catch(() => setClosed(true))
      .finally(() => setLoading(false))
    chatApi.getPinned(eventId).then(setPinned).catch(() => {})
  }, [eventId])

  // Clears every pending "typing" expiry timer on unmount/room switch —
  // otherwise a timer could fire setTypingUsers on an event room the user
  // has already navigated away from.
  useEffect(() => () => {
    Object.values(typingTimers.current).forEach((id) => window.clearTimeout(id))
  }, [])

  const { sendTyping } = useCravingChat(closed ? null : eventId, {
    // Unlike the activity feed (only ever gets new rows), a chat message can
    // change in place — an edit or a reaction — with no new id appearing, so
    // this upserts by id instead of only appending.
    onMessages: (incoming) => {
      setMessages((prev) => {
        const byId = new Map(prev.map((m) => [m.id, m]))
        for (const m of incoming) byId.set(m.id, m)
        return Array.from(byId.values()).sort((a, b) => a.id - b.id)
      })
    },
    onTyping: ({ user_id, username }) => {
      if (user_id === user?.id) return
      setTypingUsers((prev) => ({ ...prev, [user_id]: username }))
      if (typingTimers.current[user_id]) window.clearTimeout(typingTimers.current[user_id])
      typingTimers.current[user_id] = window.setTimeout(() => {
        setTypingUsers((prev) => {
          if (!(user_id in prev)) return prev
          const next = { ...prev }
          delete next[user_id]
          return next
        })
      }, TYPING_EXPIRE_MS)
    },
    onPinned: setPinned,
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'nearest' })
  }, [messages.length])

  const applyUpdate = (updated: ChatMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === updated.id ? updated : m)))
  }

  const send = async () => {
    const content = draft.trim()
    if (!content) return
    setSending(true)
    try {
      if (editingId != null) {
        applyUpdate(await chatApi.editMessage(eventId, editingId, content))
        setEditingId(null)
      } else {
        const msg = await chatApi.postMessage(eventId, content, replyingTo?.id ?? null)
        setMessages((prev) => [...prev, msg])
        setReplyingTo(null)
      }
      setDraft('')
      setMentionQuery(null)
      setEmoteQuery(null)
    } finally {
      setSending(false)
    }
  }

  const remove = async (messageId: number) => {
    await chatApi.deleteMessage(eventId, messageId)
    setMessages((prev) => prev.filter((m) => m.id !== messageId))
  }

  const startReply = (m: ChatMessage) => {
    setReplyingTo(m)
    setEditingId(null)
    setOpenMenuId(null)
    composerRef.current?.focus()
  }

  const startEdit = (m: ChatMessage) => {
    setEditingId(m.id)
    setDraft(m.content)
    setReplyingTo(null)
    setOpenMenuId(null)
    setMentionQuery(null)
    setEmoteQuery(null)
    composerRef.current?.focus()
  }

  const cancelComposerMode = () => {
    setReplyingTo(null)
    setEditingId(null)
    setDraft('')
    setMentionQuery(null)
    setEmoteQuery(null)
  }

  const pickReaction = async (messageId: number, emoji: string) => {
    setReactingId(null)
    applyUpdate(await chatApi.react(eventId, messageId, emoji))
  }

  const canEdit = (m: ChatMessage) => m.is_mine && Date.now() - parseUtc(m.created_at).getTime() < EDIT_WINDOW_MS

  const togglePin = async (m: ChatMessage) => {
    setOpenMenuId(null)
    if (pinned?.id === m.id) {
      await chatApi.unpin(eventId)
      setPinned(null)
    } else {
      setPinned(await chatApi.pin(eventId, m.id))
    }
  }

  // Recomputes the in-progress "@fragment" and ":fragment" (if any) from the
  // text *before* the cursor on every keystroke — not just "does the draft
  // contain an @ or : somewhere", so a finished "@CrossWax hey" or ":gg:
  // well played" earlier in the message doesn't reopen a dropdown while
  // typing further along. The two can never both match at once (the tail
  // can't simultaneously end in "@…" and ":…"), so only one dropdown is ever
  // live. Letters-only fragment for ":" — "12:30" or "https:" never matches
  // since a digit or "/" right after the colon breaks the pattern.
  const handleDraftChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setDraft(value)
    const cursor = e.target.selectionStart ?? value.length
    const uptoCursor = value.slice(0, cursor)
    const mentionMatch = uptoCursor.match(/(?:^|\s)@(\S*)$/)
    setMentionQuery(mentionMatch ? mentionMatch[1] : null)
    setMentionIndex(0)
    const emoteMatch = uptoCursor.match(/(?:^|\s):([a-zA-Z]*)$/)
    setEmoteQuery(emoteMatch ? emoteMatch[1] : null)
    setEmoteIndex(0)

    // Throttled, not per-keystroke — the backend relays this to every other
    // connected client immediately, so there's no reason to spam the socket
    // faster than the "typing…" indicator's own expiry needs to be refreshed.
    if (value.trim() && Date.now() - lastTypingSentAt.current > TYPING_SEND_THROTTLE_MS) {
      lastTypingSentAt.current = Date.now()
      sendTyping()
    }
  }

  const insertMention = (attendee: EventAttendee) => {
    const input = composerRef.current
    const cursor = input?.selectionStart ?? draft.length
    const uptoCursor = draft.slice(0, cursor)
    const atIndex = uptoCursor.lastIndexOf('@')
    if (atIndex === -1) { setMentionQuery(null); return }
    const insertion = `@${attendee.username} `
    const next = draft.slice(0, atIndex) + insertion + draft.slice(cursor)
    setDraft(next)
    setMentionQuery(null)
    const caretPos = atIndex + insertion.length
    // The input re-renders with the new value before this runs, so the
    // selection can be restored to right after the inserted "@username ".
    requestAnimationFrame(() => {
      input?.focus()
      input?.setSelectionRange(caretPos, caretPos)
    })
  }

  // Inserts the raw ":code: " text, not the emoji itself — same convention
  // as insertMention storing "@username": the composer (and an edit
  // re-opened later) shows the shortcode you typed, and replaceEmoticons
  // turns it into the emoji at render time, whether it got there via this
  // picker or by typing the whole code out by hand.
  const insertEmote = (emote: { code: string; emoji: string }) => {
    const input = composerRef.current
    const cursor = input?.selectionStart ?? draft.length
    const uptoCursor = draft.slice(0, cursor)
    const colonIndex = uptoCursor.lastIndexOf(':')
    if (colonIndex === -1) { setEmoteQuery(null); return }
    const insertion = `:${emote.code}: `
    const next = draft.slice(0, colonIndex) + insertion + draft.slice(cursor)
    setDraft(next)
    setEmoteQuery(null)
    const caretPos = colonIndex + insertion.length
    requestAnimationFrame(() => {
      input?.focus()
      input?.setSelectionRange(caretPos, caretPos)
    })
  }

  const handleComposerKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (mentionQuery !== null && mentionMatches.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setMentionIndex((i) => (i + 1) % mentionMatches.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setMentionIndex((i) => (i - 1 + mentionMatches.length) % mentionMatches.length); return }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); insertMention(mentionMatches[mentionIndex]); return }
      if (e.key === 'Escape') { e.preventDefault(); setMentionQuery(null); return }
    }
    if (emoteQuery !== null && emoteMatches.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setEmoteIndex((i) => (i + 1) % emoteMatches.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setEmoteIndex((i) => (i - 1 + emoteMatches.length) % emoteMatches.length); return }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); insertEmote(emoteMatches[emoteIndex]); return }
      if (e.key === 'Escape') { e.preventDefault(); setEmoteQuery(null); return }
    }
    if (e.key === 'Enter' && !e.shiftKey) send()
  }

  if (loading) {
    return (
      <div className="border border-border bg-card p-8 text-center">
        <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
      </div>
    )
  }

  if (closed) {
    return (
      <div className="border border-border bg-card p-6 text-center">
        <p className="font-mono-label text-muted-foreground text-xs">{t('cravingChat.closed')}</p>
      </div>
    )
  }

  return (
    <div className={`border border-border bg-card flex flex-col ${heightClassName}`}>
      <div className="border-b border-border px-3 py-1.5 flex items-center gap-1.5 flex-shrink-0">
        <Search size={12} strokeWidth={1.5} className="text-muted-foreground flex-shrink-0" />
        <input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t('cravingChat.searchPlaceholder')}
          className="flex-1 min-w-0 bg-transparent text-xs text-foreground placeholder:text-muted-foreground outline-none"
        />
        {searchQuery && (
          <>
            <span className="font-mono-label text-muted-foreground text-[10px] flex-shrink-0">
              {t('cravingChat.searchResults', { count: displayedMessages.length })}
            </span>
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="text-muted-foreground hover:text-foreground flex-shrink-0"
              title={t('cravingChat.searchClear')}
              aria-label={t('cravingChat.searchClear')}
            >
              <X size={12} strokeWidth={1.5} />
            </button>
          </>
        )}
      </div>
      {pinned && (
        <div className="border-b border-border bg-accent/5 px-3 py-2 flex items-center gap-2 flex-shrink-0">
          <Pin size={12} strokeWidth={1.5} className="text-accent flex-shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="font-mono-label text-accent text-[10px]">{t('cravingChat.pinnedLabel')}</p>
            <p className="text-xs text-foreground truncate">
              <span className="font-bold">{pinned.username}</span>: {pinned.content}
            </p>
          </div>
          {isAdmin && (
            <button
              type="button"
              onClick={async () => { await chatApi.unpin(eventId); setPinned(null) }}
              className="text-muted-foreground hover:text-foreground flex-shrink-0"
              title={t('cravingChat.unpin')}
              aria-label={t('cravingChat.unpin')}
            >
              <X size={13} strokeWidth={1.5} />
            </button>
          )}
        </div>
      )}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {displayedMessages.length === 0 ? (
          <p className="font-mono-label text-muted-foreground text-xs text-center mt-8">
            {normalizedSearch ? t('cravingChat.searchEmpty') : t('cravingChat.empty')}
          </p>
        ) : (
          displayedMessages.map((m) => {
            // Popovers anchor toward the bubble's own side (right for mine,
            // left for others') so they grow inward, toward the center of
            // the chat, instead of always growing leftward off a right-1
            // anchor — which spilled off the chat box's edge for short
            // bubbles sitting close to either side.
            const anchorSide = m.is_mine ? 'right-1' : 'left-1'
            return (
            <div key={m.id} className={`group flex ${m.is_mine ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`relative max-w-[75%] px-3 py-2 text-white ${
                  m.is_mine ? 'bg-emerald-800' : 'bg-neutral-700'
                }`}
              >
                {/* Hover action toolbar — react (others' messages only) + a
                    down-chevron menu (reply always, edit/delete own only). */}
                <div className={`absolute -top-3 ${anchorSide} hidden group-hover:flex items-center gap-0.5 bg-card border border-border shadow-sm z-10`}>
                  {!m.is_mine && (
                    <button
                      type="button"
                      onClick={() => { setReactingId(reactingId === m.id ? null : m.id); setOpenMenuId(null) }}
                      className="p-1 text-muted-foreground hover:text-accent"
                      title={t('cravingChat.reactButton')}
                      aria-label={t('cravingChat.reactButton')}
                    >
                      <Smile size={13} strokeWidth={1.5} />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => { setOpenMenuId(openMenuId === m.id ? null : m.id); setReactingId(null) }}
                    className="p-1 text-muted-foreground hover:text-accent"
                    title={t('cravingChat.moreActions')}
                    aria-label={t('cravingChat.moreActions')}
                  >
                    <ChevronDown size={13} strokeWidth={1.5} />
                  </button>
                </div>

                {openMenuId === m.id && (
                  <div className={`absolute top-4 ${anchorSide} min-w-[140px] bg-card border border-border shadow-md z-20 text-xs text-foreground`}>
                    <button
                      type="button"
                      onClick={() => startReply(m)}
                      className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted text-left"
                    >
                      <CornerUpLeft size={12} strokeWidth={1.5} /> {t('cravingChat.reply')}
                    </button>
                    {canEdit(m) && (
                      <button
                        type="button"
                        onClick={() => startEdit(m)}
                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted text-left border-t border-border"
                      >
                        <Pencil size={12} strokeWidth={1.5} /> {t('cravingChat.edit')}
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => togglePin(m)}
                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted text-left border-t border-border"
                      >
                        {pinned?.id === m.id ? (
                          <><PinOff size={12} strokeWidth={1.5} /> {t('cravingChat.unpin')}</>
                        ) : (
                          <><Pin size={12} strokeWidth={1.5} /> {t('cravingChat.pin')}</>
                        )}
                      </button>
                    )}
                    {m.is_mine && (
                      <button
                        type="button"
                        onClick={() => remove(m.id)}
                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted text-left border-t border-border text-red-400"
                      >
                        <Trash2 size={12} strokeWidth={1.5} /> {t('cravingChat.deleteButton')}
                      </button>
                    )}
                  </div>
                )}

                {reactingId === m.id && (
                  // Used to also have a free-text input (type/paste any
                  // emoji via the OS's own picker) — dropped after crew
                  // testing found it genuinely unintuitive even with a
                  // visible caption on it. The 6 presets below cover the
                  // common cases; simpler beats complete for this.
                  <div className={`absolute top-4 ${anchorSide} bg-card border border-border shadow-md z-20 p-1.5 flex items-center gap-1 w-max`}>
                    {QUICK_REACTIONS.map((emoji) => (
                      <button
                        key={emoji}
                        type="button"
                        onClick={() => pickReaction(m.id, emoji)}
                        title={emoji}
                        className="w-7 h-7 flex items-center justify-center text-base border border-transparent hover:border-border hover:bg-muted rounded-sm transition-colors"
                      >
                        {emoji}
                      </button>
                    ))}
                  </div>
                )}

                {!m.is_mine && (
                  <Link to={`/players/${m.user_id}`} className="flex items-center gap-1.5 mb-1 w-fit group/author">
                    {/* Circular avatar is a deliberate, one-off exception to
                        md/13.uxui/UXUI.md's "no rounded corners" rule — a group chat
                        reads as a WhatsApp-style group specifically because
                        of the round sender photos, and that association is
                        the whole point here. Nowhere else in the app should
                        copy this. */}
                    <div className="w-5 h-5 rounded-full bg-muted border border-border overflow-hidden flex-shrink-0">
                      {m.avatar_url ? (
                        <img src={m.avatar_url} alt={m.username} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <span className="text-[8px] font-black text-muted-foreground">
                            {m.username[0].toUpperCase()}
                          </span>
                        </div>
                      )}
                    </div>
                    <p
                      className="text-xs font-bold group-hover/author:underline"
                      style={{ color: colorForUser(m.user_id, m.is_admin) }}
                    >
                      {m.username}
                    </p>
                  </Link>
                )}

                {m.reply_to && (
                  <div className="border-l-2 border-white/40 pl-2 mb-1.5 opacity-75">
                    <p className="text-[10px] font-bold">{m.reply_to.username}</p>
                    <p className="text-xs truncate">{m.reply_to.content}</p>
                  </div>
                )}

                <p className="text-sm whitespace-pre-wrap break-words">{renderMessageContent(m.content, m.mentions)}</p>

                {m.link_preview && (
                  <ExternalLink
                    href={m.link_preview.url}
                    className="block w-full text-left mt-1.5 border border-white/20 bg-black/20 hover:bg-black/30 transition-colors overflow-hidden"
                  >
                    {m.link_preview.image_url && (
                      <img
                        src={m.link_preview.image_url}
                        alt=""
                        className="w-full max-h-40 object-cover"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                    )}
                    <div className="px-2.5 py-2">
                      {m.link_preview.site_name && (
                        <p className="text-[10px] font-mono-label opacity-60 mb-0.5">{m.link_preview.site_name}</p>
                      )}
                      {m.link_preview.title && (
                        <p className="text-xs font-bold leading-snug">{m.link_preview.title}</p>
                      )}
                      {m.link_preview.description && (
                        <p className="text-[11px] opacity-70 leading-snug line-clamp-2 mt-0.5">{m.link_preview.description}</p>
                      )}
                    </div>
                  </ExternalLink>
                )}

                <div className="flex items-center gap-1.5 mt-1">
                  <span className="text-[10px] opacity-70">{timeAgo(m.created_at)}</span>
                  {m.edited_at && <span className="text-[10px] opacity-70">· {t('cravingChat.editedTag')}</span>}
                </div>

                {m.reactions.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {m.reactions.map((r) => (
                      <button
                        key={r.emoji}
                        type="button"
                        onClick={async () => applyUpdate(await chatApi.react(eventId, m.id, r.emoji))}
                        className={`text-xs px-1.5 py-0.5 rounded-full bg-black/25 border ${
                          r.mine ? 'border-accent' : 'border-white/20'
                        }`}
                      >
                        {r.emoji} <span className="font-mono">{r.count}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )})
        )}
        <div ref={bottomRef} />
      </div>

      {Object.keys(typingUsers).length > 0 && (
        <div className="px-3 pt-1.5 flex-shrink-0">
          <p className="font-mono-label text-muted-foreground text-[10px] animate-pulse">
            {t('cravingChat.typing', {
              count: Object.keys(typingUsers).length,
              username: Object.values(typingUsers)[0],
            })}
          </p>
        </div>
      )}

      {(replyingTo || editingId != null) && (
        <div className="border-t border-border px-3 py-2 flex items-center justify-between gap-2 bg-muted/50">
          <div className="min-w-0 text-xs text-muted-foreground">
            {editingId != null ? (
              <span className="font-mono-label">{t('cravingChat.editingLabel')}</span>
            ) : (
              <>
                <span className="font-mono-label">{t('cravingChat.replyingLabel')}</span>{' '}
                <span className="truncate">{replyingTo?.username}: {replyingTo?.content}</span>
              </>
            )}
          </div>
          <button type="button" onClick={cancelComposerMode} className="text-muted-foreground hover:text-foreground flex-shrink-0">
            <X size={14} strokeWidth={1.5} />
          </button>
        </div>
      )}

      <div className="border-t border-border p-3 flex items-center gap-2">
        <div className="flex-1 relative">
          {mentionQuery !== null && mentionMatches.length > 0 && (
            <div className="absolute bottom-full left-0 mb-1 w-full max-w-xs bg-card border border-border shadow-md z-20 text-xs text-foreground">
              {mentionMatches.map((a, i) => (
                <button
                  key={a.user_id}
                  type="button"
                  // Fires before the input's blur, so clicking a suggestion
                  // doesn't collapse the selection/close the dropdown first.
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => insertMention(a)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-left ${i === mentionIndex ? 'bg-muted' : 'hover:bg-muted'}`}
                >
                  <div className="w-5 h-5 rounded-full bg-muted border border-border overflow-hidden flex-shrink-0">
                    {a.avatar_url ? (
                      <img src={a.avatar_url} alt={a.username} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <span className="text-[8px] font-black text-muted-foreground">
                          {a.username[0].toUpperCase()}
                        </span>
                      </div>
                    )}
                  </div>
                  <span className="font-bold">{a.username}</span>
                </button>
              ))}
            </div>
          )}
          {emoteQuery !== null && emoteMatches.length > 0 && (
            <div className="absolute bottom-full left-0 mb-1 w-full max-w-xs bg-card border border-border shadow-md z-20 text-xs text-foreground">
              {emoteMatches.map((em, i) => (
                <button
                  key={em.code}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => insertEmote(em)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-left ${i === emoteIndex ? 'bg-muted' : 'hover:bg-muted'}`}
                >
                  <span className="text-base">{em.emoji}</span>
                  <span className="font-mono-label">:{em.code}:</span>
                </button>
              ))}
            </div>
          )}
          <input
            ref={composerRef}
            value={draft}
            onChange={handleDraftChange}
            onKeyDown={handleComposerKeyDown}
            placeholder={t('cravingChat.placeholder')}
            maxLength={2000}
            className="w-full bg-muted border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-accent outline-none"
          />
        </div>
        <button
          onClick={send}
          disabled={sending || !draft.trim()}
          className="p-2 bg-accent text-accent-foreground disabled:opacity-40 transition-opacity"
          title={t('cravingChat.sendButton')}
          aria-label={t('cravingChat.sendButton')}
        >
          <Send size={14} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  )
}
