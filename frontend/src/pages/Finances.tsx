import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { useAppConfig } from '../contexts/AppConfigContext'
import { expensesApi, eventsApi, usersApi } from '../lib/api'
import { useToast } from '../contexts/ToastContext'
import { Expense, ProRataResult, LanEvent, User, EXPENSE_CATEGORIES } from '../types'
import i18n from '../i18n'
import { buildCsv, csvFormatFor, downloadCsv, formatCsvNumber } from '../lib/csv'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Badge from '../components/ui/Badge'
import ProRataTable from '../components/ProRataTable'
import { Plus, Trash2, Edit2, X, Check, DollarSign, Download, AlertTriangle } from 'lucide-react'

// Amounts and percentages in the member's Excel format (decimal comma in
// French), so they land as numbers a treasurer can sum, not as text.
function exportProRataCSV(proRata: ProRataResult, currency: string) {
  const fmt = csvFormatFor(i18n.language)
  const rows = [
    [i18n.t('finances.csv.player'), i18n.t('finances.csv.nights'), i18n.t('finances.csv.percentage'), i18n.t('finances.csv.amount', { currency })],
    ...proRata.shares.map((s) => [
      s.username,
      String(s.nights),
      formatCsvNumber(s.percentage, 1, fmt) + '%',
      formatCsvNumber(s.amount, 2, fmt),
    ]),
    [
      i18n.t('finances.csv.total'),
      '',
      formatCsvNumber(proRata.shares.reduce((sum, s) => sum + s.percentage, 0), 1, fmt) + '%',
      formatCsvNumber(proRata.total_expenses, 2, fmt),
    ],
  ]
  downloadCsv(buildCsv(rows, fmt), 'prorata.csv')
}

interface ExpenseForm {
  description: string
  amount: string
  category: string
  date: string
  event_id: string
  paid_by: string
}

