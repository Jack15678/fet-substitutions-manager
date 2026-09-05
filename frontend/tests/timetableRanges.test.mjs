import assert from 'node:assert/strict'
import { test } from 'node:test'
import { rangeErrors, rangesValid, sortedRanges } from '../src/components/timetableRanges.js'

test('effective periods validate independently and sort without changing the draft', () => {
  const january = { effective_from: '2027-01-15', effective_to: '2027-01-30' }
  const june = { effective_from: '2027-06-21', effective_to: '2027-07-10' }
  const draft = [june, january]
  assert.equal(rangesValid(draft), true)
  assert.deepEqual(sortedRanges(draft), [january, june])
  assert.deepEqual(draft, [june, january])
  assert.equal(rangesValid([]), false)
  assert.deepEqual(rangeErrors([{}]), ['importCenter.rangeRequired'])
  assert.deepEqual(rangeErrors([{ effective_from: '2027-07-10', effective_to: '2027-06-21' }]), ['importCenter.rangeReversed'])
  assert.deepEqual(rangeErrors([january, january]), ['importCenter.rangeOverlap', 'importCenter.rangeOverlap'])
  assert.equal(rangesValid([january, { effective_from: '2027-01-30', effective_to: '2027-02-01' }]), false)
  assert.equal(rangesValid([january, { effective_from: '2027-01-31', effective_to: '2027-02-01' }]), true)
  assert.equal(rangesValid([{ effective_from: '2027-01-15', effective_to: '2027-01-15' }]), true)
})
