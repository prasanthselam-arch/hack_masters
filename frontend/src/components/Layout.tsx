import {
  CalendarClock,
  ChevronsUpDown,
  Languages,
  LayoutDashboard,
  LineChart,
  LogOut,
  MessageCircleHeart,
  Pill,
  ShieldCheck,
  Upload,
  UserPlus,
  Users,
} from 'lucide-react'
import { Suspense } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LANGUAGES } from '@/i18n'
import { useAuth } from '@/lib/auth'
import { useLang, usePatient } from '@/lib/patient'
import { cn } from '@/lib/utils'
import { formatPhone } from '@/lib/phone'
import { Avatar } from './Avatar'
import { Disclaimer } from './medical'
import { Spinner } from './ui'

const NAV_GROUPS = [
  {
    key: 'records',
    items: [
      { to: '/', key: 'dashboard', icon: LayoutDashboard },
      { to: '/upload', key: 'upload', icon: Upload },
      { to: '/timeline', key: 'timeline', icon: CalendarClock },
      { to: '/trends', key: 'trends', icon: LineChart },
      { to: '/medications', key: 'medications', icon: Pill },
    ],
  },
  {
    key: 'assist',
    items: [
      { to: '/chat', key: 'chat', icon: MessageCircleHeart },
      { to: '/abha', key: 'abha', icon: ShieldCheck },
      { to: '/profiles', key: 'profiles', icon: Users },
    ],
  },
]
const NAV = NAV_GROUPS.flatMap((g) => g.items)

