import { Eye, EyeOff } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { FieldMessage } from '@/components/ContactInputs'
import { Input, Label } from '@/components/ui'

export function PasswordField({
  value,
  onChange,
  autoComplete,
  label,
  error,
  hint,
  autoFocus,
}: {
  value: string
  onChange: (v: string) => void
  autoComplete: string
  label: ReactNode
  error?: ReactNode
  hint?: ReactNode
  autoFocus?: boolean
}) {
  const { t } = useTranslation()
  const [show, setShow] = useState(false)
  return (
    <label className="block">
      <Label>{label}</Label>
      <div className="relative">
        <Input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          aria-invalid={!!error}
          className="pr-10"
        />
        <button
          type="button"
          onClick={() => setShow((v) => !v)}
          className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600"
          aria-label={t(show ? 'auth.hide_password' : 'auth.show_password')}
          aria-pressed={show}
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      <FieldMessage error={error}>{hint}</FieldMessage>
    </label>
  )
}
