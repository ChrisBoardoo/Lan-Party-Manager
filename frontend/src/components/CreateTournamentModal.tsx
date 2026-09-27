import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { tournamentsApi, eventsApi } from '../lib/api'
import { LanEvent } from '../types'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import GamePicker, { GamePick } from './GamePicker'
import { Plus, Users, User as UserIcon, X } from 'lucide-react'

interface TournamentForm {
  bracket_type: string
  event_type: 'team' | 'individual'
  max_team_size: number
  event_id: string
}

export default function CreateTournamentModal({
  onClose,
  onCreate,
  presetEventId,
}: {
  onClose: () => void
  onCreate: () => void
  presetEventId?: number
}) {
  const { t } = useTranslation()
  const [events, setEvents] = useState<LanEvent[]>([])
  const { register, handleSubmit, watch, formState: { isSubmitting } } = useForm<TournamentForm>({
    defaultValues: { bracket_type: 'single_elimination', event_type: 'team', max_team_size: 2, event_id: '' },
  })
  const eventType = watch('event_type')
  const formEventId = watch('event_id')
  const [game, setGame] = useState<GamePick>({ game_name: '' })
  const [gameError, setGameError] = useState<string | undefined>()

  useEffect(() => {
    if (presetEventId == null) {
      eventsApi.getAll().then(setEvents)
    }
  }, [presetEventId])

  const onSubmit = async (data: TournamentForm) => {
    if (!game.game_name.trim()) {
      setGameError(t('tournaments.modal.gameNameRequired'))
      return
    }
    await tournamentsApi.create({
      ...data,
      game_name: game.game_name.trim(),
      game_id: game.game_id,
      max_team_size: data.event_type === 'individual' ? 1 : Number(data.max_team_size),
      event_id: presetEventId ?? (data.event_id ? Number(data.event_id) : undefined),
    })
    onCreate()
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-background/90 z-50 flex items-center justify-center p-6">
      <div className="bg-card border border-border w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b border-border">
          <p className="font-mono-label text-accent">{t('tournaments.modal.newTournament')}</p>
          <button onClick={onClose}><X size={16} className="text-muted-foreground hover:text-foreground" /></button>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <GamePicker
            value={game}
            onChange={(pick) => { setGame(pick); setGameError(undefined) }}
            eventId={presetEventId ?? (formEventId ? Number(formEventId) : undefined)}
            error={gameError}
          />
          <div>
            <label className="font-mono-label text-muted-foreground block mb-1.5">{t('tournaments.modal.eventTypeLabel')}</label>
            <div className="grid grid-cols-2 gap-2">
              {(['team', 'individual'] as const).map((type) => (
                <label
                  key={type}
                  className={`flex items-center justify-center gap-2 h-10 border cursor-pointer font-mono-label text-sm transition-colors ${
                    eventType === type
                      ? 'border-accent text-accent bg-accent/10'
                      : 'border-border text-muted-foreground hover:border-border-hover'
                  }`}
                >
                  <input type="radio" value={type} {...register('event_type')} className="sr-only" />
                  {type === 'team' ? <Users size={13} /> : <UserIcon size={13} />}
                  {type === 'team' ? t('tournaments.modal.eventTypeTeam') : t('tournaments.modal.eventTypeIndividual')}
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="font-mono-label text-muted-foreground block mb-1.5">{t('tournaments.modal.bracketTypeLabel')}</label>
            <select
              className="w-full h-12 px-4 bg-input border border-border text-foreground focus:border-accent outline-none text-sm"
              {...register('bracket_type')}
            >
              <option value="single_elimination">{t('tournaments.modal.bracketSingleElim')}</option>
              <option value="round_robin">{t('tournaments.modal.bracketRoundRobin')}</option>
              <option value="groups_then_knockout">{t('tournaments.modal.bracketGroupsKnockout')}</option>
            </select>
          </div>
          {eventType === 'team' && (
            <Input
              label={t('tournaments.modal.maxTeamSizeLabel')}
              type="number"
              min={2}
              max={10}
              {...register('max_team_size', { required: true, min: 2, max: 10 })}
            />
          )}
          {presetEventId == null && events.length > 0 && (
            <div>
              <label className="font-mono-label text-muted-foreground block mb-1.5">{t('tournaments.modal.eventLabel')}</label>
              <select
                className="w-full h-12 px-4 bg-input border border-border text-foreground focus:border-accent outline-none text-sm"
                {...register('event_id')}
              >
                <option value="">{t('tournaments.modal.noEvent')}</option>
                {events.map((e) => (
                  <option key={e.id} value={e.id}>{e.title}</option>
                ))}
              </select>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? t('tournaments.modal.creating') : <><Plus size={14} /> {t('common.create')}</>}
            </Button>
            <Button variant="ghost" type="button" onClick={onClose}>{t('common.cancel')}</Button>
          </div>
        </form>
      </div>
    </div>
  )
}
