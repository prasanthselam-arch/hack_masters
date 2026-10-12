import { FlaskConical, MailCheck, RotateCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FieldMessage } from '@/components/ContactInputs'
import { Input, Label } from '@/components/ui'
import type { CodeSent } from '@/lib/types'
import { codeComplete } from '@/lib/utils'

/** The 6-digit email code, with a resend countdown. Remount it (change `key`) each time a new code is sent. */
export function CodeEntry({
  sent,
  value,
  onChange,
  onResend,
  resending,
  showErrors,
}: {
  sent: CodeSent
  value: string
  onChange: (code: string) => void
  onResend: () => void
  resending?: boolean
  showErrors?: boolean
}) {
  const { t } = useTranslation()
  const [wait, setWait] = useState(sent.resend_in)
  useEffect(() => {
    const id = window.setInterval(() => setWait((s) => Math.max(0, s - 1)), 1000)
    return () => window.clearInterval(id)
  }, [])
  const minutes = Math.round(sent.expires_in / 60)

  return (
    <div className="space-y-4">
      <div className="flex gap-3 rounded-2xl bg-brand-50 p-4 text-sm text-brand-900 ring-1 ring-brand-100">
        <MailCheck className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
        <div>
          <p>{sent.sent_to ? t('code.sent', { email: sent.sent_to, minutes }) : t('code.sent_reset', { minutes })}</p>
          <p className="mt-1 text-brand-700/80">{t('code.spam')}</p>
        </div>
      </div>
      {sent.dev_code && (
        <p className="flex items-center gap-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-amber-200">
          <FlaskConical className="h-4 w-4 shrink-0" />
          {t('code.dev', { code: sent.dev_code })}
        </p>
      )}
      <label className="block">
        <Label>{t('code.label')}</Label>
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, 6))}
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          placeholder="••••••"
          aria-invalid={showErrors && !codeComplete(value)}
          className="text-center font-mono text-2xl font-semibold tracking-[0.5em] tabular-nums"
        />
        <FieldMessage error={showErrors && !codeComplete(value) ? t('code.invalid') : null} />
      </label>
      <button
        type="button"
        onClick={() => {
          onResend()
          setWait(sent.resend_in)
        }}
        disabled={wait > 0 || resending}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:text-brand-800 disabled:cursor-not-allowed disabled:text-slate-400"
      >
        <RotateCw className={resending ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
        {wait > 0 ? t('code.resend_in', { count: wait }) : t('code.resend')}
      </button>
    </div>
  )
}
