import { ChevronLeft, ChevronRight, ExternalLink, RotateCw, ZoomIn, ZoomOut } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from './ui'

export function PageViewer({ pages, fileUrl, page, onPage }: { pages: string[]; fileUrl: string; page?: number; onPage?: (n: number) => void }) {
  const { t } = useTranslation()
  const [internal, setInternal] = useState(1)
  const [zoom, setZoom] = useState(1)
  const [rotations, setRotations] = useState<Record<number, number>>({})
  const current = Math.min(Math.max(page ?? internal, 1), Math.max(pages.length, 1))
  const go = (n: number) => (onPage ? onPage(n) : setInternal(n))
  const rot = rotations[current] ?? 0
  const rotate = () => setRotations((r) => ({ ...r, [current]: (rot + 90) % 360 }))

  if (!pages.length)
    return (
      <div className="flex h-64 items-center justify-center rounded-xl bg-slate-100 text-sm text-slate-500">
        <a href={fileUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-brand-700 hover:underline">
          {t('review.original')} <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>
    )

  return (
    <div className="theme-fixed flex h-full flex-col overflow-hidden rounded-xl bg-slate-800 ring-1 ring-slate-700">
      <div className="flex items-center justify-between gap-2 border-b border-slate-700 px-2 py-1.5 text-slate-200">
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" className="text-slate-200 hover:bg-slate-700" aria-label={t('viewer.previous')} disabled={current <= 1} onClick={() => go(current - 1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-16 text-center text-xs">
            {t('common.page')} {current} / {pages.length}
          </span>
          <Button size="icon" variant="ghost" className="text-slate-200 hover:bg-slate-700" aria-label={t('viewer.next')} disabled={current >= pages.length} onClick={() => go(current + 1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" className="text-slate-200 hover:bg-slate-700" aria-label={t('viewer.zoom_out')} onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="w-10 text-center text-xs">{Math.round(zoom * 100)}%</span>
          <Button size="icon" variant="ghost" className="text-slate-200 hover:bg-slate-700" aria-label={t('viewer.zoom_in')} onClick={() => setZoom((z) => Math.min(4, z + 0.25))}>
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button size="icon" variant="ghost" className="text-slate-200 hover:bg-slate-700" aria-label={t('viewer.rotate')} onClick={rotate}>
            <RotateCw className="h-4 w-4" />
          </Button>
          <a
            href={fileUrl}
            target="_blank"
            rel="noreferrer"
            title={t('review.original')}
            aria-label={t('review.original')}
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-200 transition-colors hover:bg-slate-700"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>
      <div className="scrollbar-thin flex-1 overflow-auto p-3">
        <img
          src={pages[current - 1]}
          alt={`${t('common.page')} ${current}`}
          className="mx-auto max-w-none origin-top rounded bg-white shadow-lg transition-transform"
          style={{ width: `${zoom * 100}%`, transform: rot ? `rotate(${rot}deg)` : undefined }}
        />
      </div>
    </div>
  )
}
