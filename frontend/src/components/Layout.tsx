import { Activity, CalendarClock, HeartPulse, Languages, LayoutDashboard, LineChart, LogOut, MessageCircleHeart, Pill, ShieldCheck, Upload, UserPlus } from 'lucide-react'
import { Suspense } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LANGUAGES } from '@/i18n'
import { useAuth } from '@/lib/auth'
import { useLang, usePatient } from '@/lib/patient'
import { cn } from '@/lib/utils'
import { Disclaimer } from './medical'
import { Spinner } from './ui'

const NAV = [
  { to: '/', key: 'dashboard', icon: LayoutDashboard },
  { to: '/upload', key: 'upload', icon: Upload },
  { to: '/timeline', key: 'timeline', icon: CalendarClock },
  { to: '/trends', key: 'trends', icon: LineChart },
  { to: '/medications', key: 'medications', icon: Pill },
  { to: '/chat', key: 'chat', icon: MessageCircleHeart },
  { to: '/abha', key: 'abha', icon: ShieldCheck },
]

export function LanguageSwitcher({ className }: { className?: string }) {
  const { i18n, t } = useTranslation()
  const lang = useLang()
  return (
    <label className={cn('flex items-center gap-2 text-sm', className)}>
      <Languages className="h-4 w-4 text-slate-400" />
      <span className="sr-only">{t('common.language')}</span>
      <select
        value={lang}
        onChange={(e) => i18n.changeLanguage(e.target.value)}
        className="w-full rounded-lg border-0 bg-slate-100 py-1.5 pl-2 pr-7 text-sm text-slate-700 focus:ring-2 focus:ring-brand-500"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
            {l.code !== 'en' ? ` · ${l.english}` : ''}
          </option>
        ))}
      </select>
    </label>
  )
}

function PatientSwitcher() {
  const { patients, patient, select } = usePatient()
  if (!patient) return null
  return (
    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-800">
          {patient.name.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0">
          {patients.length > 1 ? (
            <select
              value={patient.id}
              onChange={(e) => select(e.target.value)}
              className="w-full truncate border-0 bg-transparent p-0 pr-6 text-sm font-medium text-slate-900 focus:ring-0"
            >
              {patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          ) : (
            <p className="truncate text-sm font-medium text-slate-900">{patient.name}</p>
          )}
          <p className="truncate text-xs text-slate-500">
            {patient.abha_address ? (
              <span className="inline-flex items-center gap-1 text-brand-700">
                <ShieldCheck className="h-3 w-3" />
                {patient.abha_address}
              </span>
            ) : (
              [patient.gender, patient.birth_date].filter(Boolean).join(' · ')
            )}
          </p>
        </div>
      </div>
    </div>
  )
}

function AccountBar() {
  const { t } = useTranslation()
  const { account, signOut } = useAuth()
  if (!account) return null
  return (
    <div className="flex items-center justify-between gap-2 px-1">
      <p className="min-w-0 truncate text-xs text-slate-500" title={account.login}>
        {t('auth.signed_in_as')} <span className="font-medium text-slate-700">{account.name}</span>
      </p>
      <div className="flex shrink-0 gap-1">
        <Link to="/profiles/new" title={t('profile.add')} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-brand-700">
          <UserPlus className="h-4 w-4" />
          <span className="sr-only">{t('profile.add')}</span>
        </Link>
        <button onClick={signOut} title={t('auth.sign_out')} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-red-600">
          <LogOut className="h-4 w-4" />
          <span className="sr-only">{t('auth.sign_out')}</span>
        </button>
      </div>
    </div>
  )
}

export function Layout() {
  const { signOut } = useAuth()
  const { t } = useTranslation()
  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-slate-200 bg-white px-4 py-5 lg:flex">
        <Brand />
        <nav className="mt-6 flex-1 space-y-0.5">
          {NAV.map(({ to, key, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-brand-50 text-brand-800' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
                )
              }
            >
              <Icon className="h-4 w-4" />
              {t(`nav.${key}`)}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-3">
          <LanguageSwitcher />
          <PatientSwitcher />
          <AccountBar />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur lg:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <Brand />
            <div className="flex items-center gap-1">
              <LanguageSwitcher className="w-40" />
              <Link to="/profiles/new" title={t('profile.add')} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">
                <UserPlus className="h-4 w-4" />
              </Link>
              <button onClick={signOut} title={t('auth.sign_out')} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
          <nav className="scrollbar-thin flex gap-1 overflow-x-auto px-3 pb-2">
            {NAV.map(({ to, key, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  cn(
                    'flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm',
                    isActive ? 'bg-brand-50 text-brand-800' : 'text-slate-600',
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {t(`nav.${key}`)}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Suspense fallback={<Spinner label={t('common.loading')} />}>
            <Outlet />
          </Suspense>
        </main>

        <footer className="border-t border-slate-200 bg-white px-4 py-3 sm:px-6 lg:px-8">
          <Disclaimer className="mx-auto max-w-7xl" />
        </footer>
      </div>
    </div>
  )
}

export function Brand() {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm">
        <HeartPulse className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <p className="font-semibold text-slate-900">{t('app.name')}</p>
        <p className="flex items-center gap-1 text-xs text-slate-500">
          <Activity className="h-3 w-3" />
          {t('app.tagline')}
        </p>
      </div>
    </div>
  )
}
