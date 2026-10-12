import { useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { FieldMessage, PhoneInput } from '@/components/ContactInputs'
import { Button, ErrorNote, Input, Label, Select } from '@/components/ui'
import { LANGUAGES } from '@/i18n'
import { RELATIONSHIPS, type Lang, type Patient, type Relationship } from '@/lib/types'

const MALE: Relationship[] = ['father', 'son', 'brother', 'grandfather', 'grandson', 'father_in_law']
const FEMALE: Relationship[] = ['mother', 'daughter', 'sister', 'grandmother', 'granddaughter', 'mother_in_law']

export interface ProfileValues {
  name: string
  relationship: Relationship | null
  gender: string | null
  birth_date: string | null
  phone: string | null
  preferred_language: Lang
}

export function emptyProfile(lang: Lang, p?: Partial<Patient>): ProfileValues {
  return {
    name: p?.name ?? '',
    relationship: p?.relationship ?? null,
    gender: p?.gender ?? null,
    birth_date: p?.birth_date ?? null,
    phone: p?.phone ?? null,
    preferred_language: p?.preferred_language ?? lang,
  }
}

/**
 * Name, relationship (for family members), gender, date of birth, mobile and language.
 * `askRelationship` makes the relationship required; "self" is never offered because each account has one.
 */
export function ProfileForm({
  initial,
  askRelationship,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
  onLanguageChange,
  autoFocus,
  footer,
  askName = true,
}: {
  initial: ProfileValues
  askRelationship: boolean
  submitLabel: ReactNode
  pending?: boolean
  error?: unknown
  onSubmit: (v: ProfileValues) => void
  onCancel?: () => void
  onLanguageChange?: (l: Lang) => void
  autoFocus?: boolean
  footer?: ReactNode
  /** Off for the account holder's first profile: the name already came from sign-up. */
  askName?: boolean
}) {
  const { t } = useTranslation()
  const [v, setV] = useState(initial)
  const [phoneValid, setPhoneValid] = useState(true)
  const [tried, setTried] = useState(false)
  const [today] = useState(() => new Date().toLocaleDateString('en-CA')) // local YYYY-MM-DD, not the UTC date

  const name = v.name.replace(/\s+/g, ' ').trim()
  const dobProblem = v.birth_date && (v.birth_date > today || v.birth_date < '1900-01-01') ? t('profiles.dob_invalid') : null
  const relProblem = askRelationship && !v.relationship ? t('profiles.relationship_required') : null
  const valid = !!name && phoneValid && !dobProblem && !relProblem

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTried(true)
    if (valid) onSubmit({ ...v, name, relationship: askRelationship ? v.relationship : initial.relationship })
  }
  const setRelationship = (r: Relationship | null) =>
    setV((cur) => ({
      ...cur,
      relationship: r,
      gender: cur.gender || (r && MALE.includes(r) ? 'male' : r && FEMALE.includes(r) ? 'female' : cur.gender),
    }))

  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      {(askName || askRelationship) && (
        <div className={askRelationship ? 'grid gap-5 sm:grid-cols-2' : ''}>
          {askName && (
            <label className="block">
              <Label>{t('onboarding.name')}</Label>
              <Input
                required
                maxLength={100}
                value={v.name}
                onChange={(e) => setV({ ...v, name: e.target.value })}
                autoFocus={autoFocus}
                autoComplete="name"
                aria-invalid={tried && !name}
              />
              <FieldMessage error={tried && !name ? t('contact.required') : null} />
            </label>
          )}
          {askRelationship && (
            <label className="block">
              <Label>{t('profiles.relationship')}</Label>
              <Select
                required
                value={v.relationship ?? ''}
                onChange={(e) => setRelationship((e.target.value || null) as Relationship | null)}
                aria-invalid={tried && !!relProblem}
              >
                <option value="">{t('profiles.choose_relationship')}</option>
                {RELATIONSHIPS.filter((r) => r !== 'self').map((r) => (
                  <option key={r} value={r}>
                    {t(`relationship.${r}`)}
                  </option>
                ))}
              </Select>
              <FieldMessage error={tried ? relProblem : null} />
            </label>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <label className="block">
          <Label>{t('onboarding.gender')}</Label>
          <Select value={v.gender ?? ''} onChange={(e) => setV({ ...v, gender: e.target.value || null })}>
            <option value="">{t('onboarding.choose_gender')}</option>
            <option value="male">{t('onboarding.male')}</option>
            <option value="female">{t('onboarding.female')}</option>
            <option value="other">{t('onboarding.other')}</option>
          </Select>
          <FieldMessage>{t('onboarding.why_gender')}</FieldMessage>
        </label>
        <label className="block">
          <Label>{t('onboarding.dob')}</Label>
          <Input
            type="date"
            value={v.birth_date ?? ''}
            min="1900-01-01"
            max={today}
            onChange={(e) => setV({ ...v, birth_date: e.target.value || null })}
            aria-invalid={!!dobProblem}
          />
          <FieldMessage error={dobProblem} />
        </label>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div>
          <Label>{t('onboarding.phone')}</Label>
          <PhoneInput
            value={v.phone ?? ''}
            showErrors={tried}
            onChange={(p) => {
              setV((cur) => ({ ...cur, phone: p.value || null }))
              setPhoneValid(p.valid)
            }}
          />
        </div>
        <label className="block">
          <Label>{t('onboarding.language')}</Label>
          <Select
            value={v.preferred_language}
            onChange={(e) => {
              const l = e.target.value as Lang
              setV({ ...v, preferred_language: l })
              onLanguageChange?.(l)
            }}
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </Select>
        </label>
      </div>

      {error ? <ErrorNote error={error} /> : null}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" size="lg" className={onCancel ? '' : 'w-full'} loading={pending}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" size="lg" variant="secondary" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
        )}
      </div>
      {footer}
    </form>
  )
}
