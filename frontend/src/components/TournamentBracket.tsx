import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Tournament, Match, Team } from '../types'
import Button from './ui/Button'
import { useAuth } from '../contexts/AuthContext'
import { tournamentsApi } from '../lib/api'

interface TournamentBracketProps {
  tournament: Tournament
  onUpdate: () => void
}

interface MatchCardProps {
  match: Match
  canEdit: boolean
  onUpdate: (matchId: number, data: { score_a?: number; score_b?: number; status?: string; winner_id?: number }) => void
  onReport: (matchId: number, data: { score_a: number; score_b: number }) => void
  onConfirm: (matchId: number) => void
  onReject: (matchId: number) => void
}

function MatchCard({ match, canEdit, onUpdate, onReport, onConfirm, onReject }: MatchCardProps) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [editing, setEditing] = useState(false)
  const [scoreA, setScoreA] = useState(match.score_a)
  const [scoreB, setScoreB] = useState(match.score_b)
  const [saving, setSaving] = useState(false)
  const [reporting, setReporting] = useState(false)
  const [repA, setRepA] = useState(0)
  const [repB, setRepB] = useState(0)

  const isDone = match.status === 'completed'
  const teamA = match.team_a
  const teamB = match.team_b
  const hasReport = match.reported_by != null
  const isParticipant = !!user && [teamA, teamB].some((tm) => tm?.members?.some((m) => m.user_id === user.id))

  const submitReport = async () => {
    setSaving(true)
    try {
      await onReport(match.id, { score_a: repA, score_b: repB })
      setReporting(false)
    } finally {
      setSaving(false)
    }
  }

  const handleSave = async (winnerId: number) => {
    setSaving(true)
    try {
      await onUpdate(match.id, {
        score_a: scoreA,
        score_b: scoreB,
        winner_id: winnerId,
        status: 'completed',
      })
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className={`border ${isDone ? 'border-border' : 'border-border hover:border-border-hover'} bg-card transition-colors duration-150 min-w-[200px]`}
    >
      {/* Team A */}
      <div
        className={`flex items-center justify-between px-3 py-2 border-b border-border ${
          isDone && match.winner_id === teamA?.id ? 'bg-accent/10' : ''
        }`}
      >
        <span
          className={`text-sm font-semibold truncate ${
            isDone && match.winner_id === teamA?.id ? 'text-accent' : teamA ? 'text-foreground' : 'text-muted-foreground'
          }`}
        >
          {teamA?.team_name ?? t('tournaments.bracketView.tbd')}
        </span>
        {editing ? (
          <input
            type="number"
            min={0}
            value={scoreA}
            onChange={(e) => setScoreA(Number(e.target.value))}
            className="w-10 h-6 text-center text-sm bg-input border border-border focus:border-accent outline-none font-mono"
          />
        ) : (
          <span className="font-mono text-sm font-bold text-foreground">{isDone ? match.score_a : '—'}</span>
        )}
      </div>

      {/* Team B */}
      <div
        className={`flex items-center justify-between px-3 py-2 ${
          isDone && match.winner_id === teamB?.id ? 'bg-accent/10' : ''
        }`}
      >
        <span
          className={`text-sm font-semibold truncate ${
            isDone && match.winner_id === teamB?.id ? 'text-accent' : teamB ? 'text-foreground' : 'text-muted-foreground'
          }`}
        >
          {teamB?.team_name ?? t('tournaments.bracketView.tbd')}
        </span>
        {editing ? (
          <input
            type="number"
            min={0}
            value={scoreB}
            onChange={(e) => setScoreB(Number(e.target.value))}
            className="w-10 h-6 text-center text-sm bg-input border border-border focus:border-accent outline-none font-mono"
          />
        ) : (
          <span className="font-mono text-sm font-bold text-foreground">{isDone ? match.score_b : '—'}</span>
        )}
      </div>

      {/* Actions */}
      {canEdit && !isDone && teamA && teamB && (
        <div className="px-3 py-2 border-t border-border bg-muted/50">
          {editing ? (
            <div className="flex gap-1">
              <button
                onClick={() => handleSave(scoreA >= scoreB ? teamA.id : teamB.id)}
                disabled={saving || scoreA === scoreB}
                className="flex-1 text-xs font-mono-label py-1 bg-accent text-accent-foreground hover:bg-accent/90 disabled:opacity-40 transition-colors"
              >
                {saving ? '...' : t('common.save')}
              </button>
              <button
                onClick={() => setEditing(false)}
                className="px-2 text-xs font-mono-label py-1 border border-border text-muted-foreground hover:text-foreground transition-colors"
              >
                ✕
              </button>
            </div>
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="w-full text-xs font-mono-label py-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              {t('tournaments.bracketView.setScore')}
            </button>
          )}
        </div>
      )}

      {/* Self-service score reporting (participants report, organizer confirms) */}
      {!isDone && teamA && teamB && (
        <>
          {/* Organizer: a pending reported score to accept or reject */}
          {canEdit && hasReport && (
            <div className="px-3 py-2 border-t border-border bg-accent/5">
              <p className="font-mono-label text-accent text-[10px] mb-1.5">
                {t('tournaments.bracketView.reported', { a: match.reported_score_a, b: match.reported_score_b })}
              </p>
              <div className="flex gap-1">
                <button
                  onClick={() => onConfirm(match.id)}
                  className="flex-1 text-xs font-mono-label py-1 bg-accent text-accent-foreground hover:bg-accent/90 transition-colors"
                >
                  {t('tournaments.bracketView.confirm')}
                </button>
                <button
                  onClick={() => onReject(match.id)}
                  className="px-2 text-xs font-mono-label py-1 border border-border text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('tournaments.bracketView.reject')}
                </button>
              </div>
            </div>
          )}

          {/* Participant (non-organizer): report a score from your own device */}
          {!canEdit && isParticipant && (
            hasReport ? (
              <div className="px-3 py-2 border-t border-border">
                <p className="font-mono-label text-muted-foreground text-[10px]">
                  {t('tournaments.bracketView.reported', { a: match.reported_score_a, b: match.reported_score_b })}
                  {' · '}{t('tournaments.bracketView.awaitingConfirm')}
                </p>
                {match.reported_by === user?.id && (
                  <button
                    onClick={() => onReject(match.id)}
                    className="mt-1 text-[10px] font-mono-label text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {t('tournaments.bracketView.withdraw')}
                  </button>
                )}
              </div>
            ) : reporting ? (
              <div className="px-3 py-2 border-t border-border bg-muted/50 flex items-center gap-1">
                <input
                  type="number" min={0} value={repA}
                  onChange={(e) => setRepA(Number(e.target.value))}
                  className="w-10 h-6 text-center text-sm bg-input border border-border focus:border-accent outline-none font-mono"
                />
                <span className="text-muted-foreground">–</span>
                <input
                  type="number" min={0} value={repB}
                  onChange={(e) => setRepB(Number(e.target.value))}
                  className="w-10 h-6 text-center text-sm bg-input border border-border focus:border-accent outline-none font-mono"
                />
                <button
                  onClick={submitReport}
                  disabled={saving}
                  className="flex-1 text-xs font-mono-label py-1 bg-accent text-accent-foreground hover:bg-accent/90 disabled:opacity-40 transition-colors"
                >
                  {saving ? '...' : t('tournaments.bracketView.submitReport')}
                </button>
                <button
                  onClick={() => setReporting(false)}
                  className="px-2 text-xs font-mono-label py-1 border border-border text-muted-foreground hover:text-foreground transition-colors"
                >
                  ✕
                </button>
              </div>
            ) : (
              <div className="px-3 py-2 border-t border-border">
                <button
                  onClick={() => setReporting(true)}
                  className="w-full text-xs font-mono-label py-1 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {t('tournaments.bracketView.reportScore')}
                </button>
              </div>
            )
          )}
        </>
      )}

      {isDone && (
        <div className="px-3 py-1.5 border-t border-border">
          <span className="font-mono-label text-accent text-[10px]">
            {t('tournaments.bracketView.winner', { name: teamA?.id === match.winner_id ? teamA?.team_name : teamB?.team_name })}
          </span>
        </div>
      )}
    </div>
  )
}

