export const sortedRanges = (ranges) => ranges.map(range => ({ ...range }))
  .sort((a, b) => a.effective_from.localeCompare(b.effective_from))

export const rangeErrors = (ranges) => ranges.map((range, index) => {
  if (!range.effective_from || !range.effective_to) return 'importCenter.rangeRequired'
  if (range.effective_from > range.effective_to) return 'importCenter.rangeReversed'
  if (ranges.some((other, otherIndex) => otherIndex !== index
    && other.effective_from && other.effective_to && other.effective_from <= other.effective_to
    && range.effective_from <= other.effective_to && other.effective_from <= range.effective_to)) {
    return 'importCenter.rangeOverlap'
  }
  return ''
})

export const rangesValid = (ranges) => ranges.length > 0 && rangeErrors(ranges).every(error => !error)
