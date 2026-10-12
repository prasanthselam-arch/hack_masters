import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { normalizeMarkdown } from '@/lib/markdown'

const components: Components = {
  p: ({ children }) => <p className="mb-2.5 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  ul: ({ children }) => <ul className="mb-2.5 list-disc space-y-1 pl-5 marker:text-brand-500 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2.5 list-decimal space-y-1 pl-5 marker:text-slate-400 last:mb-0">{children}</ol>,
  h1: ({ children }) => <p className="mb-1.5 font-semibold text-slate-900">{children}</p>,
  h2: ({ children }) => <p className="mb-1.5 font-semibold text-slate-900">{children}</p>,
  h3: ({ children }) => <p className="mb-1.5 font-semibold text-slate-900">{children}</p>,
  a: ({ children }) => <span className="font-medium text-brand-700">{children}</span>,
  code: ({ children }) => <span className="rounded bg-slate-100 px-1 font-mono text-[0.85em]">{children}</span>,
  table: ({ children }) => (
    <div className="scrollbar-thin my-3 overflow-x-auto rounded-xl ring-1 ring-slate-200">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">{children}</thead>,
  tr: ({ children }) => <tr className="border-t border-slate-100 first:border-t-0 even:bg-slate-50/50">{children}</tr>,
  th: ({ children }) => <th className="whitespace-nowrap px-3 py-2 font-semibold">{children}</th>,
  td: ({ children }) => <td className="px-3 py-2 align-top text-slate-700">{children}</td>,
}

export function ChatMarkdown({ text }: { text: string }) {
  return (
    <div className="text-[0.925rem] leading-relaxed text-slate-700">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {normalizeMarkdown(text)}
      </Markdown>
    </div>
  )
}
