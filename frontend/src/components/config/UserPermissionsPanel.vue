<template>
  <section v-if="user" class="permissions-panel" :aria-labelledby="headingId">
    <header class="panel-header">
      <Button
        v-if="!isNew"
        class="mobile-back p-button-text p-button-sm"
        icon="pi pi-arrow-left"
        :label="$t('common.back')"
        @click="emit('back')"
      />
      <div>
        <p class="eyebrow">{{ isNew ? $t('config.users.addTitle') : $t('config.users.account') }}</p>
        <h2 :id="headingId" ref="headingRef" tabindex="-1">
          {{ isNew ? $t('config.users.newAccount') : user.username }}
        </h2>
      </div>
      <span v-if="!isNew" class="status" :class="{ inactive: !form.active }">
        {{ form.active ? $t('config.users.active') : $t('config.users.inactive') }}
      </span>
    </header>

    <div class="account-grid p-fluid">
      <div class="field">
        <label :for="`${idPrefix}-username`">{{ $t('config.users.username') }}</label>
        <InputText
          :id="`${idPrefix}-username`"
          v-model="form.username"
          :disabled="accountLocked"
          autocomplete="new-username"
          name="new-username"
        />
      </div>
      <div class="field">
        <label :for="`${idPrefix}-password`">{{ $t('config.users.password') }}</label>
        <Password
          :inputId="`${idPrefix}-password`"
          v-model="form.password"
          :disabled="accountLocked"
          :feedback="false"
          toggleMask
          :placeholder="isNew ? '' : $t('config.users.passwordOptional')"
          class="w-full password-with-eye"
          :inputProps="{ autocomplete: 'new-password', name: 'new-password' }"
        />
      </div>
      <div class="field">
        <label :for="`${idPrefix}-role`">{{ $t('config.users.role') }}</label>
        <Dropdown
          :inputId="`${idPrefix}-role`"
          v-model="form.role"
          :options="roleOptions"
          optionLabel="label"
          optionValue="value"
          :disabled="accountLocked"
          class="w-full"
        />
      </div>
      <div v-if="currentRole === 'super_admin'" class="field">
        <label :for="`${idPrefix}-institution`">{{ $t('config.users.institucio') }}</label>
        <Dropdown
          :inputId="`${idPrefix}-institution`"
          v-model="form.institucio"
          :options="institutions"
          optionLabel="label"
          optionValue="value"
          :disabled="accountLocked"
          class="w-full"
        />
      </div>
      <div class="field active-field">
        <Checkbox
          :inputId="`${idPrefix}-active`"
          v-model="form.active"
          :disabled="accountLocked"
          binary
        />
        <label :for="`${idPrefix}-active`">{{ $t('config.users.active') }}</label>
      </div>
    </div>

    <div class="permissions-heading">
      <div>
        <h3>{{ $t('config.users.permissions.title') }}</h3>
        <p>{{ $t('config.users.permissions.hint') }}</p>
      </div>
    </div>

    <div v-if="form.role !== 'user'" class="all-permissions" role="status">
      <i class="pi pi-shield" aria-hidden="true"></i>
      <div>
        <strong>{{ $t('config.users.permissions.allTitle') }}</strong>
        <p>{{ $t('config.users.permissions.allHint') }}</p>
      </div>
    </div>

    <template v-else>
      <div class="risk-notice">
        <i class="pi pi-exclamation-triangle" aria-hidden="true"></i>
        <span>{{ $t('config.users.permissions.riskHint') }}</span>
      </div>

      <div class="permission-groups">
        <section v-for="group in permissionGroups" :key="group.key" class="permission-group">
          <h4>{{ $t(`config.users.permissions.groups.${group.key}`) }}</h4>
          <div
            v-for="permission in group.permissions"
            :key="permission"
            class="permission-row"
          >
            <div class="permission-copy">
              <label :for="`${idPrefix}-${permission}`">
                {{ $t(`config.users.permissions.items.${permission.replace('.', '_')}.label`) }}
                <span v-if="highRiskPermissions.has(permission)" class="risk-badge">
                  {{ $t('config.users.permissions.highRisk') }}
                </span>
              </label>
              <small :id="`${idPrefix}-${permission}-description`">
                {{ $t(`config.users.permissions.items.${permission.replace('.', '_')}.description`) }}
              </small>
            </div>
            <span class="switch-control">
              <InputSwitch
                :inputId="`${idPrefix}-${permission}`"
                :modelValue="selectedPermissions.includes(permission)"
                :aria-describedby="`${idPrefix}-${permission}-description`"
                :disabled="accountLocked"
                @update:modelValue="togglePermission(permission, $event)"
              />
            </span>
          </div>
        </section>
      </div>
    </template>

    <p v-if="accountLocked" class="locked-note">
      <i class="pi pi-lock" aria-hidden="true"></i>
      {{ $t('config.users.superAdminLocked') }}
    </p>

    <footer class="panel-actions">
      <div v-if="!isNew" class="danger-actions">
        <Button
          :label="$t('config.users.deactivateAction')"
          icon="pi pi-ban"
          class="p-button-outlined p-button-danger"
          :disabled="accountLocked || saving"
          @click="emit('deactivate', user)"
        />
        <Button
          v-if="currentRole === 'super_admin'"
          :label="$t('common.delete')"
          icon="pi pi-trash"
          class="p-button-text p-button-danger"
          :disabled="accountLocked || saving"
          @click="emit('delete', user)"
        />
      </div>
      <Button v-if="isNew" :label="$t('common.cancel')" class="p-button-text" @click="emit('cancel')" />
      <Button
        :label="$t('common.save')"
        icon="pi pi-check"
        class="p-button-success save-button"
        :loading="saving"
        :disabled="accountLocked || !form.username.trim() || (isNew && !form.password)"
        @click="save"
      />
    </footer>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Dropdown from 'primevue/dropdown'
