import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { AuroraPage, WelcomeHero } from '@/components/Hero'
import { Disclaimer } from '@/components/medical'
import { emptyProfile, ProfileForm, type ProfileValues } from '@/components/ProfileForm'
import { Card } from '@/components/ui'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useLang, usePatient } from '@/lib/patient'

/** Creates the account's first profile, or (with `addMember`) another profile for a family member. */
export default function Onboarding({ addMember = false }: { addMember?: boolean }) {
  const { t, i18n } = useTranslation()
  const lang = useLang()
  const qc = useQueryClient()
  const nav = useNavigate()
  const { select } = usePatient()
  const { account } = useAuth()
  const ownMobile = account?.login.startsWith('+') ? account.login : null

  const create = useMutation({
    mutationFn: (v: ProfileValues) => api.createPatient(v),
    onSuccess: async (p) => {
      select(p.id)
      await qc.invalidateQueries({ queryKey: ['patients'] })
      nav('/')
    },
  })

  return (
    <AuroraPage>
        <WelcomeHero
          title={addMember ? t('profile.add_title') : t('onboarding.title')}
          subtitle={addMember ? t('profile.add_sub') : t('onboarding.subtitle')}
        />

        <Card className="animate-fade-up rounded-3xl p-6 shadow-[var(--shadow-lift)] sm:p-9">
          {addMember && (
            <Link to="/profiles" className="mb-5 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800">
              <ArrowLeft className="h-4 w-4" />
              {t('common.back')}
            </Link>
          )}
          <ProfileForm
            autoFocus
            askRelationship={addMember}
            initial={
              addMember
                ? emptyProfile(lang)
                : emptyProfile(lang, { name: account?.name ?? '', phone: ownMobile, relationship: 'self' })
            }
            onLanguageChange={addMember ? undefined : (l) => i18n.changeLanguage(l)}
            submitLabel={addMember ? t('profile.add') : t('onboarding.create')}
            pending={create.isPending}
            error={create.error}
            onSubmit={(v) => create.mutate(v)}
            footer={<Disclaimer />}
          />
        </Card>
    </AuroraPage>
  )
}
