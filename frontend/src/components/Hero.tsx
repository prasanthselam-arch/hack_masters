import { FileHeart, Languages, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { LANGUAGES } from '@/i18n'
import { Brand } from './Layout'

/** Full-page backdrop for the sign-in and profile setup screens. */
export function AuroraPage({ children }: { children: ReactNode }) {
  return (
    <div className="relative isolate min-h-full overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="animate-float absolute -top-40 -left-32 h-[34rem] w-[34rem] rounded-full bg-brand-300/35 blur-3xl" />
        <div className="animate-float absolute top-1/3 -right-40 h-[30rem] w-[30rem] rounded-full bg-sky-300/30 blur-3xl [animation-delay:-5s]" />
        <div className="animate-float absolute -bottom-40 left-1/3 h-[26rem] w-[26rem] rounded-full bg-violet-300/20 blur-3xl [animation-delay:-9s]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgb(15_23_42/0.035)_1px,transparent_1px),linear-gradient(to_bottom,rgb(15_23_42/0.035)_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_75%)]" />
      </div>
      <div className="mx-auto grid max-w-6xl items-center gap-10 px-6 py-10 lg:min-h-screen lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:py-16">{children}</div>
    </div>
  )
}

/** Left-hand welcome panel shared by the sign-in and profile setup screens. */
export function WelcomeHero({ title, subtitle }: { title: string; subtitle: string }) {
  const { t } = useTranslation()
  return (
    <div className="animate-fade-up flex flex-col justify-center">
      <Brand />
      <h1 className="mt-8 text-4xl leading-[1.1] font-extrabold tracking-tight text-slate-900 lg:mt-12 lg:text-5xl">
        <span className="text-gradient">{title}</span>
      </h1>
      <p className="mt-4 max-w-lg text-slate-600 lg:text-lg">{subtitle}</p>
      <ul className="mt-10 hidden space-y-3 text-slate-700 lg:block">
        <Feature icon={<FileHeart className="h-5 w-5" />} text={t('upload.subtitle')} />
        <Feature icon={<Languages className="h-5 w-5" />} text={LANGUAGES.map((l) => l.label).join(' · ')} />
        <Feature icon={<ShieldCheck className="h-5 w-5" />} text={t('abha.subtitle')} />
      </ul>
    </div>
  )
}

function Feature({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <li className="surface flex max-w-lg items-start gap-3 rounded-2xl p-3 pr-4">
      <span className="rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 p-2 text-white shadow-[var(--shadow-glow)]">{icon}</span>
      <span className="pt-1.5 text-sm">{text}</span>
    </li>
  )
}