import InputSwitch from 'primevue/inputswitch'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'

const ALL_PERMISSIONS = [
  'workbench.view',
  'absence.create',
  'adjustment.confirm',
  'manual_arrangement.manage',
  'records.view',
  'records.manage',
  'statistics.view',
  'exports.download',
  'timetable.upload',
  'timetable.manage'
]

const DEFAULT_USER_PERMISSIONS = [
  'workbench.view',
  'absence.create',
  'adjustment.confirm',
  'records.view'
]

const permissionGroups = [
  { key: 'workbench', permissions: ALL_PERMISSIONS.slice(0, 4) },
  { key: 'records', permissions: ALL_PERMISSIONS.slice(4, 8) },
  { key: 'timetable', permissions: ALL_PERMISSIONS.slice(8) }
]

const requiredParents = {
  'absence.create': 'workbench.view',
  'adjustment.confirm': 'workbench.view',
  'manual_arrangement.manage': 'workbench.view',
  'exports.download': 'workbench.view',
  'records.manage': 'records.view'
}

const dependentChildren = Object.entries(requiredParents).reduce((result, [child, parent]) => {
  result[parent] = [...(result[parent] || []), child]
  return result
}, {})

const highRiskPermissions = new Set([
  'manual_arrangement.manage',
  'records.manage',
  'exports.download',
  'timetable.manage'
])

const props = defineProps({
  user: { type: Object, default: null },
  institutions: { type: Array, default: () => [] },
  currentRole: { type: String, default: null },
  isNew: { type: Boolean, default: false },
  saving: { type: Boolean, default: false }
})

const emit = defineEmits(['save', 'cancel', 'back', 'deactivate', 'delete'])
const { t } = useI18n()
const headingRef = ref(null)
const form = ref({ username: '', password: '', role: 'user', institucio: '', active: true })
const selectedPermissions = ref([])

const idPrefix = computed(() => `user-${props.isNew ? 'new' : props.user?.id || 'selected'}`)
const headingId = computed(() => `${idPrefix.value}-heading`)
const accountLocked = computed(() => !props.isNew && props.user?.role === 'super_admin')
const roleOptions = computed(() => {
  const roles = props.currentRole === 'super_admin'
    ? ['super_admin', 'admin', 'user']
    : ['admin', 'user']
  return roles.map((role) => ({ label: t(`config.users.roles.${role}`), value: role }))
})

watch(() => props.user, (user) => {
  if (!user) return
  form.value = {
    username: user.username || '',
    password: '',
    role: user.role || 'user',
    institucio: user.institucio || '',
    active: user.active !== false
  }
  selectedPermissions.value = Array.isArray(user.permissions)
    ? ALL_PERMISSIONS.filter((permission) => user.permissions.includes(permission))
    : [...DEFAULT_USER_PERMISSIONS]
}, { immediate: true })

const togglePermission = (permission, enabled) => {
  const next = new Set(selectedPermissions.value)
  if (enabled) {
    next.add(permission)
    if (requiredParents[permission]) next.add(requiredParents[permission])
  } else {
    next.delete(permission)
    dependentChildren[permission]?.forEach((child) => next.delete(child))
  }
  selectedPermissions.value = ALL_PERMISSIONS.filter((item) => next.has(item))
}

