export const candidateOptionLabel = (candidate, label) => {
  const [target, ...others] = candidate.legs || []
  if (!target) return `${label.kind(candidate.kind)} · ${candidate.reason}`
  if (candidate.kind === 'direct_swap') {
    const other = others[0]
    return `${label.date(other.from_date)}${label.period(other.from_period)}｜${label.join(other.teacher_names)}｜${other.class_code} ${other.subject}｜${label.kind(candidate.kind)}`
  }
  if (candidate.kind === 'three_cycle') {
    const lessons = others.map(leg => (
      `${label.date(leg.from_date)}${label.period(leg.from_period)} ${label.join(leg.teacher_names)}・${leg.class_code} ${leg.subject}`
    )).join(' → ')
    return `${lessons}｜${candidate.moved_lessons} · ${label.kind(candidate.kind)}`
  }
  if (candidate.kind === 'emergency_cover') {
    return `${label.date(target.from_date)}${label.period(target.from_period)}｜${target.replacement_teacher_name}｜${target.class_code} ${target.subject}｜${label.kind(candidate.kind)}`
  }
  return `${label.kind(candidate.kind)} · ${candidate.reason}`
}
