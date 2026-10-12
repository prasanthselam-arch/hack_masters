import { FileHeart, Languages, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { LANGUAGES } from '@/i18n'
import { Brand } from './Layout'

/** Left-hand welcome panel shared by the sign-in and profile setup screens. */
export function WelcomeHero({ title, subtitle }: { title: string; subtitle: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col justify-center">
      <Brand />
      <h1 className="mt-6 text-3xl lg:mt-8 lg:text-4xl font-semibold tracking-tight text-slate-900">{title}</h1>
      <p className="mt-2 text-slate-600 lg:mt-3 lg:text-lg">{subtitle}</p>
      <ul className="mt-8 hidden space-y-4 text-slate-700 lg:block">
        <Feature icon={<FileHeart className="h-5 w-5" />} text={t('upload.subtitle')} />
        <Feature icon={<Languages className="h-5 w-5" />} text={LANGUAGES.map((l) => l.label).join(' · ')} />
        <Feature icon={<ShieldCheck className="h-5 w-5" />} text={t('abha.subtitle')} />
      </ul>
    </div>
  )
}

function Feature({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <li className="flex items-start gap-3">
      <span className="rounded-lg bg-white p-2 text-brand-600 shadow-sm ring-1 ring-slate-200">{icon}</span>
      <span className="pt-1.5 text-sm">{text}</span>
    </li>
  )
}
