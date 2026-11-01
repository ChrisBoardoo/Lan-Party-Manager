import { describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import '../i18n'
import { ToastProvider } from '../contexts/ToastContext'
import { chatApi } from '../lib/api'
import type { ChatMention, ChatMessage } from '../types'
import CravingChatSection, { renderMessageContent, colorForUser, mergeMessages } from './CravingChatSection'

vi.mock('../lib/api', () => ({ chatApi: { getMessages: vi.fn(), getPinned: vi.fn() } }))
vi.mock('../hooks/useCravingChat', () => ({ useCravingChat: () => ({ sendTyping: () => {} }) }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, role: 'user' } }) }))

// renderMessageContent is the one-pass URL + @mention highlighter for chat
// bubbles (router_chat.py's _resolve_mentions is the actual security
// boundary — this only decides what lights up visually). Regressions here
// are easy to miss because they only ever change *rendering*, not data.

function renderContent(text: string, mentions: ChatMention[] = []) {
  return render(<div data-testid="content">{renderMessageContent(text, mentions)}</div>)
}

describe('renderMessageContent', () => {
  it('renders plain text with no highlighting untouched', () => {
    const { getByTestId } = renderContent('gg, see you at the LAN')
    expect(getByTestId('content').textContent).toBe('gg, see you at the LAN')
  })

  it('highlights a resolved @mention', () => {
    const { container } = renderContent('good luck @CrossWax !', [{ user_id: 1, username: 'CrossWax' }])
    const highlighted = container.querySelector('span.font-bold')
    expect(highlighted).not.toBeNull()
    expect(highlighted?.textContent).toBe('@CrossWax')
  })

  it('never highlights a name that is not in the server-confirmed mentions list', () => {
    // No mentions passed — a raw "@someone" in the text must not light up,
    // since only the server's resolved list is trusted (never a blind regex
    // over arbitrary "@word" text).
    const { container } = renderContent('hey @notarealuser, ping?', [])
    expect(container.querySelector('span.font-bold')).toBeNull()
  })

  it('matches a mention case-insensitively against the resolved username', () => {
    // The server resolves mentions case-insensitively too (a stored
    // "CrossWax" must still highlight when the raw text says "@crosswax").
    const { container } = renderContent('gg @crosswax', [{ user_id: 1, username: 'CrossWax' }])
    const highlighted = container.querySelector('span.font-bold')
    expect(highlighted?.textContent).toBe('@crosswax')
  })

  it('picks the longest matching name so a shorter mention cannot shadow a longer one', () => {
    const mentions: ChatMention[] = [
      { user_id: 1, username: 'Chris' },
      { user_id: 2, username: 'ChrisTournamentAdmin' },
    ]
    const { container } = renderContent('welcome @ChrisTournamentAdmin', mentions)
    const spans = container.querySelectorAll('span.font-bold')
    expect(spans).toHaveLength(1)
    expect(spans[0].textContent).toBe('@ChrisTournamentAdmin')
  })

  it('does not swallow trailing punctuation into the mention', () => {
    const { container } = renderContent('thanks @CrossWax!', [{ user_id: 1, username: 'CrossWax' }])
    const highlighted = container.querySelector('span.font-bold')
    expect(highlighted?.textContent).toBe('@CrossWax')
  })

  it('renders a URL as a link with its own text', () => {
    const { container } = renderContent('check https://example.com/path for details')
    const link = container.querySelector('a')
    expect(link).not.toBeNull()
    expect(link?.getAttribute('href')).toBe('https://example.com/path')
    expect(link?.textContent).toBe('https://example.com/path')
  })

  it('strips trailing punctuation from a URL without dropping it from the sentence', () => {
    const { getByTestId, container } = renderContent('see https://example.com/path.')
    const link = container.querySelector('a')
    expect(link?.getAttribute('href')).toBe('https://example.com/path')
    expect(getByTestId('content').textContent).toBe('see https://example.com/path.')
  })

  it('highlights a URL and a mention in the same message without one eating the other', () => {
    const { container } = renderContent('cc @CrossWax see https://example.com/x', [
      { user_id: 1, username: 'CrossWax' },
    ])
    expect(container.querySelector('a')?.textContent).toBe('https://example.com/x')
    expect(container.querySelector('span.font-bold')?.textContent).toBe('@CrossWax')
  })

  it('replaces <3 with a heart', () => {
    const { getByTestId } = renderContent('love this crew <3')
    expect(getByTestId('content').textContent).toBe('love this crew ❤️')
  })

  it('replaces :smile: with a smile', () => {
    const { getByTestId } = renderContent('gg :smile:')
    expect(getByTestId('content').textContent).toBe('gg 🙂')
  })

  it('replaces :xd: with a huge smile, case-insensitively', () => {
    const { getByTestId } = renderContent('that was :xd: so :XD: so :Xd: funny')
    expect(getByTestId('content').textContent).toBe('that was 😆 so 😆 so 😆 funny')
  })

  it('does not rewrite a bare "xD" that is not wrapped in colons', () => {
    // The colon-code convention is deliberate: only ":xd:" converts now, not
    // a bare "xD" — avoids the old false-positive risk (e.g. "TuxDeploy").
    const { getByTestId } = renderContent('that was xD funny, TuxDeploy is not an emoticon')
    expect(getByTestId('content').textContent).toBe('that was xD funny, TuxDeploy is not an emoticon')
  })

  it('replaces :rofl: with the rolling-on-the-floor-laughing emoji', () => {
    const { getByTestId } = renderContent('lol :rofl:')
    expect(getByTestId('content').textContent).toBe('lol 🤣')
  })

  it.each([
    ['lol', '😂'],
    ['wink', '😉'],
    ['love', '😍'],
    ['cry', '😭'],
    ['sad', '🙁'],
    ['angry', '😠'],
    ['fire', '🔥'],
    ['clap', '👏'],
    ['eyes', '👀'],
    ['gg', '🎮'],
  ])('replaces the :%s: shortcode with its emoji', (code, emoji) => {
    const { getByTestId } = renderContent(`:${code}:`)
    expect(getByTestId('content').textContent).toBe(emoji)
  })

  it('does not rewrite emoticon-like text inside a URL or a mention', () => {
    const { getByTestId, container } = renderContent('see https://example.com/:gg:-page <3 @CrossWax', [
      { user_id: 1, username: 'CrossWax' },
    ])
    expect(container.querySelector('a')?.textContent).toBe('https://example.com/:gg:-page')
    expect(container.querySelector('span.font-bold')?.textContent).toBe('@CrossWax')
    expect(getByTestId('content').textContent).toBe('see https://example.com/:gg:-page ❤️ @CrossWax')
  })
})

