import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, KeyRound, Mail, Pencil, Phone, ShieldCheck, Trash2, UserCog, UserPlus, UserRound, Users } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { FieldMessage, LoginInput, type LoginValue } from '@/components/ContactInputs'
import { CodeEntry } from '@/components/CodeEntry'
import { PasswordField } from '@/components/PasswordField'
import { emptyProfile, ProfileForm, type ProfileValues } from '@/components/ProfileForm'
import { Badge, Button, Card, ErrorNote, Input, Label, PageHeader } from '@/components/ui'
import { LANGUAGES } from '@/i18n'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useLang, usePatient } from '@/lib/patient'
import { emailValid, formatPhone } from '@/lib/phone'
import { ageOf, codeComplete, fmtDate } from '@/lib/utils'
import type { Account, CodeSent, Patient } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Avatar } from '@/components/Avatar'

export default function Profiles() {
  const { t } = useTranslation()
  const { patients } = usePatient()
  const me = patients.find((p) => p.relationship === 'self')
  const family = patients.filter((p) => p !== me)
  const indexOf = (p: Patient) => patients.indexOf(p)

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('profiles.title')}
        subtitle={t('profiles.subtitle')}
        action={
          <Link to="/profiles/new">
            <Button>
              <UserPlus className="h-4 w-4" />
              {t('profile.add')}
            </Button>
          </Link>
        }
      />

      {me && (
        <section>
          <SectionTitle icon={<UserRound className="h-4 w-4" />} title={t('profiles.you')} sub={t('profiles.you_sub')} />
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            <ProfileCard patient={me} index={indexOf(me)} isSelf />
          </div>
        </section>
      )}

      <section>
        <SectionTitle icon={<Users className="h-4 w-4" />} title={t('profiles.family')} count={family.length} sub={t('profiles.family_sub')} />
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {family.map((p) => (
            <ProfileCard key={p.id} patient={p} index={indexOf(p)} />
          ))}
          <Link
            to="/profiles/new"
            className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-200 p-6 text-center text-sm font-medium text-slate-500 transition-colors hover:border-brand-300 hover:bg-brand-50/50 hover:text-brand-700"
          >
            <UserPlus className="h-6 w-6" />
            {t('profile.add')}
            {family.length === 0 && <span className="max-w-64 text-xs font-normal text-slate-400">{t('profiles.family_empty')}</span>}
          </Link>
        </div>
      </section>

      <AccountSettings />
    </div>
  )
}

function SectionTitle({ icon, title, sub, count }: { icon: ReactNode; title: string; sub: string; count?: number }) {
  return (
    <div className="mb-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-500 uppercase">
        {icon}
        {title}
        {count !== undefined && <span className="font-normal text-slate-400">· {count}</span>}
      </h2>
      <p className="mt-0.5 text-sm text-slate-500">{sub}</p>
    </div>
  )
}

