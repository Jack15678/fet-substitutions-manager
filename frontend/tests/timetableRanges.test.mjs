import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, reactive } from 'vue'
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

test('compact range editor starts quietly while retaining validation and multiple periods', () => {
  const { descriptor } = parse(readFileSync(new URL('../src/components/TimetableRangeEditor.vue', import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'range-editor-test' }).content.replace(/^import .+$/gm, '').replace('export default', 'return')
  const component = new Function('computed', 'Button', 'rangeErrors', script)(computed, {}, rangeErrors)
  const props = reactive({ compact: true, modelValue: [{ effective_from: '', effective_to: '' }] })
  const view = component.setup(props, { expose() {}, emit: (_, value) => { props.modelValue = value } })
  assert.deepEqual(view.errors.value, [''])
  assert.equal(rangesValid(props.modelValue), false)
  view.update(0, 'effective_from', '2026-12-08')
  assert.deepEqual(view.errors.value, ['importCenter.rangeRequired'])
  view.update(0, 'effective_to', '2026-12-01')
  assert.deepEqual(view.errors.value, ['importCenter.rangeReversed'])
  view.update(0, 'effective_to', '2026-12-20')
  view.add()
  assert.equal(props.modelValue.length, 2)
  view.update(1, 'effective_from', '2026-12-15')
  view.update(1, 'effective_to', '2026-12-22')
  assert.deepEqual(view.errors.value, ['importCenter.rangeOverlap', 'importCenter.rangeOverlap'])
  view.remove(1)
  assert.equal(rangesValid(props.modelValue), true)
  props.compact = false
  view.add()
  assert.equal(view.errors.value[1], 'importCenter.rangeRequired', 'full editor keeps existing validation')
})
