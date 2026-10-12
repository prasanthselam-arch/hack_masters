/** Mobile numbers and emails, validated as the user types. Mirrors backend/app/services/contact.py. */

export interface Country {
  iso: string
  dial: string
  name: string
  lengths: number[]
  pattern: RegExp
  example: string
}

export const COUNTRIES: Country[] = [
  { iso: 'IN', dial: '91', name: 'India', lengths: [10], pattern: /^[6-9]\d{9}$/, example: '98765 43210' },
  { iso: 'US', dial: '1', name: 'United States / Canada', lengths: [10], pattern: /^[2-9]\d{9}$/, example: '415 555 2671' },
  { iso: 'GB', dial: '44', name: 'United Kingdom', lengths: [10], pattern: /^7\d{9}$/, example: '7911 123456' },
  { iso: 'AE', dial: '971', name: 'UAE', lengths: [9], pattern: /^5\d{8}$/, example: '50 123 4567' },
  { iso: 'SA', dial: '966', name: 'Saudi Arabia', lengths: [9], pattern: /^5\d{8}$/, example: '51 234 5678' },
  { iso: 'QA', dial: '974', name: 'Qatar', lengths: [8], pattern: /^[3-7]\d{7}$/, example: '3312 3456' },
  { iso: 'KW', dial: '965', name: 'Kuwait', lengths: [8], pattern: /^[569]\d{7}$/, example: '5012 3456' },
  { iso: 'OM', dial: '968', name: 'Oman', lengths: [8], pattern: /^[79]\d{7}$/, example: '9212 3456' },
  { iso: 'BH', dial: '973', name: 'Bahrain', lengths: [8], pattern: /^[36]\d{7}$/, example: '3600 1234' },
  { iso: 'SG', dial: '65', name: 'Singapore', lengths: [8], pattern: /^[89]\d{7}$/, example: '8123 4567' },
  { iso: 'MY', dial: '60', name: 'Malaysia', lengths: [9, 10], pattern: /^1\d{8,9}$/, example: '12 345 6789' },
  { iso: 'AU', dial: '61', name: 'Australia', lengths: [9], pattern: /^4\d{8}$/, example: '412 345 678' },
  { iso: 'NZ', dial: '64', name: 'New Zealand', lengths: [8, 9, 10], pattern: /^2\d{7,9}$/, example: '21 123 4567' },
  { iso: 'NP', dial: '977', name: 'Nepal', lengths: [10], pattern: /^9[78]\d{8}$/, example: '984 1234567' },
  { iso: 'LK', dial: '94', name: 'Sri Lanka', lengths: [9], pattern: /^7\d{8}$/, example: '71 234 5678' },
  { iso: 'BD', dial: '880', name: 'Bangladesh', lengths: [10], pattern: /^1[3-9]\d{8}$/, example: '1812 345678' },
  { iso: 'DE', dial: '49', name: 'Germany', lengths: [10, 11], pattern: /^1[5-7]\d{8,9}$/, example: '151 23456789' },
  { iso: 'FR', dial: '33', name: 'France', lengths: [9], pattern: /^[67]\d{8}$/, example: '6 12 34 56 78' },
  { iso: 'IE', dial: '353', name: 'Ireland', lengths: [9], pattern: /^8\d{8}$/, example: '85 012 3456' },
  { iso: 'ZA', dial: '27', name: 'South Africa', lengths: [9], pattern: /^[6-8]\d{8}$/, example: '71 123 4567' },
]

export const DEFAULT_COUNTRY = COUNTRIES[0]
const byDial = (dial: string) => COUNTRIES.find((c) => c.dial === dial)

/** Country from a typed "+<code>…" (longest code wins), or null. */
export function detectCountry(raw: string): Country | null {
  const digits = raw.replace(/[\s\-().]/g, '').replace(/^00/, '+')
  if (!digits.startsWith('+')) return null
  for (const n of [3, 2, 1]) {
    const c = byDial(digits.slice(1, 1 + n))
    if (c) return c
  }
  return null
}

/** Splits a stored E.164 number into its country and national part. */
export function splitE164(value: string | null | undefined): { country: Country; national: string } {
  if (!value) return { country: DEFAULT_COUNTRY, national: '' }
  const c = detectCountry(value)
  if (c) return { country: c, national: value.replace(/\D/g, '').slice(c.dial.length) }
  return { country: DEFAULT_COUNTRY, national: value.replace(/\D/g, '') }
}

export function nationalDigits(national: string, country: Country) {
  const d = national.replace(/\D/g, '')
  return d.length > Math.max(...country.lengths) ? d.replace(/^0+/, '') : d
}

export type PhoneProblem = null | { key: 'phone_digits'; count: number; want: string; country: string } | { key: 'phone_invalid'; country: string }

export function phoneProblem(national: string, country: Country): PhoneProblem {
  const d = nationalDigits(national, country)
  if (!country.lengths.includes(d.length))
    return { key: 'phone_digits', count: d.length, want: country.lengths.join(' / '), country: country.name }
  if (!country.pattern.test(d)) return { key: 'phone_invalid', country: country.name }
  return null
}

export function toE164(national: string, country: Country) {
  return `+${country.dial}${nationalDigits(national, country)}`
}

/** "+919876543210" -> "+91 98765 43210" for display. */
export function formatPhone(value: string | null | undefined) {
  if (!value) return ''
  const { country, national } = splitE164(value)
  if (!value.startsWith('+')) return value
  const groups = country.dial === '91' && national.length === 10 ? [national.slice(0, 5), national.slice(5)] : national.match(/.{1,4}/g) ?? []
  return `+${country.dial} ${groups.join(' ')}`
}

const EMAIL = /^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/

export function emailValid(s: string) {
  return s.length <= 254 && EMAIL.test(s.trim()) && !s.includes('..')
}

/** A login field holds an email when it has an @ or letters; otherwise it is a phone number. */
export function looksLikeEmail(s: string) {
  return /[@A-Za-z]/.test(s)
}
