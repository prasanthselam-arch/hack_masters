import { AlertCircle, CheckCircle2, ChevronDown } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import {
  COUNTRIES,
  DEFAULT_COUNTRY,
  detectCountry,
  emailValid,
  looksLikeEmail,
  phoneProblem,
  splitE164,
  toE164,
  type Country,
  type PhoneProblem,
} from '@/lib/phone'
import { cn } from '@/lib/utils'

const box =
  'flex w-full items-stretch overflow-hidden rounded-lg bg-white ring-1 ring-inset focus-within:ring-2 focus-within:ring-brand-500'

/** Compact "IN +91" button over a native select, so the full country list stays accessible. */
function CountryPicker({ country, onChange }: { country: Country; onChange: (c: Country) => void }) {
  const { t } = useTranslation()
  return (
    <span className="relative flex shrink-0 items-center gap-1 border-r border-slate-200 bg-slate-50 pr-2 pl-3 text-sm text-slate-700">
      <span className="font-medium">{country.iso}</span>
      <span className="text-slate-500">+{country.dial}</span>
      <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
      <select
        aria-label={t('contact.country')}
        value={country.iso}
        onChange={(e) => onChange(COUNTRIES.find((c) => c.iso === e.target.value) ?? DEFAULT_COUNTRY)}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {COUNTRIES.map((c) => (
          <option key={c.iso} value={c.iso}>
            {c.name} (+{c.dial})
          </option>
        ))}
      </select>
    </span>
  )
}

function useProblemText() {
  const { t } = useTranslation()
  return (p: PhoneProblem | 'email' | 'required' | null) => {
    if (!p) return null
    if (p === 'email') return t('contact.email_invalid')
    if (p === 'required') return t('contact.required')
    if (p.key === 'phone_digits') return t('contact.phone_digits', { country: p.country, want: p.want, count: p.count })
    return t('contact.phone_invalid', { country: p.country })
  }
}

export function FieldMessage({ error, ok, children }: { error?: ReactNode; ok?: boolean; children?: ReactNode }) {
  if (error)
    return (
      <span role="alert" className="mt-1 flex items-center gap-1 text-xs text-red-600">
        <AlertCircle className="h-3.5 w-3.5 shrink-0" />
        {error}
      </span>
    )
  if (ok && children)
    return (
      <span className="mt-1 flex items-center gap-1 text-xs text-emerald-700">
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
        {children}
      </span>
    )
  return children ? <span className="mt-1 block text-xs text-slate-500">{children}</span> : null
}

/** Typing "+44…" (or "0044…") switches the country; the national number is checked against that country's rules. */
function takeDialCode(raw: string, country: Country): { country: Country; national: string } {
  const trimmed = raw.trimStart()
  if (/^(\+|00)/.test(trimmed)) {
    const found = detectCountry(trimmed)
    if (found) {
      const digits = trimmed.replace(/^(\+|00)/, '').replace(/[\s\-().]/g, '')
      return { country: found, national: digits.slice(found.dial.length) }
    }
    return { country, national: '+' + trimmed.replace(/[^\d\s]/g, '') }
  }
  return { country, national: raw.replace(/[^\d\s\-()]/g, '') }
}

export interface PhoneValue {
  /** E.164 such as "+919876543210", or "" when empty. */
  value: string
  valid: boolean
}

/**
 * Mobile number with a country picker. Emits E.164 and whether it is valid.
 * Errors show once the field has been left or `showErrors` is set (e.g. after a submit attempt).
 */
