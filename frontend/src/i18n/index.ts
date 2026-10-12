import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'
import type { Lang } from '@/lib/types'
import en from './en.json'
import hi from './hi.json'
import kn from './kn.json'
import ta from './ta.json'
import te from './te.json'

export const LANGUAGES: { code: Lang; label: string; english: string }[] = [
  { code: 'en', label: 'English', english: 'English' },
  { code: 'hi', label: 'हिन्दी', english: 'Hindi' },
  { code: 'te', label: 'తెలుగు', english: 'Telugu' },
  { code: 'ta', label: 'தமிழ்', english: 'Tamil' },
  { code: 'kn', label: 'ಕನ್ನಡ', english: 'Kannada' },
]

const SUPPORTED = LANGUAGES.map((l) => l.code)

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, hi: { translation: hi }, te: { translation: te }, ta: { translation: ta }, kn: { translation: kn } },
    fallbackLng: 'en',
    supportedLngs: SUPPORTED,
    nonExplicitSupportedLngs: true,
    load: 'languageOnly',
    interpolation: { escapeValue: false },
    detection: { order: ['querystring', 'localStorage', 'navigator'], lookupQuerystring: 'lng', lookupLocalStorage: 'hc.lang', caches: ['localStorage'] },
  })

i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng
})
document.documentElement.lang = i18n.resolvedLanguage ?? 'en'

export function currentLang(): Lang {
  const l = (i18n.resolvedLanguage ?? i18n.language ?? 'en').slice(0, 2) as Lang
  return SUPPORTED.includes(l) ? l : 'en'
}

export default i18n
