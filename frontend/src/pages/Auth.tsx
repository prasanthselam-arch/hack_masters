import { useMutation } from '@tanstack/react-query'
import { Eye, EyeOff, Lock } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { LoginInput, type LoginValue } from '@/components/ContactInputs'
import { AuroraPage, WelcomeHero } from '@/components/Hero'
import { LanguageSwitcher } from '@/components/Layout'
import { Disclaimer } from '@/components/medical'
import { Button, Card, ErrorNote, Input, Label } from '@/components/ui'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'

type Mode = 'sign_in' | 'sign_up'

export default function AuthPage() {
  const { t } = useTranslation()
  const { signedIn } = useAuth()
  const [mode, setMode] = useState<Mode>('sign_in')
  const [form, setForm] = useState({ name: '', password: '' })
  const [login, setLogin] = useState<LoginValue>({ value: '', valid: false, kind: 'empty' })
  const [tried, setTried] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const submit = useMutation({
    mutationFn: () =>
      mode === 'sign_up'
        ? api.register({ name: form.name.trim(), login: login.value, password: form.password })
        : api.login({ login: login.value, password: form.password }),
    onSuccess: signedIn,
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTried(true)
    if (login.valid && (!signUp || (form.name.trim() && form.password.length >= 8))) submit.mutate()
  }
  const switchMode = (m: Mode) => {
    setMode(m)
    setTried(false)
    submit.reset()
  }
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  const signUp = mode === 'sign_up'

  return (
    <AuroraPage>
        <WelcomeHero title={t('auth.hero_title')} subtitle={t('auth.private_note')} />

        <Card className="animate-fade-up rounded-3xl p-6 shadow-[var(--shadow-lift)] sm:p-9">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-[1.65rem] font-bold tracking-tight text-slate-900">{signUp ? t('auth.create_title') : t('auth.welcome')}</h2>
              <p className="mt-1 text-sm text-slate-500">{signUp ? t('auth.create_sub') : t('auth.welcome_sub')}</p>
            </div>
            <LanguageSwitcher className="w-36 shrink-0" />
          </div>

          <form onSubmit={onSubmit} className="space-y-5">
            {signUp && (
              <label className="block">
                <Label>{t('auth.name')}</Label>
                <Input required value={form.name} onChange={set('name')} autoComplete="name" autoFocus />
              </label>
            )}
            <div>
              <Label>{t('auth.login')}</Label>
              <LoginInput onChange={setLogin} showErrors={tried} autoFocus={!signUp} hint={t('contact.login_hint')} />
            </div>
            <label className="block">
              <Label hint={signUp ? t('auth.password_hint') : undefined}>{t('auth.password')}</Label>
              <div className="relative">
                <Input
                  required
                  type={showPassword ? 'text' : 'password'}
                  minLength={signUp ? 8 : undefined}
                  value={form.password}
                  onChange={set('password')}
                  autoComplete={signUp ? 'new-password' : 'current-password'}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600"
                  aria-label={t(showPassword ? 'auth.hide_password' : 'auth.show_password')}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </label>

            {submit.error && <ErrorNote error={submit.error} />}
            <Button type="submit" size="lg" className="w-full" loading={submit.isPending}>
              <Lock className="h-4 w-4" />
              {signUp ? t('auth.sign_up') : t('auth.sign_in')}
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-slate-600">
            {signUp ? t('auth.have_account') : t('auth.no_account')}{' '}
            <button
              type="button"
              onClick={() => switchMode(signUp ? 'sign_in' : 'sign_up')}
              className="font-medium text-brand-700 hover:text-brand-800"
            >
              {signUp ? t('auth.sign_in') : t('auth.sign_up')}
            </button>
          </p>
          <Disclaimer className="mt-6" />
        </Card>
    </AuroraPage>
  )
}