export function PhoneInput({
  value,
  onChange,
  required,
  showErrors,
  id,
  autoFocus,
}: {
  value: string
  onChange: (v: PhoneValue) => void
  required?: boolean
  showErrors?: boolean
  id?: string
  autoFocus?: boolean
}) {
  const problemText = useProblemText()
  const [{ country, national }, setState] = useState(() => splitE164(value))
  const [touched, setTouched] = useState(false)

  const problem = national.replace(/\D/g, '') ? phoneProblem(national, country) : required ? 'required' : null
  const emit = (c: Country, n: string) => {
    const digits = n.replace(/\D/g, '')
    const p = digits ? phoneProblem(n, c) : null
    onChange({ value: digits ? toE164(n, c) : '', valid: !p && (!required || !!digits) })
  }
  const update = (next: { country: Country; national: string }) => {
    setState(next)
    emit(next.country, next.national)
  }
  const error = (touched || showErrors) && problem ? problemText(problem) : null

  return (
    <>
      <div className={cn(box, error ? 'ring-red-300' : 'ring-slate-200')}>
        <CountryPicker country={country} onChange={(c) => update({ country: c, national })} />
        <input
          id={id}
          type="tel"
          inputMode="tel"
          autoComplete="tel-national"
          autoFocus={autoFocus}
          value={national}
          placeholder={country.example}
          aria-invalid={!!error}
          onChange={(e) => update(takeDialCode(e.target.value, country))}
          onBlur={() => setTouched(true)}
          className="min-w-0 flex-1 border-0 bg-transparent px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
        />
      </div>
      <FieldMessage error={error} />
    </>
  )
}

export interface LoginValue {
  /** Lower-cased email or E.164 phone, ready to send. */
  value: string
  valid: boolean
  kind: 'email' | 'phone' | 'empty'
}

/** "Email or mobile number": shows a country picker as soon as the entry looks like a phone number. */
export function LoginInput({
  initial = '',
  onChange,
  showErrors,
  autoFocus,
  hint,
}: {
  initial?: string
  onChange: (v: LoginValue) => void
  showErrors?: boolean
  autoFocus?: boolean
  hint?: ReactNode
}) {
  const { t } = useTranslation()
  const problemText = useProblemText()
  const start = initial && !looksLikeEmail(initial) ? splitE164(initial) : { country: DEFAULT_COUNTRY, national: initial }
  const [text, setText] = useState(start.national)
  const [country, setCountry] = useState(start.country)
  const [touched, setTouched] = useState(false)

  const kind: LoginValue['kind'] = !text.trim() ? 'empty' : looksLikeEmail(text) ? 'email' : 'phone'
  const problem =
    kind === 'empty' ? 'required' : kind === 'email' ? (emailValid(text) ? null : 'email') : phoneProblem(text, country)

  const emit = (raw: string, c: Country) => {
    const k: LoginValue['kind'] = !raw.trim() ? 'empty' : looksLikeEmail(raw) ? 'email' : 'phone'
    if (k === 'email') onChange({ kind: k, value: raw.trim().toLowerCase(), valid: emailValid(raw) })
    else if (k === 'phone') onChange({ kind: k, value: toE164(raw, c), valid: !phoneProblem(raw, c) })
    else onChange({ kind: k, value: '', valid: false })
  }
  const change = (raw: string) => {
    let next = raw
    let c = country
    if (!looksLikeEmail(raw)) {
      const taken = takeDialCode(raw, country)
      next = taken.national
      c = taken.country
    }
    setText(next)
    setCountry(c)
    emit(next, c)
  }
  const error = (touched || showErrors) && problem ? problemText(problem) : null
  const ok = !problem && kind !== 'empty'

  return (
    <>
      <div className={cn(box, error ? 'ring-red-300' : 'ring-slate-200')}>
        {kind === 'phone' && (
          <CountryPicker
            country={country}
            onChange={(c) => {
              setCountry(c)
              emit(text, c)
            }}
          />
        )}
        <input
          required
          autoComplete="username"
          autoFocus={autoFocus}
          value={text}
          placeholder={t('auth.login_hint')}
          aria-invalid={!!error}
          onChange={(e) => change(e.target.value)}
          onBlur={() => setTouched(true)}
          className="min-w-0 flex-1 border-0 bg-transparent px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
        />
      </div>
      <FieldMessage error={error} ok={ok}>
        {ok ? (kind === 'email' ? t('contact.email_ok') : t('contact.phone_ok', { number: toE164(text, country) })) : hint}
      </FieldMessage>
    </>
  )
}
