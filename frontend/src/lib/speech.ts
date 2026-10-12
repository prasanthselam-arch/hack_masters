/** Voice for the chat: reading replies aloud and dictating questions. */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'

const LOCALES: Record<string, string> = {
  en: 'en-IN', hi: 'hi-IN', te: 'te-IN', ta: 'ta-IN', kn: 'kn-IN', ml: 'ml-IN', mr: 'mr-IN', bn: 'bn-IN',
  gu: 'gu-IN', pa: 'pa-IN', or: 'or-IN', ur: 'ur-IN', ne: 'ne-NP', si: 'si-LK', ar: 'ar-SA', es: 'es-ES',
  fr: 'fr-FR', de: 'de-DE',
}
export const speechLocale = (lang: string) => LOCALES[lang] ?? lang

/** "తెలుగు" for "te": the language's own name, for badges. */
export function languageName(code: string) {
  try {
    return new Intl.DisplayNames([code], { type: 'language' }).of(code) ?? code
  } catch {
    return code
  }
}

// ---------- reading aloud ----------

interface SpeakState {
  id: string | null
  lastId: string | null
  loading: boolean
  error: string | null
}
let state: SpeakState = { id: null, lastId: null, loading: false, error: null }
const listeners = new Set<() => void>()
const set = (s: Partial<SpeakState>) => {
  state = { ...state, ...s }
  listeners.forEach((l) => l())
}
let audio: HTMLAudioElement | null = null
let run = 0

export function useSpeaker() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => state,
  )
}

export function stopSpeaking() {
  run++
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  audio?.pause()
  audio = null
  set({ id: null, loading: false })
}

async function voices(): Promise<SpeechSynthesisVoice[]> {
  if (!('speechSynthesis' in window)) return []
  const now = window.speechSynthesis.getVoices()
  if (now.length) return now
  // Chrome fills the list asynchronously.
  return new Promise((resolve) => {
    const done = () => resolve(window.speechSynthesis.getVoices())
    window.speechSynthesis.addEventListener('voiceschanged', done, { once: true })
    setTimeout(done, 700)
  })
}

function pickVoice(list: SpeechSynthesisVoice[], lang: string) {
  const want = speechLocale(lang).toLowerCase()
  const norm = (v: SpeechSynthesisVoice) => v.lang.replace('_', '-').toLowerCase()
  return list.find((v) => norm(v) === want) ?? list.find((v) => norm(v).split('-')[0] === lang) ?? null
}

/** Browsers cut long utterances short (Chrome stops after ~15 s), so speak sentence by sentence. */
function chunks(text: string) {
  const parts = text.match(/[^.!?।\n]+[.!?।]*\s*/g) ?? [text]
  const out: string[] = []
  for (const p of parts) {
    const last = out[out.length - 1]
    if (last && last.length + p.length < 220) out[out.length - 1] = last + p
    else out.push(p)
  }
  return out.map((c) => c.trim()).filter(Boolean)
}

/**
 * Reads `text` in `lang`, using a voice installed on the device when there is one and the server's voice otherwise
 * (most desktops have no Telugu, Tamil or Kannada voice). Calls `onEnd` when finished, not when stopped.
 */
export async function speak(id: string, text: string, lang: string, onEnd?: () => void) {
  stopSpeaking()
  const mine = ++run
  set({ id, lastId: id, loading: true, error: null })
  const voice = pickVoice(await voices(), lang)
  if (mine !== run) return

  const finish = () => {
    if (mine !== run) return
    set({ id: null, loading: false })
    onEnd?.()
  }

  if (voice) {
    const parts = chunks(text)
    parts.forEach((p, i) => {
      const u = new SpeechSynthesisUtterance(p)
      u.voice = voice
      u.lang = voice.lang
      u.rate = 0.95
      if (i === 0) u.onstart = () => mine === run && set({ loading: false })
      if (i === parts.length - 1) u.onend = finish
      u.onerror = (e) => {
        if (e.error !== 'interrupted' && e.error !== 'canceled') finish()
      }
      window.speechSynthesis.speak(u)
    })
    return
  }

  try {
    const res = await fetch('/api/voice/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, lang }),
    })
    if (!res.ok) throw new Error(String(res.status))
    const url = URL.createObjectURL(await res.blob())
    if (mine !== run) return URL.revokeObjectURL(url)
    audio = new Audio(url)
    audio.onended = () => {
      URL.revokeObjectURL(url)
      finish()
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      if (mine === run) set({ id: null, loading: false, error: 'voice_error' })
    }
    await audio.play()
    if (mine === run) set({ loading: false })
  } catch {
    if (mine === run) set({ id: null, loading: false, error: 'voice_error' })
  }
}

// ---------- dictation ----------

interface RecognitionResult {
  isFinal: boolean
  0: { transcript: string }
}
interface Recognition extends EventTarget {
  lang: string
  interimResults: boolean
  continuous: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  abort(): void
  onresult: ((e: { resultIndex: number; results: ArrayLike<RecognitionResult> }) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}
type RecognitionCtor = new () => Recognition

const NativeRecognition: RecognitionCtor | undefined =
  typeof window === 'undefined'
    ? undefined
    : ((window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor })
        .SpeechRecognition ??
      (window as unknown as { webkitSpeechRecognition?: RecognitionCtor }).webkitSpeechRecognition)

