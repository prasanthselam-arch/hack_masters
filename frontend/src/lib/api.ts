import type {
  Account,
  ChatReply,
  DocumentInfo,
  Health,
  Lang,
  Medication,
  Observation,
  Patient,
  Profile,
  ReviewPayload,
  Summary,
  TimelineEvent,
  TrendSeries,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Fired when the session has expired or was revoked, so the app can return to the sign-in screen. */
export const UNAUTHORIZED_EVENT = 'hc:unauthorized'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (res.status === 401 && !path.startsWith('/api/auth/')) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = errorText(body.detail ?? body)
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

/** FastAPI validation errors arrive as a list of {loc, msg}; show just the messages. */
function errorText(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail
      .map((d) => String((d as { msg?: string }).msg ?? d).replace(/^Value error, /, ''))
      .join('. ')
  return JSON.stringify(detail)
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  health: () => request<Health>('/api/health'),
  me: () => request<Account>('/api/auth/me'),
  register: (body: { name: string; login: string; password: string }) => request<Account>('/api/auth/register', json('POST', body)),
  login: (body: { login: string; password: string }) => request<Account>('/api/auth/login', json('POST', body)),
  logout: () => request<{ signed_out: boolean }>('/api/auth/logout', json('POST')),
  updateMe: (body: { name?: string; login?: string; current_password?: string }) => request<Account>('/api/auth/me', json('PATCH', body)),
  changePassword: (body: { current_password: string; new_password: string }) =>
    request<{ changed: boolean }>('/api/auth/password', json('POST', body)),
  deleteAccount: (password: string) => request<{ deleted: boolean }>('/api/auth/delete-account', json('POST', { password })),
  patients: () => request<Patient[]>('/api/patients'),
  createPatient: (body: Partial<Patient>) => request<Patient>('/api/patients', json('POST', body)),
  updatePatient: (id: string, body: Partial<Patient>) => request<Patient>(`/api/patients/${id}`, json('PATCH', body)),
  deletePatient: (id: string) => request<{ deleted: boolean }>(`/api/patients/${id}`, json('DELETE')),
  profile: (id: string) => request<Profile>(`/api/patients/${id}/profile`),
  timeline: (id: string) => request<TimelineEvent[]>(`/api/patients/${id}/timeline`),
  trends: (id: string) => request<TrendSeries[]>(`/api/patients/${id}/trends`),
  medications: (id: string) => request<Medication[]>(`/api/patients/${id}/medications`),
  observations: (id: string) => request<Observation[]>(`/api/patients/${id}/observations`),
  documents: (id: string) => request<DocumentInfo[]>(`/api/patients/${id}/documents`),
  upload: (id: string, files: File[]) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    return request<DocumentInfo[]>(`/api/patients/${id}/documents`, { method: 'POST', body: fd })
  },
  document: (docId: string) => request<DocumentInfo>(`/api/documents/${docId}`),
  refreshReview: (docId: string, payload: ReviewPayload) =>
    request<ReviewPayload>(`/api/documents/${docId}/review/refresh`, json('POST', payload)),
  confirm: (docId: string, payload: ReviewPayload) =>
    request<{ document: DocumentInfo; saved: Record<string, number> }>(`/api/documents/${docId}/confirm`, json('POST', payload)),
  reprocess: (docId: string) => request<DocumentInfo>(`/api/documents/${docId}/reprocess`, json('POST')),
  deleteDocument: (docId: string) => request<{ deleted: boolean }>(`/api/documents/${docId}`, json('DELETE')),
  documentFhir: (docId: string) => request<{ bundle: Record<string, unknown>; validation_errors: string[] }>(`/api/documents/${docId}/fhir`),
  documentSummary: (docId: string, lang: Lang) => request<Summary>(`/api/documents/${docId}/summary?lang=${lang}`),
  patientSummary: (id: string, lang: Lang) => request<Summary>(`/api/patients/${id}/summary?lang=${lang}`),
  chat: (id: string, message: string, history: { role: string; content: string }[], lang: Lang) =>
    request<ChatReply>(`/api/patients/${id}/chat`, json('POST', { message, history, lang })),
  abhaInit: (id: string, body: { abha_number?: string; abha_address?: string }) =>
    request<{ txn_id: string; message: string; demo_otp_hint: string }>(`/api/patients/${id}/abha/init`, json('POST', body)),
  abhaConfirm: (id: string, txn_id: string, otp: string) =>
    request<{ linked: boolean; abha_number: string; abha_address: string }>(`/api/patients/${id}/abha/confirm`, json('POST', { txn_id, otp })),
  abhaImport: (id: string, hi_types: string[]) =>
    request<{
      consent: Record<string, unknown> & { consent_id: string; hi_types: string[]; permission: { date_range: { from: string; to: string } } }
      imported: { id: string; title: string; type: string; date: string | null }[]
      fhir_validation_errors: string[]
      bundles: number
    }>(`/api/patients/${id}/abha/import`, json('POST', { hi_types })),
  abhaUnlink: (id: string) => request<{ linked: boolean }>(`/api/patients/${id}/abha`, json('DELETE')),
  fhirExportUrl: (id: string) => `/api/patients/${id}/fhir`,
}