export default function TournamentBracket({ tournament, onUpdate }: TournamentBracketProps) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const canEdit = user?.id === tournament.organizer_id || user?.role === 'admin'

  const rounds = Array.from(new Set(tournament.matches.map((m) => m.round_number))).sort()

  const matchesByRound = (rn: number) =>
    tournament.matches
      .filter((m) => m.round_number === rn)
      .sort((a, b) => a.match_number - b.match_number)

  const handleMatchUpdate = async (
    matchId: number,
    data: { score_a?: number; score_b?: number; status?: string; winner_id?: number }
  ) => {
    await tournamentsApi.updateMatch(tournament.id, matchId, data)
    onUpdate()
  }

  const handleReport = async (matchId: number, data: { score_a: number; score_b: number }) => {
    await tournamentsApi.reportMatch(tournament.id, matchId, data)
    onUpdate()
  }

  const handleConfirm = async (matchId: number) => {
    await tournamentsApi.confirmMatch(tournament.id, matchId)
    onUpdate()
  }

  const handleReject = async (matchId: number) => {
    await tournamentsApi.rejectReport(tournament.id, matchId)
    onUpdate()
  }

  if (tournament.matches.length === 0) {
    return (
      <div className="text-center py-16 border border-border">
        <p className="font-mono-label text-muted-foreground mb-2">{t('tournaments.bracketView.noBracketsGenerated')}</p>
        <p className="text-sm text-muted-foreground">
          {t('tournaments.bracketView.addTeamsHint')}
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto scrollbar-thin pb-4">
      <div className="flex gap-8 items-start min-w-max">
        {rounds.map((rn) => {
          const roundMatches = matchesByRound(rn)
          const roundName = roundMatches[0]?.round ?? ''

          return (
            <div key={rn} className="flex flex-col gap-2">
              {/* Round header */}
              <div className="font-mono-label text-accent text-center pb-2 border-b border-border">
                {t(`roundLabels.${roundName}`, roundName.toUpperCase())}
              </div>

              {/* Matches */}
              <div
                className="flex flex-col"
                style={{ gap: `${Math.pow(2, rn - 1) * 8}px` }}
              >
                {roundMatches.map((match) => (
                  <MatchCard
                    key={match.id}
                    match={match}
                    canEdit={canEdit}
                    onUpdate={handleMatchUpdate}
                    onReport={handleReport}
                    onConfirm={handleConfirm}
                    onReject={handleReject}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
