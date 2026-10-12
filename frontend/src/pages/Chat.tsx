import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, BookMarked, Bot, Info, Send, Stethoscope, User } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import Markdown from 'react-markdown'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, ErrorNote, PageHeader } from '@/components/ui'
import { api } from '@/lib/api'
import { useActivePatient, useLang } from '@/lib/patient'
import type { ChatReply } from '@/lib/types'
import { fmtDate } from '@/lib/utils'

interface Msg {
  role: 'user' | 'assistant'
  content: string
  reply?: ChatReply
}

export default function Chat() {
  const { t } = useTranslation()
  const lang = useLang()
  const patient = useActivePatient()
  const storeKey = `hc.chat.${patient.id}`
  const [messages, setMessages] = useState<Msg[]>(() => JSON.parse(sessionStorage.getItem(storeKey) ?? '[]'))
  const [input, setInput] = useState('')
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    sessionStorage.setItem(storeKey, JSON.stringify(messages.slice(-30)))
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, storeKey])

  const ask = useMutation({
    mutationFn: (text: string) =>
      api.chat(
        patient.id,
        text,
        messages.slice(-8).map((m) => ({ role: m.role, content: m.content })),
        lang,
      ),
    onSuccess: (reply) => setMessages((m) => [...m, { role: 'assistant', content: reply.answer, reply }]),
  })

  const send = (text: string) => {
    const q = text.trim()
    if (!q || ask.isPending) return
    setMessages((m) => [...m, { role: 'user', content: q }])
    setInput('')
    ask.mutate(q)
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    send(input)
  }

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col lg:h-[calc(100vh-10rem)]">
      <PageHeader title={t('chat.title')} subtitle={t('chat.subtitle')} />
      <Card className="flex min-h-0 flex-1 flex-col">
        <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="rounded-full bg-brand-50 p-4 text-brand-600">
                <Bot className="h-8 w-8" />
              </div>
              <p className="mt-3 max-w-md text-slate-600">{t('chat.subtitle')}</p>
              <div className="mt-5 grid w-full max-w-2xl gap-2 sm:grid-cols-2">
                {['s1', 's2', 's3', 's4'].map((k) => (
                  <button
                    key={k}
                    onClick={() => send(t(`chat.${k}`))}
                    className="rounded-xl bg-white px-4 py-3 text-left text-sm text-slate-700 ring-1 ring-slate-200 transition-colors hover:bg-brand-50 hover:ring-brand-200"
                  >
                    {t(`chat.${k}`)}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (m.role === 'user' ? <UserBubble key={i} text={m.content} /> : <AssistantBubble key={i} m={m} />))}
          {ask.isPending && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Bot className="h-4 w-4 animate-pulse text-brand-600" />
              {t('chat.thinking')}
            </div>
          )}
          {ask.error && <ErrorNote error={ask.error} />}
          <div ref={end} />
        </div>
        <form onSubmit={submit} className="flex items-end gap-2 border-t border-slate-100 p-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send(input)
              }
            }}
            rows={1}
            placeholder={t('chat.placeholder')}
            className="max-h-40 min-h-11 flex-1 resize-none rounded-xl border-0 bg-slate-50 px-4 py-3 text-sm ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-brand-500 focus:outline-none"
          />
          <Button type="submit" size="lg" disabled={!input.trim()} loading={ask.isPending} className="h-11">
            <Send className="h-4 w-4" />
            <span className="hidden sm:inline">{t('chat.send')}</span>
          </Button>
        </form>
      </Card>
    </div>
  )
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end gap-2">
      <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white">{text}</div>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-600">
        <User className="h-4 w-4" />
      </div>
    </div>
  )
}

function AssistantBubble({ m }: { m: Msg }) {
  const { t } = useTranslation()
  const lang = useLang()
  const r = m.reply
  return (
    <div className="flex gap-2">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
        <Bot className="h-4 w-4" />
      </div>
      <div className="min-w-0 max-w-[85%] space-y-2">
        {r?.emergency_notice && (
          <div className="flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-800 ring-1 ring-red-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {r.emergency_notice}
          </div>
        )}
        <div className="prose-sm rounded-2xl rounded-tl-sm bg-slate-50 px-4 py-3 text-sm leading-relaxed text-slate-800 ring-1 ring-slate-200 [&_li]:ml-4 [&_ol]:list-decimal [&_p+p]:mt-2 [&_ul]:list-disc">
          <Markdown>{m.content}</Markdown>
        </div>
        {r && (
          <div className="flex flex-wrap items-center gap-1.5">
            {!r.answered_from_records && (
              <Badge className="bg-slate-100">
                <Info className="h-3 w-3" />
                {t('chat.not_in_records')}
              </Badge>
            )}
            {r.citations.length > 0 && (
              <>
                <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                  <BookMarked className="h-3 w-3" />
                  {t('chat.sources')}:
                </span>
                {r.citations.map((c) =>
                  c.document_id ? (
                    <Link key={c.id} to={`/documents/${c.document_id}`}>
                      <Badge className="bg-white hover:bg-brand-50">
                        {c.label}
                        {c.date && ` · ${fmtDate(c.date, lang)}`}
                      </Badge>
                    </Link>
                  ) : (
                    <Badge key={c.id}>{c.label}</Badge>
                  ),
                )}
              </>
            )}
          </div>
        )}
        {r?.suggest_doctor && (
          <p className="flex items-center gap-1.5 text-xs text-slate-500">
            <Stethoscope className="h-3.5 w-3.5" />
            {t('chat.doctor_hint')}
          </p>
        )}
      </div>
    </div>
  )
}
