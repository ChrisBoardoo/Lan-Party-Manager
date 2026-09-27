import { describe, it, expect } from 'vitest'
import { buildCsv, csvCell, csvFormatFor, formatCsvNumber, parseCsv } from './csv'

const FR = csvFormatFor('fr')
const EN = csvFormatFor('en')

describe('csvFormatFor', () => {
  it('follows the Excel of each language', () => {
    expect(FR).toEqual({ separator: ';', decimal: ',' })
    expect(csvFormatFor('fr-FR')).toEqual(FR)
    expect(EN).toEqual({ separator: ',', decimal: '.' })
    expect(csvFormatFor('en-GB')).toEqual(EN)
  })

  it('writes numbers with the matching decimal mark', () => {
    expect(formatCsvNumber(12.5, 2, FR)).toBe('12,50')
    expect(formatCsvNumber(12.5, 2, EN)).toBe('12.50')
  })
})

describe('buildCsv', () => {
  it('starts with a BOM, uses the separator and ends every line with CRLF', () => {
    expect(buildCsv([['Joueur', 'Montant'], ['bob', '12,50']], FR)).toBe('﻿Joueur;Montant\r\nbob;12,50\r\n')
    expect(buildCsv([['Player', 'Amount'], ['bob', '12.50']], EN)).toBe('﻿Player,Amount\r\nbob,12.50\r\n')
  })

  it('quotes a field holding the separator, a quote or a line break', () => {
    expect(csvCell('a;b', ';')).toBe('"a;b"')
    expect(csvCell('a,b', ';')).toBe('a,b')
    expect(csvCell('a,b', ',')).toBe('"a,b"')
    expect(csvCell('say "hi"', ';')).toBe('"say ""hi"""')
    expect(csvCell('two\nlines', ';')).toBe('"two\nlines"')
  })

  it('defuses text Excel would run as a formula, but keeps numbers as numbers', () => {
    expect(csvCell('=HYPERLINK("x")', ';')).toBe(`"'=HYPERLINK(""x"")"`)
    expect(csvCell('+33 6', ';')).toBe("'+33 6")
    expect(csvCell('@bob', ';')).toBe("'@bob")
    expect(csvCell('-sel', ';')).toBe("'-sel")
    expect(csvCell('-5', ';')).toBe('-5')
    expect(csvCell('-12,50', ',')).toBe('"-12,50"')
    expect(csvCell('33,3%', ';')).toBe('33,3%')
  })
})

describe('parseCsv', () => {
  it('still reads the old comma-separated, fully quoted exports', () => {
    expect(parseCsv('"Catégorie","Article"\r\n"Boissons","Coca, 6x"\r\n')).toEqual([
      ['Catégorie', 'Article'],
      ['Boissons', 'Coca, 6x'],
    ])
  })

  it('reads a French Excel file: BOM, semicolons, and commas inside fields', () => {
    expect(parseCsv('﻿Catégorie;Article;Quantité\r\nBoissons;Coca, 6x;1,5 L\r\n')).toEqual([
      ['Catégorie', 'Article', 'Quantité'],
      ['Boissons', 'Coca, 6x', '1,5 L'],
    ])
  })

  it('counts separators outside quotes only', () => {
    expect(parseCsv('"a;b",c\r\n')).toEqual([['a;b', 'c']])
  })

  it('drops blank lines', () => {
    expect(parseCsv('a;b\n\n;\nc;d\n')).toEqual([['a', 'b'], ['c', 'd']])
  })

  it('gets back exactly what buildCsv wrote, in both formats', () => {
    const rows = [
      ['Catégorie', 'Article', 'Qté'],
      ['Été', 'a;b', 'x,y'],
      ['say "hi"', 'two\nlines', ''],
      ['=1+1', '-sel', '-5'],
      ['@bob', '+33', '12,50'],
    ]
    expect(parseCsv(buildCsv(rows, FR))).toEqual(rows)
    expect(parseCsv(buildCsv(rows, EN))).toEqual(rows)
  })
})
