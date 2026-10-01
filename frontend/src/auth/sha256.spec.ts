import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'

import { ensureDigest, sha256 } from './sha256'

const hex = (b: Uint8Array): string => Buffer.from(b).toString('hex')
const nodeHash = (b: Uint8Array): string => createHash('sha256').update(b).digest('hex')

describe('sha256 для PKCE по HTTP', () => {
  it('совпадает с эталоном на границах блоков', () => {
    for (const len of [0, 1, 55, 56, 63, 64, 65, 96, 128, 1000]) {
      const data = new Uint8Array(len).map((_, i) => (i * 31 + 7) & 0xff)
      expect(hex(sha256(data))).toBe(nodeHash(data))
    }
    expect(hex(sha256(new TextEncoder().encode('abc')))).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    )
  })

  it('подставляет digest, только если crypto.subtle нет', async () => {
    const insecure: { subtle?: SubtleCrypto } = {}
    ensureDigest(insecure)
    const verifier = new TextEncoder().encode('a'.repeat(96))
    const out = await insecure.subtle!.digest('SHA-256', verifier)
    expect(hex(new Uint8Array(out))).toBe(nodeHash(verifier))
    await expect(insecure.subtle!.digest('SHA-1', verifier)).rejects.toThrow()

    const secure = { subtle: globalThis.crypto.subtle }
    ensureDigest(secure)
    expect(secure.subtle).toBe(globalThis.crypto.subtle)
  })
})
