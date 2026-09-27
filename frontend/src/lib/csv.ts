// Client-side CSV for the app's exports (LoL stats, pro-rata, t-shirt sizes,
// groceries) and the groceries import. Shaped for what the crew actually does
// with them: double-click, and Excel opens it — columns split, accents intact,
// numbers as numbers. No library, no backend endpoint.

export interface CsvFormat {
  separator: ';' | ','
  decimal: ',' | '.'
}

// French Excel splits on ";" and reads a decimal comma, English Excel "," and a
// point. Keyed on the UI language — the closest hint we have to the member's Excel.
export function csvFormatFor(language: string): CsvFormat {
  return language.startsWith('fr') ? { separator: ';', decimal: ',' } : { separator: ',', decimal: '.' }
}

export function formatCsvNumber(n: number, digits: number, fmt: CsvFormat): string {
  return n.toFixed(digits).replace('.', fmt.decimal)
}

// A plain number — possibly negative, decimal or a percentage — is data, not a
// formula, and keeps its leading "-".
const NUMBER = /^-?\d+([.,]\d+)?%?$/
// What Excel would run as a formula when it opens the file.
const FORMULA_START = /^[=+\-@\t\r]/

// Quoted when needed, and text starting like a formula gets an apostrophe:
// usernames and item names are typed by members, and Excel would otherwise
// evaluate "=HYPERLINK(...)" on open.
export function csvCell(value: string, separator: string): string {
  const safe = FORMULA_START.test(value) && !NUMBER.test(value) ? `'${value}` : value
  return safe.includes(separator) || /["\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe
}

// The BOM first: without it Excel reads UTF-8 as ANSI and mangles accents (é → Ã©).
export function buildCsv(rows: string[][], fmt: CsvFormat): string {
  return '﻿' + rows.map((r) => r.map((c) => csvCell(c, fmt.separator)).join(fmt.separator)).join('\r\n') + '\r\n'
}

export function downloadCsv(csv: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// Whichever of ";" and "," the first line uses more, outside quotes — so a
// file from either Excel (or from an export made before the ";" switch) reads.
function detectSeparator(text: string): ';' | ',' {
  let semicolons = 0
  let commas = 0
  let inQuotes = false
  for (const c of text) {
    if (c === '"') inQuotes = !inQuotes
    else if (!inQuotes && c === '\n') break
    else if (!inQuotes && c === ';') semicolons++
    else if (!inQuotes && c === ',') commas++
  }
  return semicolons > commas ? ';' : ','
}

// Minimal RFC 4180 parser (quoted fields, "" as an escaped quote, \r\n or \n
// line endings), reading back what buildCsv writes: BOM skipped, separator
// detected, a formula-guard apostrophe removed. Blank lines dropped.
export function parseCsv(text: string): string[][] {
  const src = text.replace(/^﻿/, '')
  const sep = detectSeparator(src)
  const unguard = (f: string) => (f.startsWith("'") && FORMULA_START.test(f.slice(1)) ? f.slice(1) : f)
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < src.length; i++) {
    const c = src[i]
    if (inQuotes) {
      if (c === '"') {
        if (src[i + 1] === '"') { field += '"'; i++ } else { inQuotes = false }
      } else {
        field += c
      }
    } else if (c === '"') {
      inQuotes = true
    } else if (c === sep) {
      row.push(unguard(field)); field = ''
    } else if (c === '\n') {
      row.push(unguard(field)); rows.push(row); row = []; field = ''
    } else if (c !== '\r') {
      field += c
    }
  }
  if (field !== '' || row.length > 0) { row.push(unguard(field)); rows.push(row) }
  return rows.filter((r) => r.some((c) => c.trim() !== ''))
}
