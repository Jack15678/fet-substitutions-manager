import assert from 'node:assert/strict'
import test from 'node:test'

import { candidateOptionLabel } from './candidateLabel.js'

const label = {
  date: () => '8/10（一）',
  period: period => `第 ${period} 節`,
  join: items => items.join('、'),
  kind: kind => ({ direct_swap: '直接互調', three_cycle: '同班連鎖互調', emergency_cover: '同科緊急代課' })[kind],
}
const leg = (subject, teacher, period, from_date = '2026-08-10') => ({
  class_code: '1A', subject, teacher_names: [teacher], from_date, from_period: period,
})

test('direct swap fields all describe the counterpart lesson', () => {
  assert.equal(candidateOptionLabel({
    kind: 'direct_swap', completion_date: '2026-08-10', moved_lessons: 2,
    legs: [leg('中文', 'A老師', 1), leg('英文', 'B老師', 4)],
  }, label), '8/10（一）第 4 節｜B老師｜1A 英文｜直接互調')
})

test('cycle lists each counterpart lesson without ambiguous subject arrows', () => {
  assert.equal(candidateOptionLabel({
    kind: 'three_cycle', completion_date: '2026-08-10', moved_lessons: 3,
    legs: [leg('中文', 'A老師', 1), leg('英文', 'B老師', 2), leg('數學', 'C老師', 3)],
  }, label), '8/10（一）第 2 節 B老師・1A 英文 → 8/10（一）第 3 節 C老師・1A 數學｜3 · 同班連鎖互調')
})

test('emergency cover names the replacement teacher', () => {
  assert.equal(candidateOptionLabel({
    kind: 'emergency_cover', completion_date: '2026-08-10', moved_lessons: 1,
    legs: [{ ...leg('中文', 'A老師', 1), replacement_teacher_name: 'C老師' }],
  }, label), '8/10（一）第 1 節｜C老師｜1A 中文｜同科緊急代課')
})