describe('colorForUser', () => {
  it('always gives admins the accent red, regardless of user id', () => {
    expect(colorForUser(1, true)).toBe('#FF3D00')
    expect(colorForUser(999, true)).toBe('#FF3D00')
  })

  it('is deterministic for the same non-admin user id', () => {
    expect(colorForUser(42, false)).toBe(colorForUser(42, false))
  })

  it('never assigns a non-admin the reserved admin color', () => {
    for (let id = 0; id < 50; id++) {
      expect(colorForUser(id, false)).not.toBe('#FF3D00')
    }
  })
})

describe('mergeMessages', () => {
  const msg = (id: number, content = `m${id}`) => ({ id, content }) as ChatMessage

  it('keeps a message I sent once when the socket pushed it before the POST answered', () => {
    const pushed = mergeMessages([msg(1)], [msg(2, 'test')])
    const answered = mergeMessages(pushed, [msg(2, 'test')], true)
    expect(answered.map((m) => m.id)).toEqual([1, 2])
  })

  it("doesn't let the POST's older copy overwrite what the socket pushed", () => {
    const pushed = mergeMessages([], [msg(2, 'with its link preview')])
    expect(mergeMessages(pushed, [msg(2, 'as posted')], true)[0].content).toBe('with its link preview')
  })

  it('lets the socket update a message in place (an edit, a reaction)', () => {
    expect(mergeMessages([msg(1, 'before')], [msg(1, 'after')])[0].content).toBe('after')
  })

  it('keeps the list in id order', () => {
    expect(mergeMessages([msg(3)], [msg(1), msg(2)]).map((m) => m.id)).toEqual([1, 2, 3])
  })
})

// 2026-11-01, desktop app: the Hub opened the October LAN's room (picked
// before the chat rules had loaded), switched to the 2027 LAN's a moment
// later, and the October room's slower answer landed last — the Hub then
// showed October's messages while the chat page showed 2027's.
describe('CravingChatSection: switching rooms', () => {
  const message = (id: number, eventId: number, content: string) =>
    ({
      id, event_id: eventId, user_id: 2, username: 'HugeP', avatar_url: null, is_admin: false, content,
      created_at: '2026-10-19T12:00:00', edited_at: null, is_mine: false, reply_to: null,
      reactions: [], link_preview: null, mentions: [],
    }) as ChatMessage

  it("keeps the new room's messages when the old room answers last", async () => {
    Element.prototype.scrollIntoView = vi.fn()  // jsdom has none
    let answerOld!: (items: ChatMessage[]) => void
    let answerNew!: (items: ChatMessage[]) => void
    vi.mocked(chatApi.getMessages)
      .mockReturnValueOnce(new Promise((resolve) => { answerOld = resolve }))
      .mockReturnValueOnce(new Promise((resolve) => { answerNew = resolve }))
    vi.mocked(chatApi.getPinned).mockResolvedValue(null)
    const room = (eventId: number) => (
      <MemoryRouter><ToastProvider><CravingChatSection eventId={eventId} attendees={[]} /></ToastProvider></MemoryRouter>
    )

    const { rerender } = render(room(1))
    rerender(room(2))
    await act(async () => { answerNew([message(20, 2, 'yes lanpartymanager.com')]) })
    await act(async () => { answerOld([message(10, 1, 'Gg lan')]) })

    expect(screen.getByText('yes lanpartymanager.com')).toBeInTheDocument()
    expect(screen.queryByText('Gg lan')).toBeNull()
  })
})
