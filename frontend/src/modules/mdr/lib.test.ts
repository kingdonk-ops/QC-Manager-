import { describe, expect, it } from 'vitest'
import { gateReady, moveSection, nextRevisionLabel, sha256Hex } from './lib'

describe('dossier builder helpers', () => {
  it('moves sections up and down, and not past the ends', () => {
    const s = ['index', 'itp', 'inspections']
    expect(moveSection(s, 2, -1)).toEqual(['index', 'inspections', 'itp'])
    expect(moveSection(s, 0, 1)).toEqual(['itp', 'index', 'inspections'])
    expect(moveSection(s, 0, -1)).toBe(s)
    expect(moveSection(s, 2, 1)).toBe(s)
  })

  it('names revisions like the server', () => {
    expect(nextRevisionLabel('review', 0)).toBe('A')
    expect(nextRevisionLabel('review', 25)).toBe('Z')
    expect(nextRevisionLabel('review', 26)).toBe('AA')
    expect(nextRevisionLabel('final', 0)).toBe('0')
  })

  it('treats not-available checks as non-blocking', () => {
    expect(
      gateReady([
        { key: 'a', blocking: true, status: 'not_available' },
        { key: 'b', blocking: false, status: 'fail' },
      ])
    ).toBe(true)
    expect(gateReady([{ key: 'c', blocking: true, status: 'fail' }])).toBe(
      false
    )
  })

  it('hashes like sha256sum', async () => {
    const data = new TextEncoder().encode('abc').buffer as ArrayBuffer
    expect(await sha256Hex(data)).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    )
  })
})
