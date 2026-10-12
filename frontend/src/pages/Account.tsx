import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, KeyRound, Mail, Pencil, Trash2 } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'
import { FieldMessage, PhoneInput, type PhoneValue } from '@/components/ContactInputs'
import { CodeEntry } from '@/components/CodeEntry'
import { PasswordField } from '@/components/PasswordField'
import { Badge, Button, Card, ErrorNote, Input, Label, PageHeader } from '@/components/ui'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useLang } from '@/lib/patient'
import { emailValid } from '@/lib/phone'
import { codeComplete, fmtDate } from '@/lib/utils'
import type { Account, CodeSent } from '@/lib/types'
import { cn } from '@/lib/utils'

export default function AccountPage() {
  const { t } = useTranslation()
  const { account } = useAuth()
  const { hash } = useLocation()
  useEffect(() => {
    if (hash === '#email') document.getElementById('email')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [hash])
  if (!account) return null
  return (
    <div className="space-y-6">
      <PageHeader title={t('account.title')} subtitle={t('account.subtitle')} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AccountDetails account={account} />
        <EmailSettings account={account} />
        <ChangePassword />
        <NotificationSettings account={account} />
        <DeleteAccount />
      </div>
    </div>
  )
}

function AccountDetails({ account }: { account: Account }) {
  const { t } = useTranslation()
  const lang = useLang()
  const qc = useQueryClient()
  const [first, setFirst] = useState(() => splitName(account.name)[0])
  const [last, setLast] = useState(() => splitName(account.name)[1])
  const [phone, setPhone] = useState<PhoneValue>({ value: account.phone ?? '', valid: true })
  const [tried, setTried] = useState(false)
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      api.updateMe({
        name: `${first.trim()} ${last.trim()}`,
        ...(phone.value !== (account.phone ?? '') ? { phone: phone.value } : {}),
      }),
    onSuccess: (acc) => {
      qc.setQueryData(['me'], acc)
      setSaved(true)
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTried(true)
    setSaved(false)
    if (first.trim() && last.trim() && phone.valid) save.mutate()
  }

  return (
    <Card className="p-6">
      <p className="font-semibold text-slate-900">{t('profiles.details')}</p>
      <p className="mb-5 text-sm text-slate-500">
        {t('profiles.member_since', { date: fmtDate(account.created_at, lang) })}
      </p>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
          <Label>{t('profiles.phone')}</Label>
          <PhoneInput value={account.phone ?? ''} onChange={setPhone} showErrors={tried} />
          <FieldMessage>{t('profiles.phone_hint')}</FieldMessage>
        </div>
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
