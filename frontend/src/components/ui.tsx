import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2, RotateCcw } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

const button = cva(
  'inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 whitespace-nowrap',
  {
    variants: {
      variant: {
        primary:
          'bg-gradient-to-b from-brand-500 to-brand-700 text-white shadow-[var(--shadow-glow),inset_0_1px_0_rgb(255_255_255/0.25)] hover:-translate-y-px hover:from-brand-500 hover:to-brand-600 hover:shadow-[0_12px_28px_-10px_rgb(22_134_114/0.65),inset_0_1px_0_rgb(255_255_255/0.25)]',
        secondary: 'bg-white text-slate-700 shadow-[var(--shadow-soft)] ring-1 ring-slate-900/[0.08] hover:-translate-y-px hover:bg-slate-50 hover:text-slate-900',
        ghost: 'text-slate-600 hover:bg-slate-900/[0.05] hover:text-slate-900',
        danger: 'bg-white text-red-600 ring-1 ring-red-200 hover:bg-red-50 shadow-[var(--shadow-soft)]',
      },
      size: { sm: 'h-8 rounded-lg px-3 text-sm', md: 'h-10 px-4 text-sm', lg: 'h-12 px-6 text-base', icon: 'h-9 w-9' },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof button> {
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, loading, children, disabled, ...props },
  ref,
) {
  return (
    <button ref={ref} className={cn(button({ variant, size }), className)} disabled={disabled || loading} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
})

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('surface rounded-2xl', className)} {...props} />
}

export function CardHeader({ title, icon, action, subtitle }: { title: ReactNode; icon?: ReactNode; action?: ReactNode; subtitle?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-slate-900/[0.06] px-5 py-4">
      <div className="flex items-start gap-3">
        {icon && (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-50 to-brand-100 text-brand-700 ring-1 ring-brand-200/60 [&_svg]:h-4 [&_svg]:w-4">
            {icon}
          </span>
        )}
        <div className="min-w-0 pt-0.5">
          <h3 className="font-semibold text-slate-900">{title}</h3>
          {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset bg-slate-50 text-slate-600 ring-slate-200', className)}
      {...props}
    />
  )
}

const field =
  'w-full rounded-xl border-0 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-[0_1px_2px_rgb(15_23_42/0.04)] ring-1 ring-inset ring-slate-900/[0.1] transition placeholder:text-slate-400 hover:ring-slate-900/[0.18] focus:ring-2 focus:ring-brand-500 focus:shadow-[0_0_0_4px_rgb(34_167_139/0.12)] focus:outline-none aria-[invalid=true]:ring-red-300'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn(field, className)} {...props} />
})

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(field, 'hc-select cursor-pointer pr-9', className)} {...props} />
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(field, className)} {...props} />
}

export function Label({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <span className="mb-1 block text-sm font-medium text-slate-700">
      {children}
      {hint && <span className="mt-0.5 block text-xs font-normal text-slate-500">{hint}</span>}
    </span>
  )
}

export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <div className={cn('flex items-center justify-center gap-2 py-10 text-sm text-slate-500', className)}>
      <Loader2 className="h-5 w-5 animate-spin text-brand-600" />
      {label}
    </div>
  )
}

export function PageHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-[1.75rem]">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-3xl text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function Empty({ icon, title, body, action }: { icon?: ReactNode; title: ReactNode; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {icon && (
        <div className="relative mb-4">
          <div className="absolute inset-0 rounded-2xl bg-brand-400/30 blur-xl" />
          <div className="relative rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 p-3.5 text-white shadow-[var(--shadow-glow)]">{icon}</div>
        </div>
      )}
      <p className="font-display text-lg font-semibold text-slate-900">{title}</p>
      {body && <p className="mt-1 max-w-md text-sm text-slate-500">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[] }) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-xl bg-slate-900/[0.05] p-1 ring-1 ring-inset ring-slate-900/[0.04]">
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            'rounded-lg px-3 py-1.5 text-sm font-medium transition-all',
            value === it.value ? 'bg-white text-slate-900 shadow-[0_1px_3px_rgb(15_23_42/0.12)]' : 'text-slate-600 hover:bg-white/50 hover:text-slate-900',
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  )
}

export function ErrorNote({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation()
  const msg = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-xl bg-red-50/90 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
      <span>{msg}</span>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          <RotateCcw className="h-3.5 w-3.5" />
          {t('common.retry')}
        </Button>
      )}
    </div>
  )
}