const save = () => {
  emit('save', {
    username: form.value.username.trim(),
    password: form.value.password,
    role: form.value.role,
    institucio: form.value.institucio,
    active: form.value.active,
    permissions: form.value.role === 'user' ? [...selectedPermissions.value] : [...ALL_PERMISSIONS]
  })
}

const focus = () => headingRef.value?.focus()
defineExpose({ focus })
</script>

<style scoped>
.permissions-panel {
  min-width: 0;
  padding: 1.25rem;
  background: #fff;
}

.panel-header,
.permissions-heading,
.panel-actions,
.danger-actions {
  display: flex;
  align-items: center;
}

.panel-header {
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.panel-header h2,
.permissions-heading h3,
.permission-group h4,
.panel-header p,
.permissions-heading p,
.all-permissions p {
  margin: 0;
}

.panel-header h2 {
  font-size: 1.35rem;
}

.panel-header h2:focus {
  outline: none;
}

.eyebrow {
  margin-bottom: 0.25rem !important;
  color: #64748b;
  font-size: var(--font-supporting);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.status {
  padding: 0.3rem 0.65rem;
  border-radius: 999px;
  background: #dcfce7;
  color: #166534;
  font-size: var(--font-supporting);
  font-weight: 700;
}

.status.inactive {
  background: #f1f5f9;
  color: #64748b;
}

.account-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid #e2e8f0;
}

.field {
  margin: 0;
}

.field > label {
  display: block;
  margin-bottom: 0.45rem;
  color: #334155;
  font-size: var(--font-ui);
  font-weight: 600;
}

.active-field {
  display: flex;
  align-items: center;
  align-self: end;
  min-height: 2.75rem;
  gap: 0.6rem;
}

.active-field > label {
  margin: 0;
}

.w-full,
:deep(.password-with-eye),
:deep(.password-with-eye .p-inputtext) {
  width: 100%;
}

.permissions-heading {
  justify-content: space-between;
  margin: 1.25rem 0 0.75rem;
}

.permissions-heading h3 {
  color: #1e293b;
  font-size: 1.05rem;
}

.permissions-heading p,
.all-permissions p {
  margin-top: 0.25rem;
  color: #64748b;
  font-size: var(--font-supporting);
}

.all-permissions,
.risk-notice,
.locked-note {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.9rem 1rem;
  border-radius: 8px;
}

.all-permissions {
  background: #eff6ff;
  color: #1d4ed8;
}

.risk-notice {
  margin-bottom: 0.9rem;
  background: #fff7ed;
  color: #9a3412;
  font-size: var(--font-supporting);
}

.permission-groups {
  display: grid;
  gap: 0.9rem;
}

.permission-group {
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.permission-group h4 {
  padding: 0.65rem 0.85rem;
  background: #f8fafc;
  color: #334155;
  font-size: var(--font-ui);
}

.permission-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 4rem;
  gap: 1rem;
  padding: 0.65rem 0.85rem;
  border-top: 1px solid #f1f5f9;
}

.permission-copy {
  min-width: 0;
}

.permission-copy label {
  display: block;
  color: #1e293b;
  font-weight: 600;
}

.permission-copy small {
  display: block;
  margin-top: 0.2rem;
  color: #64748b;
  line-height: 1.35;
}

.risk-badge {
  display: inline-block;
  margin-left: 0.35rem;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: #ffedd5;
  color: #9a3412;
  font-size: var(--font-supporting);
  vertical-align: 0.08rem;
}

.switch-control {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  min-width: 3.25rem;
  min-height: 2.75rem;
}

.locked-note {
  margin: 1rem 0 0;
  background: #f8fafc;
  color: #475569;
  font-size: var(--font-supporting);
}

.panel-actions {
  justify-content: flex-end;
  gap: 0.65rem;
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
}

.danger-actions {
  gap: 0.35rem;
  margin-right: auto;
}

.mobile-back {
  display: none;
}

@media (max-width: 720px) {
  .permissions-panel {
    padding: 0.75rem 0;
  }

  .panel-header {
    align-items: flex-start;
  }

  .mobile-back {
    display: inline-flex;
    min-height: 2.75rem;
    margin-left: -0.75rem;
  }

  .account-grid {
    grid-template-columns: 1fr;
  }

  .permission-row {
    min-height: 4.5rem;
  }

  .panel-actions {
    align-items: stretch;
    flex-direction: column-reverse;
  }

  .danger-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    margin: 0;
  }

  .save-button {
    min-height: 2.75rem;
  }
}
</style>
