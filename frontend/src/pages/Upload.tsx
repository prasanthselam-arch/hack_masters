import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, FileImage, FileText, Lightbulb, RotateCcw, UploadCloud } from 'lucide-react'
import { useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { PipelineSteps, StageLabel } from '@/components/medical'
import { Badge, Button, Card, CardHeader, ErrorNote, PageHeader } from '@/components/ui'
import { api } from '@/lib/api'
import { useActivePatient, useLang } from '@/lib/patient'
import type { DocumentInfo } from '@/lib/types'
import { cn, fmtDate } from '@/lib/utils'

const ACCEPT = {
  'application/pdf': ['.pdf'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/webp': ['.webp'],
  'image/tiff': ['.tif', '.tiff'],
  'image/bmp': ['.bmp'],
}

const isActive = (d: DocumentInfo) => d.status === 'queued' || d.status === 'processing'

export default function UploadPage() {
  const { t } = useTranslation()
  const patient = useActivePatient()
  const qc = useQueryClient()
  const camera = useRef<HTMLInputElement>(null)

  const docs = useQuery({
    queryKey: ['documents', patient.id],
    queryFn: () => api.documents(patient.id),
    refetchInterval: (q) => (q.state.data?.some(isActive) ? 1500 : false),
  })

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['documents', patient.id] })
    qc.invalidateQueries({ queryKey: ['profile', patient.id] })
    qc.invalidateQueries({ queryKey: ['timeline', patient.id] })
  }

  const upload = useMutation({
    mutationFn: (files: File[]) => api.upload(patient.id, files),
    onSuccess: refreshAll,
  })
  const reprocess = useMutation({ mutationFn: api.reprocess, onSuccess: refreshAll })

  const { getRootProps, getInputProps, isDragActive, fileRejections, open } = useDropzone({
    accept: ACCEPT,
    maxSize: 25 * 1024 * 1024,
    onDrop: (files) => files.length && upload.mutate(files),
  })

  return (
    <div className="space-y-6">
      <PageHeader title={t('upload.title')} subtitle={t('upload.subtitle')} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div
            {...getRootProps()}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-white px-6 py-14 text-center transition-colors',
              isDragActive ? 'border-brand-500 bg-brand-50' : 'border-slate-300 hover:border-brand-400 hover:bg-slate-50',
            )}
          >
            <input {...getInputProps()} />
            <div className="rounded-full bg-brand-50 p-4 text-brand-600">
              <UploadCloud className="h-8 w-8" />
            </div>
            <p className="mt-4 text-lg font-medium text-slate-900">{t('upload.drop')}</p>
            <p className="mt-1 text-sm text-slate-500">{t('upload.formats')}</p>
            <div className="mt-5 flex flex-wrap items-center justify-center gap-3" onClick={(e) => e.stopPropagation()}>
              <Button type="button" loading={upload.isPending} onClick={open}>
                <FileText className="h-4 w-4" />
                {upload.isPending ? t('upload.uploading') : t('upload.browse')}
              </Button>
              <span className="text-sm text-slate-400">{t('upload.or')}</span>
              <Button type="button" variant="secondary" onClick={() => camera.current?.click()} disabled={upload.isPending}>
                <Camera className="h-4 w-4" />
                {t('upload.camera')}
              </Button>
              <input
                ref={camera}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={(e) => {
                  const f = Array.from(e.target.files ?? [])
                  if (f.length) upload.mutate(f)
                  e.target.value = ''
                }}
              />
            </div>
          </div>
          {upload.error && <ErrorNote error={upload.error} />}
          {fileRejections.length > 0 && (
            <ErrorNote error={fileRejections.map((r) => `${r.file.name}: ${r.errors.map((e) => e.message).join(', ')}`).join(' · ')} />
          )}

          <Card>
            <CardHeader title={t('upload.queue_title')} />
            {docs.data && docs.data.length > 0 ? (
              <ul className="divide-y divide-slate-100">
                {docs.data.slice(0, 15).map((d) => (
                  <UploadRow key={d.id} d={d} onRetry={() => reprocess.mutate(d.id)} />
                ))}
              </ul>
            ) : (
              <p className="px-5 py-6 text-sm text-slate-500">—</p>
            )}
          </Card>
        </div>

        <Card className="h-fit p-5">
          <h3 className="flex items-center gap-2 font-semibold text-slate-900">
            <Lightbulb className="h-5 w-5 text-amber-500" />
            {t('upload.tips_title')}
          </h3>
          <ul className="mt-3 space-y-3 text-sm text-slate-600">
            {['tip1', 'tip2', 'tip3'].map((k, i) => (
              <li key={k} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">{i + 1}</span>
                {t(`upload.${k}`)}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}

function UploadRow({ d, onRetry }: { d: DocumentInfo; onRetry: () => void }) {
  const { t } = useTranslation()
  const lang = useLang()
  const Icon = d.mime_type === 'application/pdf' ? FileText : FileImage
  const timing = d.pipeline_log
    .filter((l) => l.model)
    .map((l) => `${t(`upload.stage.${l.stage}`, { defaultValue: l.stage })} ${(l.ms / 1000).toFixed(1)}s`)
    .join(' · ')
  return (
    <li className="px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="rounded-lg bg-slate-100 p-2 text-slate-500">
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate font-medium text-slate-900">{d.title || d.filename}</p>
            <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
              {d.doc_type && <Badge>{t(`doctype.${d.doc_type}`)}</Badge>}
              {d.handwritten && <Badge>{t('review.handwritten')}</Badge>}
              {d.languages.length > 0 && <Badge>{d.languages.join(' + ').toUpperCase()}</Badge>}
              {d.stats && (
                <span>
                  {t('review.items', { count: d.stats.items_total })}
                  {d.stats.needs_review > 0 && ` · ${t('review.needs_review', { count: d.stats.needs_review })}`}
                </span>
              )}
              <span>{fmtDate(d.created_at, lang, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {d.status === 'review' && (
            <Link to={`/documents/${d.id}/review`}>
              <Button size="sm">{t('upload.review_btn')}</Button>
            </Link>
          )}
          {d.status === 'confirmed' && (
            <Link to={`/documents/${d.id}`}>
              <Button size="sm" variant="secondary">
                {t('upload.view_btn')}
              </Button>
            </Link>
          )}
          {d.status === 'failed' && (
            <Button size="sm" variant="secondary" onClick={onRetry}>
              <RotateCcw className="h-4 w-4" />
              {t('upload.retry_btn')}
            </Button>
          )}
        </div>
      </div>
      <div className="mt-3 flex items-center gap-4">
        <div className="flex-1">
          <PipelineSteps stage={d.stage} status={d.status} />
        </div>
        <div className="w-56 shrink-0 text-right">
          <StageLabel stage={d.stage} status={d.status} />
        </div>
      </div>
      {d.status === 'failed' && d.error && <p className="mt-2 text-xs text-red-600">{t('upload.failed')}: {d.error.slice(0, 200)}</p>}
      {timing && d.status !== 'processing' && <p className="mt-1.5 text-xs text-slate-400">{timing}</p>}
    </li>
  )
}