function ProfileCard({ patient: p, index, isSelf = false }: { patient: Patient; index: number; isSelf?: boolean }) {
  const { t } = useTranslation()
  const lang = useLang()
  const qc = useQueryClient()
  const nav = useNavigate()
  const { patient: active, select, patients } = usePatient()
  const [mode, setMode] = useState<'view' | 'edit' | 'delete'>('view')

  const save = useMutation({
    mutationFn: (v: ProfileValues) => api.updatePatient(p.id, v),
    onSuccess: (updated) => {
      qc.setQueryData<Patient[]>(['patients'], (list) => list?.map((x) => (x.id === updated.id ? updated : x)))
      qc.invalidateQueries({ queryKey: ['profile', p.id] })
      qc.removeQueries({ queryKey: ['patientSummary', p.id] })
      setMode('view')
    },
  })
  const remove = useMutation({
    mutationFn: () => api.deletePatient(p.id),
    onSuccess: async () => {
      const next = patients.find((x) => x.id !== p.id)
      if (active?.id === p.id && next) select(next.id)
      qc.removeQueries({ predicate: (q) => q.queryKey.includes(p.id) })
      await qc.invalidateQueries({ queryKey: ['patients'] })
    },
  })

  const isActive = active?.id === p.id
  const age = ageOf(p.birth_date)
  const language = LANGUAGES.find((l) => l.code === p.preferred_language)
  const details = [
    age !== null ? t('profiles.age', { count: age }) : null,
    p.gender ? t(`onboarding.${p.gender}`) : null,
  ].filter(Boolean)

  if (mode === 'edit')
    return (
      <Card className="p-6 md:col-span-2 2xl:col-span-3">
        <div className="mb-5 flex items-center gap-3">
          <Avatar name={p.name} index={index} />
          <div>
            <p className="font-semibold text-slate-900">{t('profiles.edit_title', { name: p.name })}</p>
            <p className="text-sm text-slate-500">{t('profiles.edit_sub')}</p>
          </div>
        </div>
        <ProfileForm
          autoFocus
          askRelationship={!isSelf}
          initial={emptyProfile(lang, p)}
          submitLabel={t('common.save')}
          pending={save.isPending}
          error={save.error}
          onSubmit={(v) => save.mutate(v)}
          onCancel={() => {
            save.reset()
            setMode('view')
          }}
        />
      </Card>
    )

  return (
    <Card className={cn('flex flex-col p-5 transition-shadow hover:shadow-md', isActive && 'ring-2 ring-brand-300')}>
      <div className="flex items-start gap-3">
        <Avatar name={p.name} index={index} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-slate-900">{p.name}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {p.relationship && (
              <Badge className={isSelf ? 'bg-brand-50 text-brand-800 ring-brand-200' : ''}>
                {t(`relationship.${p.relationship}`)}
              </Badge>
            )}
            {isActive && <Badge className="bg-emerald-50 text-emerald-700 ring-emerald-200">{t('profiles.viewing')}</Badge>}
          </div>
        </div>
      </div>

      <dl className="mt-4 space-y-1.5 text-sm text-slate-600">
        {details.length > 0 && <Row>{details.join(' · ')}</Row>}
        {p.phone && (
          <Row>
            <Phone className="h-3.5 w-3.5 text-slate-400" />
            {formatPhone(p.phone)}
          </Row>
        )}
        {language && <Row>{t('profiles.speaks', { language: language.label })}</Row>}
        {p.abha_address && (
          <Row>
            <span className="inline-flex items-center gap-1 text-brand-700">
              <ShieldCheck className="h-3.5 w-3.5" />
              {p.abha_address}
            </span>
          </Row>
        )}
      </dl>

      {mode === 'delete' ? (
        <div className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200">
          <p>{t('profiles.delete_confirm', { name: p.name })}</p>
          {remove.error && <p className="mt-2 font-medium">{(remove.error as Error).message}</p>}
          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              <Trash2 className="h-4 w-4" />
              {t('profiles.remove')}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setMode('view')}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-auto flex flex-wrap gap-2 pt-4">
          {!isActive && (
            <Button
              size="sm"
              onClick={() => {
                select(p.id)
                nav('/')
              }}
            >
              {t('profiles.open')}
            </Button>
          )}
          <Button size="sm" variant="secondary" onClick={() => setMode('edit')}>
            <Pencil className="h-3.5 w-3.5" />
            {t('common.edit')}
          </Button>
          {!isSelf && (
            <Button size="sm" variant="ghost" className="text-slate-500 hover:text-red-600" onClick={() => setMode('delete')}>
              <Trash2 className="h-3.5 w-3.5" />
              {t('profiles.remove')}
            </Button>
          )}
          {isSelf && <p className="w-full text-xs text-slate-400">{t('profiles.self_note')}</p>}
        </div>
      )}
    </Card>
  )
}

function Row({ children }: { children: ReactNode }) {
  return <div className="flex items-center gap-1.5">{children}</div>
}

