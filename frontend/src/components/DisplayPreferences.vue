<template>
  <details :class="['display-preferences', { inline }]" :open="inline">
    <summary>
      <i class="pi pi-eye" aria-hidden="true"></i>
      {{ $t('displayPreferences.title') }}
    </summary>
    <div class="preferences-panel">
      <label :for="`${idPrefix}-size`">
        <span>{{ $t('displayPreferences.textSize') }}</span>
        <select
          :id="`${idPrefix}-size`"
          :value="size"
          @change="$emit('update:size', $event.target.value)"
        >
          <option value="standard">{{ $t('displayPreferences.sizes.standard') }}</option>
          <option value="large">{{ $t('displayPreferences.sizes.large') }}</option>
          <option value="extra-large">{{ $t('displayPreferences.sizes.extraLarge') }}</option>
        </select>
      </label>
      <label :for="`${idPrefix}-font`">
        <span>{{ $t('displayPreferences.font') }}</span>
        <select
          :id="`${idPrefix}-font`"
          :value="font"
          @change="$emit('update:font', $event.target.value)"
        >
          <option value="system">{{ $t('displayPreferences.fonts.system') }}</option>
          <option value="sans">{{ $t('displayPreferences.fonts.sans') }}</option>
          <option value="serif">{{ $t('displayPreferences.fonts.serif') }}</option>
          <option value="kai">{{ $t('displayPreferences.fonts.kai') }}</option>
        </select>
      </label>
    </div>
  </details>
</template>

<script setup>
defineProps({
  idPrefix: { type: String, required: true },
  size: { type: String, required: true },
  font: { type: String, required: true },
  inline: { type: Boolean, default: false }
})

defineEmits(['update:size', 'update:font'])
</script>

<style scoped>
.display-preferences { position: relative; color: var(--text-color-primary); }
summary {
  display: flex;
  align-items: center;
  gap: .4rem;
  min-height: 2.35rem;
  padding: .45rem .65rem;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--surface-soft);
  font-size: var(--font-ui);
  font-weight: 650;
  cursor: pointer;
  list-style: none;
}
summary::-webkit-details-marker { display: none; }
summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.preferences-panel {
  position: absolute;
  z-index: 30;
  top: calc(100% + .4rem);
  right: 0;
  display: grid;
  width: min(19rem, 88vw);
  gap: .8rem;
  padding: .9rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--card-background);
  box-shadow: 0 12px 30px rgba(12, 41, 72, .14);
}
label { display: grid; gap: .35rem; font-size: var(--font-ui); font-weight: 650; }
select {
  width: 100%;
  min-height: 2.5rem;
  padding: .45rem .6rem;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: #fff;
  color: var(--text-color-primary);
}
.inline summary { display: none; }
.inline .preferences-panel {
  position: static;
  width: 100%;
  box-shadow: none;
}
</style>
