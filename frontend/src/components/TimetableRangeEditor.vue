<template>
  <div class="range-editor" :class="{ compact }">
    <p v-if="!compact" class="range-hint">{{ $t('importCenter.rangesHint') }}</p>
    <fieldset v-for="(range, index) in modelValue" :key="index" class="range-row" :disabled="disabled">
      <legend v-if="!compact || modelValue.length > 1">{{ $t('importCenter.rangeNumber', { count: index + 1 }) }}</legend>
      <div class="range-inputs">
        <label>{{ $t('importCenter.startDate') }}<input type="date" :value="range.effective_from" :aria-invalid="Boolean(errors[index])" @input="update(index, 'effective_from', $event.target.value)" /></label>
        <label>{{ $t('importCenter.endDate') }}<input type="date" :value="range.effective_to" :aria-invalid="Boolean(errors[index])" @input="update(index, 'effective_to', $event.target.value)" /></label>
        <Button v-if="!disabled && (!compact || modelValue.length > 1)" :label="$t('importCenter.removeRange')" :aria-label="$t('importCenter.removeRangeNumber', { count: index + 1 })" size="small" text severity="danger" :disabled="modelValue.length === 1" @click="remove(index)" />
      </div>
      <p v-if="errors[index]" class="range-error" role="status">{{ $t(errors[index]) }}</p>
    </fieldset>
    <Button v-if="!disabled" :label="$t('importCenter.addRange')" icon="pi pi-plus" size="small" :outlined="!compact" :text="compact" class="add-range" @click="add" />
    <p v-if="!compact" class="range-hint">{{ $t('importCenter.rangePriority') }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Button from 'primevue/button'
import { rangeErrors } from './timetableRanges'

const props = defineProps({ modelValue: { type: Array, required: true }, disabled: Boolean, compact: Boolean })
const emit = defineEmits(['update:modelValue'])
const errors = computed(() => rangeErrors(props.modelValue).map((error, index) =>
  props.compact && !props.modelValue[index].effective_from && !props.modelValue[index].effective_to ? '' : error))
const update = (index, field, value) => emit('update:modelValue', props.modelValue.map((range, i) => i === index ? { ...range, [field]: value } : range))
const remove = (index) => emit('update:modelValue', props.modelValue.filter((_, i) => i !== index))
const add = () => emit('update:modelValue', [...props.modelValue, { effective_from: '', effective_to: '' }])
</script>

<style scoped>
.range-editor { display: grid; gap: .65rem; min-width: 0; width: 100%; }
.range-hint { margin: 0; color: var(--text-color-secondary); font-size: var(--font-supporting); white-space: normal; line-height: 1.5; }
.range-row { min-width: 0; margin: 0; padding: .65rem; border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-background); }
.range-row legend { padding: 0 .3rem; font-size: var(--font-supporting); font-weight: 700; }
.range-inputs { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .5rem; }
.range-inputs label { display: grid; flex: 1 1 145px; min-width: 0; gap: .3rem; color: var(--text-color-secondary); font-size: var(--font-supporting); }
.range-inputs input { box-sizing: border-box; width: 100%; min-width: 0; min-height: 2.55rem; padding: .5rem; border: 1px solid #cfd6df; border-radius: 8px; background: #fff; color: var(--text-color-primary); }
.range-inputs input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.range-inputs input[aria-invalid=true] { border-color: #b54a40; }
.range-inputs .p-button { min-height: 2.55rem; }
.range-error { margin: .5rem 0 0; color: #96382f; white-space: normal; font-size: var(--font-supporting); }
.add-range { justify-self: start; }
.compact .range-row { padding: 0; border: 0; border-radius: 0; background: transparent; }
.compact .range-row + .range-row { margin-top: .25rem; padding-top: .75rem; border-top: 1px solid var(--border-color); }
.compact .range-row legend { padding: 0 0 .5rem; }
.compact .range-inputs { display: grid; gap: .75rem; }
.compact .range-inputs label { gap: .32rem; color: #344054; font-weight: 700; }
.compact .range-inputs input { padding: .6rem .7rem; font: inherit; }
.compact .range-inputs .p-button { justify-self: end; }
.compact .add-range { min-height: 1.75rem; padding: .2rem 0; font-size: var(--font-supporting); }
@media (max-width: 600px) { .range-inputs { flex-direction: column; align-items: stretch; } .range-inputs label { flex-basis: auto; } .range-inputs .p-button { align-self: flex-end; } }
</style>