function ExpenseRow({
  expense,
  canEdit,
  onDelete,
  onEdit,
}: {
  expense: Expense
  canEdit: boolean
  onDelete: (id: number) => void
  onEdit: (expense: Expense) => void
}) {
  const { t } = useTranslation()
  const { currency } = useAppConfig()
  const categoryColors: Record<string, string> = {
    food: 'warning',
    drinks: 'accent',
    equipment: 'default',
    accommodation: 'success',
    transport: 'muted',
    games: 'danger',
    prizes: 'accent',
    general: 'muted',
  }

  return (
    <div className="grid grid-cols-12 gap-3 px-4 py-3 items-center border-b border-border last:border-0 hover:bg-muted/30 transition-colors group">
      <div className="col-span-4 flex items-center gap-3">
        <div className="w-1 h-8 bg-accent flex-shrink-0" />
        <span className="text-sm font-semibold text-foreground truncate">
          {expense.description}
        </span>
      </div>
      <div className="col-span-2">
        <Badge variant={(categoryColors[expense.category] as any) ?? 'muted'}>
          {t(`categories.${expense.category}`, expense.category)}
        </Badge>
      </div>
      <div className="col-span-2 font-mono-label text-muted-foreground">
        {expense.date}
      </div>
      <div className="col-span-2 font-mono-label text-muted-foreground text-xs">
        {expense.payer?.username ?? expense.creator?.username}
      </div>
      <div className="col-span-1 text-right">
        <span className="font-mono font-black text-foreground tabular-nums">
          {expense.amount.toFixed(2)}{currency}
        </span>
      </div>
      <div className="col-span-1 flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {canEdit && (
          <>
            <button
              onClick={() => onEdit(expense)}
              className="p-1 text-muted-foreground hover:text-foreground transition-colors"
              title={t('common.edit')}
            >
              <Edit2 size={12} strokeWidth={1.5} />
            </button>
            <button
              onClick={() => onDelete(expense.id)}
              className="p-1 text-muted-foreground hover:text-red-400 transition-colors"
              title={t('common.delete')}
            >
              <Trash2 size={12} strokeWidth={1.5} />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

export default function Finances() {
  const { isTreasurer, user } = useAuth()
  const { currency } = useAppConfig()
  const { t } = useTranslation()
  const { push } = useToast()
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [events, setEvents] = useState<LanEvent[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [proRata, setProRata] = useState<ProRataResult | null>(null)
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingExpense, setEditingExpense] = useState<Expense | null>(null)
  const [activeTab, setActiveTab] = useState<'expenses' | 'prorata'>('expenses')
  const [unassignedCount, setUnassignedCount] = useState(0)
  const [loading, setLoading] = useState(true)

  const defaultPaidBy = user ? String(user.id) : ''
  const formDefaults = () => ({
    category: 'general',
    date: new Date().toISOString().split('T')[0],
    // Default to the event in view. Splits are scoped by event, so an expense
    // left untagged counts towards nobody's — it should take a deliberate
    // choice to leave it out, not be the path of least resistance.
    event_id: selectedEventId ? String(selectedEventId) : '',
    paid_by: defaultPaidBy,
  })

  const { register, handleSubmit, reset, setValue, formState: { errors, isSubmitting } } =
    useForm<ExpenseForm>({ defaultValues: formDefaults() })

  // Reloads keep the event in view; only the first load lets the server
  // pick (the one in progress, or the one that just ended).
  const loadData = async (eventId: number | null = selectedEventId) => {
    const [exp, evts, usrs, pr, unassigned] = await Promise.all([
      expensesApi.getAll(),
      eventsApi.getAll(),
      usersApi.getAll(),
      expensesApi.getProRata(eventId ?? undefined),
      expensesApi.getUnassignedCount(),
    ])
    setExpenses(exp)
    setEvents(evts)
    setUsers(usrs)
    setProRata(pr)
    setSelectedEventId(pr.event_id)
    setUnassignedCount(unassigned)
    setLoading(false)
  }

  useEffect(() => { loadData(null) }, [])

  const handleEventChange = async (eventId: number) => {
    setSelectedEventId(eventId)
    const pr = await expensesApi.getProRata(eventId)
    setProRata(pr)
  }

  const reloadProRata = async () => {
    const eventId = proRata?.event_id ?? selectedEventId ?? undefined
    const pr = await expensesApi.getProRata(eventId ?? undefined)
    setProRata(pr)
  }

  const onSubmit = async (data: ExpenseForm) => {
    const payload = {
      description: data.description,
      amount: parseFloat(data.amount),
      category: data.category,
      date: data.date,
      event_id: data.event_id ? Number(data.event_id) : null,
      paid_by: data.paid_by ? Number(data.paid_by) : null,
    }
    if (editingExpense) {
      await expensesApi.update(editingExpense.id, payload)
    } else {
      await expensesApi.create(payload)
    }
    await loadData()
    reset(formDefaults())
    setShowForm(false)
    setEditingExpense(null)
    push(t('finances.expenseSaved'))
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t('finances.deleteExpenseConfirm'))) return
    await expensesApi.delete(id)
    await loadData()
  }

  const handleEdit = (expense: Expense) => {
    setEditingExpense(expense)
    setValue('description', expense.description)
    setValue('amount', String(expense.amount))
    setValue('category', expense.category)
    setValue('date', expense.date)
    setValue('event_id', expense.event_id ? String(expense.event_id) : '')
    setValue('paid_by', String(expense.paid_by ?? expense.created_by))
    setShowForm(true)
  }

  const cancelForm = () => {
    setShowForm(false)
    setEditingExpense(null)
    reset(formDefaults())
  }

  const total = expenses.reduce((s, e) => s + e.amount, 0)

  return (
    <main className="max-w-6xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div>
          <div className="font-mono-label text-accent mb-3">{t('finances.tagline')}</div>
          <h1 className="text-5xl lg:text-6xl font-black tracking-tighter text-foreground leading-none">
            {t('finances.heroLine1')}
            <br />
            <span className="text-accent">{t('finances.heroLine2')}</span>
          </h1>
        </div>
        <div className="text-right">
          <p className="font-mono-label text-muted-foreground">{t('finances.totalBudget')}</p>
          <p className="text-4xl font-black tracking-tighter text-foreground">
            {total.toFixed(2)}
            <span className="text-accent ml-1">{currency}</span>
          </p>
        </div>
      </div>

      {/* Expenses tied to no event count towards no split, so say so rather
          than letting them quietly vanish from the maths. */}
      {unassignedCount > 0 && (
        <div className="border border-yellow-700 bg-yellow-950/20 p-4 mb-8 flex items-start gap-3">
          <AlertTriangle size={16} strokeWidth={1.5} className="text-yellow-400 shrink-0 mt-0.5" />
          <div>
            <p className="font-mono-label text-yellow-400 mb-1">{t('finances.unassignedTitle')}</p>
            <p className="text-sm text-muted-foreground">
              {t('finances.unassignedBody', { count: unassignedCount })}
            </p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-border mb-8">
        {(['expenses', 'prorata'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-6 py-3 font-mono-label transition-colors border-b-2 -mb-px ${
              activeTab === tab
                ? 'text-accent border-accent'
                : 'text-muted-foreground border-transparent hover:text-foreground'
            }`}
          >
            {tab === 'expenses' ? t('finances.tabExpenses') : t('finances.tabProrata')}
          </button>
        ))}
      </div>

      {activeTab === 'expenses' && (
        <div>
          {/* Add expense form */}
          {isTreasurer && !showForm && (
            <div className="mb-6">
              {/* reset first: the form's defaults were captured before the
                  current event was known, so event_id would still be blank. */}
              <Button onClick={() => { reset(formDefaults()); setShowForm(true) }}>
                <Plus size={14} strokeWidth={2} />
                {t('finances.addExpense')}
              </Button>
            </div>
          )}

          {showForm && (
            <div className="border border-accent bg-card p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <p className="font-mono-label text-accent">
                  {editingExpense ? t('finances.editExpense') : t('finances.newExpense')}
                </p>
                <button onClick={cancelForm} className="text-muted-foreground hover:text-foreground">
                  <X size={14} />
                </button>
              </div>

              <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="lg:col-span-2">
                  <Input
                    label={t('finances.descriptionLabel')}
                    placeholder={t('finances.descriptionPlaceholder')}
                    {...register('description', { required: t('finances.descriptionRequired') })}
                    error={errors.description?.message}
                  />
                </div>
                <Input
                  label={t('finances.amountLabel', { currency })}
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="42.00"
                  {...register('amount', { required: t('finances.amountRequired'), min: 0.01 })}
                  error={errors.amount?.message}
                />
                <Input
                  label={t('finances.dateLabel')}
                  type="date"
                  {...register('date', { required: true })}
                />

                <div>
                  <label className="font-mono-label text-muted-foreground block mb-1.5">{t('finances.categoryLabel')}</label>
                  <select
                    className="w-full h-12 px-4 bg-input border border-border text-foreground focus:border-accent outline-none transition-colors text-sm"
                    {...register('category')}
                  >
                    {EXPENSE_CATEGORIES.map((c) => (
                      <option key={c} value={c} className="bg-muted">
                        {t(`categories.${c}`, c)}
                      </option>
                    ))}
                  </select>
                </div>

                {events.length > 0 && (
                  <div>
                    <label className="font-mono-label text-muted-foreground block mb-1.5">{t('finances.eventLabel')}</label>
                    <select
                      className="w-full h-12 px-4 bg-input border border-border text-foreground focus:border-accent outline-none transition-colors text-sm"
                      {...register('event_id')}
                    >
                      <option value="" className="bg-muted">{t('finances.noEvent')}</option>
                      {events.map((ev) => (
                        <option key={ev.id} value={ev.id} className="bg-muted">
                          {ev.title}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div>
                  <label className="font-mono-label text-muted-foreground block mb-1.5">{t('finances.paidByLabel')}</label>
                  <select
                    className="w-full h-12 px-4 bg-input border border-border text-foreground focus:border-accent outline-none transition-colors text-sm"
                    {...register('paid_by')}
                  >
                    {users.map((u) => (
                      <option key={u.id} value={u.id} className="bg-muted">
                        {u.username}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="sm:col-span-2 flex gap-3 items-end">
                  <Button type="submit" disabled={isSubmitting}>
                    <Check size={14} />
                    {isSubmitting ? t('common.saving') : editingExpense ? t('finances.update') : t('finances.add')}
                  </Button>
                  <Button variant="ghost" type="button" onClick={cancelForm}>
                    {t('common.cancel')}
                  </Button>
                </div>
              </form>
            </div>
          )}

          {/* Expenses list */}
          {loading ? (
            <div className="space-y-px">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-14 bg-muted animate-pulse" />
              ))}
            </div>
          ) : expenses.length === 0 ? (
            <div className="text-center py-20 border border-border">
              <DollarSign size={32} strokeWidth={1} className="text-muted-foreground mx-auto mb-4" />
              <p className="font-mono-label text-muted-foreground">{t('finances.noExpensesYet')}</p>
              {isTreasurer && (
                <p className="text-sm text-muted-foreground mt-2">
                  {t('finances.clickToStart', { button: t('finances.addExpense') })}
                </p>
              )}
            </div>
          ) : (
            <div className="border border-border">
              {/* Table header */}
              <div className="grid grid-cols-12 gap-3 px-4 py-3 bg-muted border-b border-border">
                <div className="col-span-4 font-mono-label text-muted-foreground">{t('finances.tableDescription')}</div>
                <div className="col-span-2 font-mono-label text-muted-foreground">{t('finances.tableCategory')}</div>
                <div className="col-span-2 font-mono-label text-muted-foreground">{t('finances.tableDate')}</div>
                <div className="col-span-2 font-mono-label text-muted-foreground">{t('finances.tableBy')}</div>
                <div className="col-span-1 font-mono-label text-muted-foreground text-right">{t('finances.tableAmount')}</div>
                <div className="col-span-1" />
              </div>

              {expenses.map((expense) => (
                <ExpenseRow
                  key={expense.id}
                  expense={expense}
                  canEdit={isTreasurer}
                  onDelete={handleDelete}
                  onEdit={handleEdit}
                />
              ))}

              {/* Total row */}
              <div className="grid grid-cols-12 gap-3 px-4 py-4 bg-muted border-t-2 border-accent">
                <div className="col-span-11 font-mono-label text-accent">{t('finances.total')}</div>
                <div className="col-span-1 text-right font-mono font-black text-accent tabular-nums">
                  {total.toFixed(2)}{currency}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'prorata' && (
        <div>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            {events.length > 0 ? (
              <div className="flex items-center gap-2">
                <label className="font-mono-label text-muted-foreground">{t('finances.eventLabel')}</label>
                <select
                  className="h-10 px-3 bg-input border border-border text-foreground text-sm focus:border-accent outline-none transition-colors"
                  value={selectedEventId ?? ''}
                  onChange={(e) => handleEventChange(Number(e.target.value))}
                >
                  {events.map((ev) => (
                    <option key={ev.id} value={ev.id} className="bg-muted">
                      {ev.title}
                    </option>
                  ))}
                </select>
              </div>
            ) : <div />}
            {proRata && (
              <Button variant="ghost" onClick={() => exportProRataCSV(proRata, currency)}>
                <Download size={13} /> {t('finances.downloadCsv')}
              </Button>
            )}
          </div>
          {proRata ? (
            <ProRataTable data={proRata} onSettlementChange={reloadProRata} />
          ) : (
            <div className="text-center py-20 border border-border">
              <p className="font-mono-label text-muted-foreground animate-pulse">{t('common.loading')}</p>
            </div>
          )}
          <div className="mt-8 border-t border-border pt-6">
            <p className="text-xs text-muted-foreground leading-relaxed max-w-2xl">
              <span className="text-foreground font-semibold">{t('finances.howItWorksTitle')}</span> {t('finances.howItWorksBody')}
            </p>
          </div>
        </div>
      )}
    </main>
  )
}
