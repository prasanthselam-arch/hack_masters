import { useMutation } from '@tanstack/react-query'
import { ArrowLeft, KeyRound, Lock, Mail } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { CodeEntry } from '@/components/CodeEntry'
import { FieldMessage, LoginInput, type LoginValue } from '@/components/ContactInputs'
import { AuroraPage, WelcomeHero } from '@/components/Hero'
import { LanguageSwitcher } from '@/components/Layout'
import { Disclaimer } from '@/components/medical'
import { PasswordField } from '@/components/PasswordField'
import { Button, Card, ErrorNote, Input, Label } from '@/components/ui'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { emailValid } from '@/lib/phone'
import type { Account, CodeSent } from '@/lib/types'
import { codeComplete } from '@/lib/utils'

type Mode = 'sign_in' | 'sign_up' | 'verify' | 'forgot' | 'reset'

const TITLES: Record<Mode, [string, string]> = {
  sign_in: ['auth.welcome', 'auth.welcome_sub'],
  sign_up: ['auth.create_title', 'auth.create_sub'],
  verify: ['auth.verify_title', 'auth.verify_sub'],
  forgot: ['auth.forgot_title', 'auth.forgot_sub'],
  reset: ['auth.reset_title', 'auth.reset_sub'],
}

export default function AuthPage() {
  const { t } = useTranslation()
  const { signedIn } = useAuth()
  const [mode, setMode] = useState<Mode>(() => (new URLSearchParams(window.location.search).has('forgot') ? 'forgot' : 'sign_in'))
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [login, setLogin] = useState<LoginValue>({ value: '', valid: false, kind: 'empty' })
  const [code, setCode] = useState('')
  const [sent, setSent] = useState<CodeSent | null>(null)
  const [sends, setSends] = useState(0)
  const [tried, setTried] = useState(false)

  const needsEmail = login.kind === 'phone'
  const email = needsEmail ? form.email.trim().toLowerCase() : login.value
  const codeSent = (next: Mode) => (s: CodeSent) => {
    setSent(s)
    setSends((n) => n + 1)
    setCode('')
    setTried(false)
    setMode(next)
  }
  const done = (acc: Account) => {
    window.history.replaceState(null, '', window.location.pathname)
    signedIn(acc)
  }

  const signIn = useMutation({ mutationFn: () => api.login({ login: login.value, password: form.password }), onSuccess: done })
  const startSignUp = useMutation({
    mutationFn: () =>
      api.registerStart({ name: form.name.trim(), login: login.value, email: needsEmail ? email : undefined, password: form.password }),
    onSuccess: codeSent('verify'),
  })
  const verify = useMutation({ mutationFn: () => api.registerVerify({ email: sent?.sent_to ?? email, code }), onSuccess: done })
  const forgot = useMutation({ mutationFn: () => api.forgotPassword(login.value), onSuccess: codeSent('reset') })
  const reset = useMutation({
    mutationFn: () => api.resetPassword({ login: login.value, code, password: form.password }),
    onSuccess: done,
  })
  const active = { sign_in: signIn, sign_up: startSignUp, verify, forgot, reset }[mode]
  const resend = mode === 'verify' ? startSignUp : forgot

  const go = (m: Mode) => {
    setMode(m)
    setTried(false)
    for (const mutation of [signIn, startSignUp, verify, forgot, reset]) mutation.reset()
    if (m === 'sign_in' || m === 'sign_up') setForm((f) => ({ ...f, password: '', confirm: '' }))
  }
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }))

  const passwordOk = form.password.length >= 8
  const valid = {
    sign_in: login.valid && !!form.password,
    sign_up: login.valid && !!form.name.trim() && passwordOk && (!needsEmail || emailValid(form.email)),
    verify: codeComplete(code),
    forgot: login.valid,
    reset: codeComplete(code) && passwordOk && form.confirm === form.password,
  }[mode]
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTried(true)
    if (valid) active.mutate()
  }

  const [title, sub] = TITLES[mode]
  const loginField = (autoFocus: boolean) => (
    <div>
      <Label>{t('auth.login')}</Label>
      <LoginInput initial={login.value} onChange={setLogin} showErrors={tried} autoFocus={autoFocus} hint={t('contact.login_hint')} />
    </div>
  )

  return (
    <AuroraPage>
      <WelcomeHero title={t('auth.hero_title')} subtitle={t('auth.private_note')} />

      <Card className="animate-fade-up rounded-3xl p-6 shadow-[var(--shadow-lift)] sm:p-9">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[1.65rem] font-bold tracking-tight text-slate-900">{t(title)}</h2>
            <p className="mt-1 text-sm text-slate-500">{t(sub)}</p>
          </div>
          <LanguageSwitcher className="w-36 shrink-0" />
        </div>

        <form onSubmit={onSubmit} className="space-y-5" noValidate>
          {mode === 'sign_up' && (
            <label className="block">
              <Label>{t('auth.name')}</Label>
              <Input value={form.name} onChange={(e) => set('name')(e.target.value)} autoComplete="name" autoFocus />
              <FieldMessage error={tried && !form.name.trim() ? t('contact.required') : null} />
            </label>
          )}
          {(mode === 'sign_in' || mode === 'sign_up' || mode === 'forgot') && loginField(mode !== 'sign_up')}
          {mode === 'sign_up' && needsEmail && (
            <label className="block">
              <Label>{t('auth.email')}</Label>
              <Input type="email" value={form.email} onChange={(e) => set('email')(e.target.value)} autoComplete="email" />
              <FieldMessage
                error={tried && !emailValid(form.email) ? t('contact.email_invalid') : null}
                ok={emailValid(form.email)}
              >
                {t('auth.email_hint')}
              </FieldMessage>
            </label>
          )}
          {(mode === 'sign_in' || mode === 'sign_up') && (
            <div>
              <PasswordField
                label={t('auth.password')}
                value={form.password}
                onChange={set('password')}
                autoComplete={mode === 'sign_up' ? 'new-password' : 'current-password'}
                hint={mode === 'sign_up' ? t('auth.password_hint') : undefined}
                error={tried && (mode === 'sign_up' ? !passwordOk : !form.password) ? t(mode === 'sign_up' ? 'auth.password_hint' : 'contact.required') : null}
              />
              {mode === 'sign_in' && (
                <button type="button" onClick={() => go('forgot')} className="mt-1.5 text-sm font-medium text-brand-700 hover:text-brand-800">
                  {t('auth.forgot')}
                </button>
              )}
            </div>
          )}
          {mode === 'forgot' && <p className="text-sm text-slate-500">{t('auth.forgot_no_email')}</p>}

          {(mode === 'verify' || mode === 'reset') && sent && (
            <CodeEntry
              key={sends}
              sent={sent}
              value={code}
              onChange={setCode}
              onResend={() => resend.mutate()}
              resending={resend.isPending}
              showErrors={tried}
            />
          )}
          {mode === 'reset' && (
            <>
              <PasswordField
                label={t('profiles.new_password')}
                value={form.password}
                onChange={set('password')}
                autoComplete="new-password"
                hint={t('auth.password_hint')}
                error={tried && !passwordOk ? t('auth.password_hint') : null}
              />
              <PasswordField
                label={t('profiles.confirm_password')}
                value={form.confirm}
                onChange={set('confirm')}
                autoComplete="new-password"
                error={(tried || form.confirm) && form.confirm !== form.password ? t('profiles.password_mismatch') : null}
              />
            </>
          )}

          {active.error && <ErrorNote error={active.error} />}
          {resend !== active && resend.error && <ErrorNote error={resend.error} />}
          <Button type="submit" size="lg" className="w-full" loading={active.isPending}>
            {mode === 'forgot' ? <Mail className="h-4 w-4" /> : mode === 'reset' ? <KeyRound className="h-4 w-4" /> : <Lock className="h-4 w-4" />}
            {t({ sign_in: 'auth.sign_in', sign_up: 'auth.send_code', verify: 'auth.verify_create', forgot: 'auth.send_code', reset: 'auth.reset_submit' }[mode])}
          </Button>
        </form>

        <p className="mt-5 text-center text-sm text-slate-600">
          {mode === 'sign_in' || mode === 'sign_up' ? (
            <>
              {mode === 'sign_up' ? t('auth.have_account') : t('auth.no_account')}{' '}
              <button
                type="button"
                onClick={() => go(mode === 'sign_up' ? 'sign_in' : 'sign_up')}
                className="font-medium text-brand-700 hover:text-brand-800"
              >
                {mode === 'sign_up' ? t('auth.sign_in') : t('auth.sign_up')}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => go(mode === 'verify' ? 'sign_up' : 'sign_in')}
              className="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:text-brand-800"
            >
              <ArrowLeft className="h-4 w-4" />
              {mode === 'verify' ? t('auth.change_details') : t('auth.back_to_sign_in')}
            </button>
          )}
        </p>
        <Disclaimer className="mt-6" />
      </Card>
    </AuroraPage>
  )
}
