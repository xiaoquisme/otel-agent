import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clampDetailsWidth, MIN_DETAILS_PX, MIN_LEDGER_PX } from './detailsWidth.ts'

test('keeps the inspector at least 320px on a wide split', () => {
  assert.equal(clampDetailsWidth(100, 1200), MIN_DETAILS_PX)
})

test('leaves the ledger at least 280px', () => {
  assert.equal(clampDetailsWidth(5000, 1000), 1000 - MIN_LEDGER_PX)
})

test('uses the requested width inside the range', () => {
  assert.equal(clampDetailsWidth(480.4, 1200), 480)
})

test('gives the leftover to the inspector when the split cannot fit both minimums', () => {
  assert.equal(clampDetailsWidth(400, 500), 500 - MIN_LEDGER_PX)
})

test('treats a non-finite request as the inspector minimum', () => {
  assert.equal(clampDetailsWidth(Number.NaN, 1200), MIN_DETAILS_PX)
})

test('does not collapse an unmeasured split to zero', () => {
  assert.equal(clampDetailsWidth(410, 0), 410)
  assert.equal(clampDetailsWidth(Number.NaN, 0), MIN_DETAILS_PX)
})