export type DictationStatus = 'idle' | 'listening' | 'transcribing'
export type DictationError = 'mic_denied' | 'mic_insecure' | 'mic_unsupported' | 'no_speech' | 'voice_error'

function canRecord() {
  return typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && 'MediaRecorder' in window
}

/**
 * Speech to text. Uses the browser's recogniser (Chrome, Edge, Safari) and falls back to recording the question and
 * transcribing it on the server (Firefox, or when the recogniser cannot reach its service).
 */
export function useDictation({ lang, onInterim, onFinal }: { lang: string; onInterim: (t: string) => void; onFinal: (t: string) => void }) {
  const [status, setStatus] = useState<DictationStatus>('idle')
  const [error, setError] = useState<DictationError | null>(null)
  const [level, setLevel] = useState(0)
  const useServer = useRef(!NativeRecognition)
  const stopRef = useRef<() => void>(() => undefined)
  const cbs = useRef({ onInterim, onFinal })
  useEffect(() => {
    cbs.current = { onInterim, onFinal }
  })

  const secure = typeof window === 'undefined' || window.isSecureContext
  const supported = secure && (!!NativeRecognition || canRecord())

  const startServer = useCallback(async () => {
    if (!canRecord()) return setError('mic_unsupported')
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    } catch {
      return setError('mic_denied')
    }
    const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'].find((t) => MediaRecorder.isTypeSupported(t))
    const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
    const parts: Blob[] = []
    rec.ondataavailable = (e) => e.data.size && parts.push(e.data)

    // Stop by itself after ~1.8 s of silence once the user has spoken, or after 45 s.
    const ctx = new AudioContext()
    const analyser = ctx.createAnalyser()
    ctx.createMediaStreamSource(stream).connect(analyser)
    const buf = new Uint8Array(analyser.fftSize)
    let spoke = false
    let quietSince = performance.now()
    const started = performance.now()
    const timer = setInterval(() => {
      analyser.getByteTimeDomainData(buf)
      let sum = 0
      for (const v of buf) sum += ((v - 128) / 128) ** 2
      const rms = Math.sqrt(sum / buf.length)
      setLevel(Math.min(1, rms * 6))
      const now = performance.now()
      if (rms > 0.04) {
        spoke = true
        quietSince = now
      }
      if ((spoke && now - quietSince > 1800) || now - started > 45_000 || (!spoke && now - started > 8000)) stop()
    }, 100)

    let stopped = false
    const stop = () => {
      if (stopped) return
      stopped = true
      clearInterval(timer)
      setLevel(0)
      if (rec.state !== 'inactive') rec.stop()
      stream.getTracks().forEach((t) => t.stop())
      void ctx.close()
      if (!spoke) {
        rec.onstop = null
        setStatus('idle')
        setError('no_speech')
      }
    }
    rec.onstop = async () => {
      setStatus('transcribing')
      try {
        const fd = new FormData()
        fd.append('audio', new Blob(parts, { type: rec.mimeType || 'audio/webm' }), 'question.webm')
        fd.append('lang', lang)
        const res = await fetch('/api/voice/transcribe', { method: 'POST', body: fd })
        if (!res.ok) throw new Error(String(res.status))
        const { text } = (await res.json()) as { text: string }
        if (text.trim()) cbs.current.onFinal(text.trim())
        else setError('no_speech')
      } catch {
        setError('voice_error')
      } finally {
        setStatus('idle')
      }
    }
    stopRef.current = stop
    rec.start()
    setStatus('listening')
  }, [lang])

  const start = useCallback(() => {
    setError(null)
    if (!secure) return setError('mic_insecure')
    stopSpeaking()
    if (useServer.current || !NativeRecognition) return void startServer()

    const rec = new NativeRecognition()
    rec.lang = speechLocale(lang)
    rec.interimResults = true
    rec.continuous = false
    rec.maxAlternatives = 1
    let finalText = ''
    let failed = false
    rec.onresult = (e) => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) finalText += r[0].transcript
        else interim += r[0].transcript
      }
      cbs.current.onInterim((finalText + interim).trim())
    }
    rec.onerror = (e) => {
      failed = true
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') setError('mic_denied')
      else if (e.error === 'no-speech') setError('no_speech')
      else if (e.error === 'network' || e.error === 'language-not-supported') {
        // The recogniser needs its cloud service; record and transcribe on our server instead.
        useServer.current = true
        setStatus('idle')
        void startServer()
        return
      } else if (e.error !== 'aborted') setError('voice_error')
    }
    rec.onend = () => {
      setStatus((s) => (s === 'listening' ? 'idle' : s))
      if (!failed && finalText.trim()) cbs.current.onFinal(finalText.trim())
    }
    stopRef.current = () => rec.stop()
    try {
      rec.start()
      setStatus('listening')
    } catch {
      setError('voice_error')
    }
  }, [lang, secure, startServer])

  const stop = useCallback(() => stopRef.current(), [])
  useEffect(() => () => stopRef.current(), [])

  return { status, error, level, supported, secure, start, stop, clearError: () => setError(null) }
}