export function LanguageSwitcher({ className, tone = 'light' }: { className?: string; tone?: 'light' | 'dark' }) {
  const { i18n, t } = useTranslation()
  const lang = useLang()
  const dark = tone === 'dark'
  return (
    <label
      className={cn(
        'flex items-center gap-2 rounded-xl px-2.5 text-sm ring-1 ring-inset transition',
        dark ? 'bg-white/[0.06] ring-white/10 hover:bg-white/10' : 'bg-white ring-slate-900/[0.08] shadow-[var(--shadow-soft)]',
        className,
      )}
    >
      <Languages className={cn('h-4 w-4 shrink-0', dark ? 'text-brand-300' : 'text-brand-600')} />
      <span className="sr-only">{t('common.language')}</span>
      <select
        value={lang}
        onChange={(e) => i18n.changeLanguage(e.target.value)}
        className={cn(
          'w-full cursor-pointer border-0 bg-transparent py-1.5 pr-7 pl-0 text-sm focus:ring-0 [&_option]:text-slate-900',
          dark ? 'text-slate-100' : 'text-slate-700',
        )}
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
  const { t } = useTranslation()
  const { patients, patient, select } = usePatient()
  if (!patient) return null
  const index = patients.findIndex((p) => p.id === patient.id)
  const label = (p: typeof patient) => (p.relationship ? `${p.name} · ${t(`relationship.${p.relationship}`)}` : p.name)
  return (
    <div className="relative rounded-2xl bg-gradient-to-br from-white/[0.09] to-white/[0.03] p-3 ring-1 ring-inset ring-white/10">
      <div className="flex items-center gap-3">
        <Avatar name={patient.name} index={index} className="h-10 w-10 text-sm ring-2 ring-white/15" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white">{patient.name}</p>
          <p className="truncate text-xs text-slate-400">
            {patient.abha_address ? (
              <span className="inline-flex items-center gap-1 text-brand-300">
                <ShieldCheck className="h-3 w-3" />
                {patient.abha_address}
              </span>
            ) : (
              [patient.relationship ? t(`relationship.${patient.relationship}`) : null, formatPhone(patient.phone)].filter(Boolean).join(' · ') ||
              t('profiles.viewing')
            )}
          </p>
        </div>
        {patients.length > 1 && <ChevronsUpDown className="h-4 w-4 shrink-0 text-slate-400" />}
      </div>
      {patients.length > 1 && (
        <select
          aria-label={t('profiles.family')}
          value={patient.id}
          onChange={(e) => select(e.target.value)}
          className="absolute inset-0 cursor-pointer opacity-0 [&_option]:text-slate-900"
        >
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {label(p)}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

/** Profile switcher for screens without the sidebar. */
function MobilePatientBar() {
  const { t } = useTranslation()
  const { patients, patient, select } = usePatient()
  if (!patient) return null
  const index = patients.findIndex((p) => p.id === patient.id)
  return (
    <div className="flex items-center gap-2 px-4 pb-2.5">
      <div className="relative flex min-w-0 flex-1 items-center gap-2.5 rounded-xl bg-white/80 px-2.5 py-1.5 ring-1 ring-slate-900/[0.07]">
        <Avatar name={patient.name} index={index} className="h-7 w-7 text-[11px]" />
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-sm font-semibold text-slate-900">{patient.name}</p>
          {patient.relationship && <p className="truncate text-[11px] text-slate-500">{t(`relationship.${patient.relationship}`)}</p>}
        </div>
        {patients.length > 1 && (
          <>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-slate-400" />
            <select
              aria-label={t('profiles.family')}
              value={patient.id}
              onChange={(e) => select(e.target.value)}
              className="absolute inset-0 cursor-pointer opacity-0"
            >
              {patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.relationship ? `${p.name} · ${t(`relationship.${p.relationship}`)}` : p.name}
                </option>
              ))}
            </select>
          </>
        )}
      </div>
      <Link
        to="/profiles"
        title={t('profiles.manage')}
        className="flex shrink-0 items-center gap-1.5 rounded-xl bg-white/80 px-3 py-2.5 text-xs font-medium text-slate-700 ring-1 ring-slate-900/[0.07] hover:text-brand-700"
      >
        <Users className="h-4 w-4" />
        <span className="hidden sm:inline">{t('profiles.manage')}</span>
      </Link>
    </div>
  )
}

function AccountBar() {
  const { t } = useTranslation()
  const { account, signOut } = useAuth()
  if (!account) return null
  return (
    <div className="flex items-center justify-between gap-2 px-1">
      <Link
        to="/profiles"
        className="min-w-0 truncate text-xs text-slate-400 transition-colors hover:text-white"
        title={account.login.startsWith('+') ? formatPhone(account.login) : account.login}
      >
        {t('auth.signed_in_as')} <span className="font-medium text-slate-200">{account.name}</span>
      </Link>
      <div className="flex shrink-0 gap-0.5">
        <Link to="/profiles/new" title={t('profile.add')} className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-brand-300">
          <UserPlus className="h-4 w-4" />
          <span className="sr-only">{t('profile.add')}</span>
        </Link>
        <button onClick={signOut} title={t('auth.sign_out')} className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-red-300">
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
  const location = useLocation()
  const { patient } = usePatient()
  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-[17rem] shrink-0 flex-col overflow-hidden bg-ink-900 px-4 py-5 text-slate-300 lg:flex">
        {/* soft brand glows behind the sidebar content */}
        <div className="pointer-events-none absolute -top-24 -left-16 h-64 w-64 rounded-full bg-brand-500/25 blur-3xl" />
        <div className="pointer-events-none absolute bottom-10 -right-24 h-56 w-56 rounded-full bg-sky-500/10 blur-3xl" />
        <div className="relative flex min-h-0 flex-1 flex-col">
          <Brand tone="dark" />
          <nav className="scrollbar-thin mt-7 flex-1 space-y-6 overflow-y-auto pr-1">
            {NAV_GROUPS.map((g) => (
              <div key={g.key}>
                <p className="mb-2 px-3 text-[11px] font-semibold tracking-[0.12em] text-slate-500 uppercase">{t(`nav.group_${g.key}`)}</p>
                <div className="space-y-0.5">
                  {g.items.map(({ to, key, icon: Icon }) => (
                    <NavLink
                      key={to}
                      to={to}
                      end={to === '/'}
                      className={({ isActive }) =>
                        cn(
                          'group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200',
                          isActive
                            ? 'bg-gradient-to-r from-brand-500/25 via-brand-500/10 to-transparent text-white shadow-[inset_0_0_0_1px_rgb(69_194_165/0.25)]'
                            : 'text-slate-400 hover:bg-white/[0.05] hover:text-slate-100',
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && <span className="absolute top-2 bottom-2 left-0 w-1 rounded-r-full bg-brand-400 shadow-[0_0_12px_rgb(69_194_165/0.8)]" />}
                          <Icon className={cn('h-[18px] w-[18px] transition-colors', isActive ? 'text-brand-300' : 'text-slate-500 group-hover:text-slate-300')} />
                          {t(`nav.${key}`)}
                        </>
                      )}
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>
          <div className="space-y-3 border-t border-white/[0.07] pt-4">
            <LanguageSwitcher tone="dark" />
            <PatientSwitcher />
            <Link
              to="/profiles"
              className="flex items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium text-slate-300 ring-1 ring-inset ring-white/10 transition-colors hover:bg-white/[0.06] hover:text-white"
            >
              <Users className="h-3.5 w-3.5" />
              {t('profiles.manage')}
            </Link>
            <AccountBar />
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-slate-900/[0.06] bg-white/75 backdrop-blur-xl lg:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <Brand compact />
            <div className="flex items-center gap-1">
              <LanguageSwitcher className="w-28 sm:w-36" />
              <button onClick={signOut} title={t('auth.sign_out')} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
          <MobilePatientBar />
          <nav className="scrollbar-thin flex gap-1 overflow-x-auto px-3 pb-2.5">
            {NAV.map(({ to, key, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  cn(
                    'flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition-colors',
                    isActive ? 'bg-ink-900 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-900/[0.05]',
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {t(`nav.${key}`)}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-9">
          <Suspense fallback={<Spinner label={t('common.loading')} />}>
            {/* remount on profile switch so chat history, ABHA transactions and drafts never carry over to another person */}
            <div key={`${patient?.id}:${location.pathname}`} className="animate-fade-up">
              <Outlet />
            </div>
          </Suspense>
        </main>

        <footer className="border-t border-slate-900/[0.06] bg-white/60 px-4 py-3 backdrop-blur sm:px-6 lg:px-10">
          <Disclaimer className="mx-auto max-w-7xl" />
        </footer>
      </div>
    </div>
  )
}

/** Heart with a sweeping ECG trace; still when the user prefers reduced motion. */
export function Logo({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'hc-logo relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 via-brand-600 to-brand-800 text-white shadow-[var(--shadow-glow),inset_0_1px_0_rgb(255_255_255/0.3)]',
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="h-[62%] w-[62%]" fill="none" aria-hidden="true">
        <path
          className="hc-logo-heart"
          d="M12 20.5s-7.5-4.6-9.2-9.4C1.6 7.6 3.9 4 7.4 4c2 0 3.5 1.1 4.6 2.7C13.1 5.1 14.6 4 16.6 4c3.5 0 5.8 3.6 4.6 7.1-1.7 4.8-9.2 9.4-9.2 9.4Z"
          fill="rgb(255 255 255 / 0.18)"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path
          className="hc-logo-trace"
          pathLength={100}
          d="M2.5 12.5h5l1.6-3.2 2.4 6.4 2.1-5.1 1.3 1.9h6.6"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  )
}

export function Brand({ tone = 'light', compact = false }: { tone?: 'light' | 'dark'; compact?: boolean }) {
  const { t } = useTranslation()
  const dark = tone === 'dark'
  return (
    <Link to="/" className="flex items-center gap-3 rounded-xl focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
      <Logo />
      <div className="leading-tight">
        <p className={cn('font-display text-[1.05rem] font-bold', dark ? 'text-white' : 'text-slate-900')}>{t('app.name')}</p>
        <p className={cn('text-xs', dark ? 'text-slate-400' : 'text-slate-500', compact && 'hidden sm:block')}>{t('app.tagline')}</p>
      </div>
    </Link>
  )
}