function AccountSettings() {
  const { t } = useTranslation()
  const { account } = useAuth()
  const { hash } = useLocation()
  useEffect(() => {
    if (hash === '#email') document.getElementById('email')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [hash])
  if (!account) return null
  return (
    <section>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-500 uppercase">
        <UserCog className="h-4 w-4" />
        {t('profiles.account')}
      </h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <AccountDetails account={account} />
        <EmailSettings account={account} />
        <ChangePassword />
        <NotificationSettings account={account} />
        <DeleteAccount />
      </div>
    </section>
  )
}

function AccountDetails({ account }: { account: Account }) {
  const { t } = useTranslation()
  const lang = useLang()
  const qc = useQueryClient()
  const [first, setFirst] = useState(() => splitName(account.name)[0])
  const [last, setLast] = useState(() => splitName(account.name)[1])
  const [login, setLogin] = useState<LoginValue>({ value: account.login, valid: true, kind: account.login.includes('@') ? 'email' : 'phone' })
  const [password, setPassword] = useState('')
  const [tried, setTried] = useState(false)
  const [saved, setSaved] = useState(false)

  const loginChanged = login.value !== account.login
  const save = useMutation({
    mutationFn: () =>
      api.updateMe({
        name: `${first.trim()} ${last.trim()}`,
        ...(loginChanged ? { login: login.value, current_password: password } : {}),
      }),
    onSuccess: (acc) => {
      qc.setQueryData(['me'], acc)
      setPassword('')
      setSaved(true)
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTried(true)
    setSaved(false)
    if (first.trim() && last.trim() && login.valid && (!loginChanged || password)) save.mutate()
  }

  return (
    <Card className="p-6">
      <p className="font-semibold text-slate-900">{t('profiles.details')}</p>
      <p className="mb-5 text-sm text-slate-500">
        {t('profiles.member_since', { date: fmtDate(account.created_at, lang) })}
      </p>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <Label>{t('auth.first_name')}</Label>
            <Input value={first} maxLength={50} onChange={(e) => setFirst(e.target.value)} autoComplete="given-name" />
            <FieldMessage error={tried && !first.trim() ? t('contact.required') : null} />
          </label>
          <label className="block">
            <Label>{t('auth.last_name')}</Label>
            <Input value={last} maxLength={50} onChange={(e) => setLast(e.target.value)} autoComplete="family-name" />
            <FieldMessage error={tried && !last.trim() ? t('contact.required') : null} />
          </label>
        </div>
        <div>
          <Label>{t('auth.login')}</Label>
          <LoginInput initial={account.login} onChange={setLogin} showErrors={tried} hint={t('profiles.login_hint')} />
        </div>
        {loginChanged && login.valid && (
          <PasswordField
            label={t('profiles.current_password')}
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            error={tried && !password ? t('profiles.password_needed') : null}
            hint={t('profiles.password_needed')}
          />
        )}
        {save.error && <ErrorNote error={save.error} />}
        <div className="flex items-center gap-3">
          <Button type="submit" loading={save.isPending}>
            {t('common.save')}
          </Button>
          {saved && <FieldMessage ok>{t('profiles.saved')}</FieldMessage>}
        </div>
      </form>
    </Card>
  )
}

function EmailSettings({ account }: { account: Account }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(!account.email_verified)
  const [email, setEmail] = useState(account.email_verified ? '' : (account.email ?? ''))
  const [password, setPassword] = useState('')
  const [sent, setSent] = useState<CodeSent | null>(null)
  const [sends, setSends] = useState(0)
  const [code, setCode] = useState('')
  const [tried, setTried] = useState(false)
  const changing = account.email_verified

  const start = useMutation({
    mutationFn: () => api.emailStart({ email: email.trim(), ...(changing ? { current_password: password } : {}) }),
    onSuccess: (s) => {
      setSent(s)
      setSends((n) => n + 1)
      setCode('')
      setTried(false)
    },
  })
  const verify = useMutation({
    mutationFn: () => api.emailVerify(code),
    onSuccess: (acc) => {
      qc.setQueryData(['me'], acc)
      setSent(null)
      setEditing(false)
      setPassword('')
    },
  })
  const cancel = () => {
    setSent(null)
    setEditing(!account.email_verified)
    start.reset()
    verify.reset()
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTried(true)
    if (sent) {
      if (codeComplete(code)) verify.mutate()
    } else if (emailValid(email) && (!changing || password)) start.mutate()
  }

  return (
    <Card id="email" className="scroll-mt-24 p-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold text-slate-900">
          <Mail className="h-4 w-4 text-slate-400" />
          {t('email.title')}
        </p>
        {account.email_verified ? (
          <Badge className="bg-emerald-50 text-emerald-700 ring-emerald-200">{t('email.verified')}</Badge>
        ) : (
          <Badge className="bg-amber-50 text-amber-800 ring-amber-200">{t('email.not_verified')}</Badge>
        )}
      </div>
      <p className="mb-5 text-sm text-slate-500">{t('email.sub')}</p>

      {!editing ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-medium break-all text-slate-800">{account.email}</p>
          <Button variant="secondary" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" />
            {t('email.change')}
          </Button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          {!sent ? (
            <>
              <label className="block">
                <Label>{changing ? t('email.new') : t('auth.email')}</Label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
                <FieldMessage error={tried && !emailValid(email) ? t('contact.email_invalid') : null} />
              </label>
              {changing && (
                <PasswordField
                  label={t('profiles.current_password')}
                  value={password}
                  onChange={setPassword}
                  autoComplete="current-password"
                  error={tried && !password ? t('email.password_needed') : null}
                />
              )}
            </>
          ) : (
            <CodeEntry
              key={sends}
              sent={sent}
              value={code}
              onChange={setCode}
              onResend={() => start.mutate()}
              resending={start.isPending}
              showErrors={tried}
            />
          )}
          {(start.error || verify.error) && <ErrorNote error={verify.error ?? start.error} />}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" loading={sent ? verify.isPending : start.isPending}>
              {sent ? t('email.verify') : t('auth.send_code')}
            </Button>
            {(sent || changing) && (
              <Button type="button" variant="ghost" onClick={cancel}>
                {t('common.cancel')}
              </Button>
            )}
          </div>
        </form>
      )}
    </Card>
  )
}

function NotificationSettings({ account }: { account: Account }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: (patch: Partial<Record<'notify_security' | 'notify_medicines' | 'notify_weekly', boolean>>) => api.updateMe(patch),
    onSuccess: (acc) => qc.setQueryData(['me'], acc),
  })
  const items = [
    { key: 'security', field: 'notify_security' },
    { key: 'medicines', field: 'notify_medicines' },
    { key: 'weekly', field: 'notify_weekly' },
  ] as const
  const off = !account.email_verified

  return (
    <Card className="p-6">
      <p className="flex items-center gap-2 font-semibold text-slate-900">
        <Bell className="h-4 w-4 text-slate-400" />
        {t('notify.title')}
      </p>
      <p className="mb-4 text-sm text-slate-500">{off ? t('notify.needs_email') : t('notify.sub')}</p>
      <div className="divide-y divide-slate-100">
        {items.map(({ key, field }) => {
          const on = account.notify[key]
          return (
            <div key={key} className="flex items-center justify-between gap-4 py-3">
              <div>
                <p className="text-sm font-medium text-slate-800">{t(`notify.${key}`)}</p>
                <p className="text-xs text-slate-500">{t(`notify.${key}_sub`)}</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-label={t(`notify.${key}`)}
                disabled={off || save.isPending}
                onClick={() => save.mutate({ [field]: !on })}
                className={cn(
                  'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:outline-none disabled:opacity-50',
                  on && !off ? 'bg-brand-600' : 'bg-slate-300',
                )}
              >
                <span
                  className={cn(
                    'theme-fixed inline-block h-5 w-5 rounded-full bg-white shadow transition-transform',
                    on && !off ? 'translate-x-5' : 'translate-x-0.5',
                  )}
                />
              </button>
            </div>
          )
        })}
      </div>
      {save.error && <ErrorNote error={save.error} />}
    </Card>
  )
}

