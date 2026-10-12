/**
 * Repairs Markdown the model sometimes flattens: a whole table on one line ("| a | b | | --- | --- | | 1 | 2 |"),
 * or a table glued to the paragraph above it (GFM needs a blank line in between).
 */
export function normalizeMarkdown(md: string): string {
  const lines = md
    .replace(/\r\n/g, '\n')
    .split('\n')
    .flatMap((line) => (/\|\s*:?-{3,}:?\s*\|/.test(line) && /\|\s+\|/.test(line) ? line.replace(/\|\s+\|/g, '|\n|').split('\n') : [line]))
  return lines
    .map((l, i) => {
      const prev = i > 0 ? lines[i - 1].trim() : ''
      return l.trim().startsWith('|') && prev && !prev.startsWith('|') ? `\n${l}` : l
    })
    .join('\n')
}

/** Plain text for copying or reading aloud. */
export function markdownToText(md: string): string {
  return normalizeMarkdown(md)
    .split('\n')
    .filter((l) => !/^\s*\|?\s*:?-{3,}/.test(l))
    .map((l) => l.replace(/^\s*\|\s*|\s*\|\s*$/g, '').replace(/\s*\|\s*/g, ', ').replace(/[*_#>`]/g, ''))
    .join('\n')
    .trim()
}