/** "Sai Krishna Reddy" -> ["Sai Krishna", "Reddy"]: accounts store one name, the last word is the last name. */
function splitName(name: string): [string, string] {
  const words = name.trim().split(/\s+/)
  return words.length > 1 ? [words.slice(0, -1).join(' '), words[words.length - 1]] : [words[0] ?? '', '']
}

function ChangePassword() {
  const { t } = useTranslation()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [tried, setTried] = useState(false)
  const change = useMutation({
    mutationFn: () => api.changePassword({ current_password: form.current, new_password: form.next }),
    onSuccess: () => {
      setForm({ current: '', next: '', confirm: '' })
      setTried(false)
    },
  })
  const short = form.next.length > 0 && form.next.length < 8
  const mismatch = form.confirm.length > 0 && form.confirm !== form.next
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTried(true)
    change.reset()
    if (form.current && form.next.length >= 8 && form.next === form.confirm) change.mutate()
  }
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Card className="p-6">
      <p className="flex items-center gap-2 font-semibold text-slate-900">
        <KeyRound className="h-4 w-4 text-slate-400" />
        {t('profiles.change_password')}
      </p>
      <p className="mb-5 text-sm text-slate-500">{t('profiles.change_password_sub')}</p>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <PasswordField
          label={t('profiles.current_password')}
          value={form.current}
          onChange={set('current')}
          autoComplete="current-password"
          error={tried && !form.current ? t('contact.required') : null}
        />
        <PasswordField
          label={t('profiles.new_password')}
          value={form.next}
          onChange={set('next')}
          autoComplete="new-password"
          error={short || (tried && !form.next) ? t('auth.password_hint') : null}
        />
        <PasswordField
          label={t('profiles.confirm_password')}
          value={form.confirm}
          onChange={set('confirm')}
          autoComplete="new-password"
          error={mismatch || (tried && form.confirm !== form.next) ? t('profiles.password_mismatch') : null}
        />
        {change.error && <ErrorNote error={change.error} />}
        <div className="flex items-center gap-3">
          <Button type="submit" variant="secondary" loading={change.isPending}>
            {t('profiles.change_password')}
          </Button>
          {change.isSuccess && <FieldMessage ok>{t('profiles.password_changed')}</FieldMessage>}
        </div>
      </form>
    </Card>
  )
}

function DeleteAccount() {
  const { t } = useTranslation()
  const { signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const remove = useMutation({ mutationFn: () => api.deleteAccount(password), onSuccess: signOut })

  return (
    <Card className="p-6 ring-red-100 lg:col-span-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-red-700">{t('profiles.delete_account')}</p>
          <p className="text-sm text-slate-500">{t('profiles.delete_account_sub')}</p>
        </div>
        {!open && (
          <Button variant="danger" onClick={() => setOpen(true)}>
            <Trash2 className="h-4 w-4" />
            {t('profiles.delete_account')}
          </Button>
        )}
      </div>
      {open && (
        <form
          className="mt-4 flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (password) remove.mutate()
          }}
        >
          <div className="w-full max-w-xs">
            <PasswordField label={t('profiles.current_password')} value={password} onChange={setPassword} autoComplete="current-password" />
          </div>
          <Button type="submit" variant="danger" loading={remove.isPending} disabled={!password}>
            {t('profiles.delete_forever')}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            {t('common.cancel')}
          </Button>
          {remove.error && (
            <div className="w-full">
              <ErrorNote error={remove.error} />
            </div>
          )}
        </form>
      )}
    </Card>
  )
}
