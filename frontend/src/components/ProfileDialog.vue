<template>
  <Dialog
    :visible="visible"
    @update:visible="handleVisibleChange"
    :modal="true"
    :style="{ width: 'min(36rem, calc(100vw - 2rem))' }"
    :closable="true"
    class="profile-dialog"
  >
    <template #header>
      <div class="profile-header">
        <span>{{ $t('profile.title') }}</span>
      </div>
    </template>
    <div class="profile-form">
      <div class="profile-info">
        <span class="profile-label">{{ $t('profile.username') }}</span>
        <span class="profile-value">{{ username || '—' }}</span>
      </div>

      <div class="field">
        <label for="current-password">{{ $t('profile.currentPassword') }}</label>
        <Password
          inputId="current-password"
          v-model="currentPassword"
          :feedback="false"
          toggleMask
          autocomplete="new-password"
          :inputProps="{ 'data-form-type': 'other', 'data-lpignore': 'true' }"
          class="w-full password-with-eye"
        />
      </div>

      <div class="field">
        <label for="new-password">{{ $t('profile.newPassword') }}</label>
        <Password
          inputId="new-password"
          v-model="newPassword"
          :feedback="false"
          toggleMask
          autocomplete="new-password"
          :inputProps="{ 'data-form-type': 'other', 'data-lpignore': 'true' }"
          class="w-full password-with-eye"
        />
      </div>

      <div class="field">
        <label for="confirm-password">{{ $t('profile.confirmPassword') }}</label>
        <Password
          inputId="confirm-password"
          v-model="confirmPassword"
          :feedback="false"
          toggleMask
          autocomplete="new-password"
          :inputProps="{ 'data-form-type': 'other', 'data-lpignore': 'true' }"
          class="w-full password-with-eye"
        />
      </div>

      <p v-if="errorMessage" class="profile-error" role="alert">{{ errorMessage }}</p>
      <p v-if="successMessage" class="profile-success" role="status">{{ successMessage }}</p>
    </div>

    <template #footer>
      <Button
        :label="$t('common.cancel')"
        class="profile-cancel"
        @click="handleVisibleChange(false)"
      />
      <Button
        :label="$t('common.save')"
        class="profile-save"
        :loading="saving"
        :disabled="!canSave"
        @click="guardarPassword"
      />
    </template>
  </Dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Dialog from 'primevue/dialog'
import Password from 'primevue/password'
import Button from 'primevue/button'

const { t } = useI18n()

const props = defineProps({
  visible: {
    type: Boolean,
    required: true
  },
  username: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:visible'])

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const saving = ref(false)
const canSave = computed(() => {
  return currentPassword.value && newPassword.value && confirmPassword.value && newPassword.value === confirmPassword.value
})

const resetForm = () => {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  errorMessage.value = ''
  successMessage.value = ''
  saving.value = false
}

const handleVisibleChange = (value) => {
  emit('update:visible', value)
  if (!value) {
    resetForm()
  }
}

const guardarPassword = async () => {
  if (newPassword.value !== confirmPassword.value) {
    errorMessage.value = t('profile.passwordMismatch')
    return
  }

  saving.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await axios.put('/api/users/profile/password', {
      current_password: currentPassword.value,
      new_password: newPassword.value
    })
    successMessage.value = t('profile.passwordUpdated')
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || t('profile.passwordError')
  } finally {
    saving.value = false
  }
}

watch(
  () => props.visible,
  (next) => {
    if (!next) {
      resetForm()
    }
  }
)
</script>

<style scoped>
.profile-form {
  display: flex;
  flex-direction: column;
  gap: 1.35rem;
}

.profile-form .field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.profile-form label,
.profile-label {
  color: var(--text-color-primary);
  font-size: var(--font-ui);
  font-weight: 650;
}

.profile-info {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.profile-value {
  min-height: 3rem;
  padding: 0.75rem 1rem;
  border-radius: 9px;
  background: var(--surface-soft);
  color: var(--primary-color-dark);
  font-size: var(--font-data);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.profile-error,
.profile-success {
  margin: -0.25rem 0 0;
  padding: 0.7rem 0.85rem;
  border-radius: 7px;
  font-size: var(--font-ui);
}

.profile-error {
  background: #fff1f0;
  color: #9b2c24;
}

.profile-success {
  background: #edf7f1;
  color: #216a42;
}

:deep(.p-password) {
  width: 100%;
}

:deep(.password-with-eye) {
  width: 100%;
}

:deep(.password-with-eye .p-password),
:deep(.password-with-eye.p-icon-field) {
  position: relative;
  width: 100%;
}

:deep(.password-with-eye .p-password-input),
:deep(.password-with-eye.p-icon-field-right > .p-inputtext) {
  width: 100%;
  height: 3rem;
  padding: 0.65rem 3rem 0.65rem 0.95rem;
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  color: var(--text-color-primary);
  box-shadow: none;
  transition: border-color var(--motion-fast) var(--motion-ease), box-shadow var(--motion-fast) var(--motion-ease);
}

:deep(.password-with-eye .p-password-input:hover),
:deep(.password-with-eye.p-icon-field-right > .p-inputtext:hover) {
  border-color: #9bacb8;
}

:deep(.password-with-eye .p-password-input:focus),
:deep(.password-with-eye.p-icon-field-right > .p-inputtext:focus) {
  border-color: var(--primary-color);
  box-shadow: var(--focus-ring);
}

:deep(.password-with-eye .p-input-icon),
:deep(.password-with-eye .p-password-show-icon),
:deep(.password-with-eye .p-password-hide-icon) {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  right: 0.9rem;
  color: var(--text-color-secondary);
  line-height: 1;
  cursor: pointer;
}

.profile-header {
  display: inline-flex;
  align-items: center;
  color: var(--primary-color-dark);
  font-size: 1.35rem;
  font-weight: 750;
  letter-spacing: -0.02em;
}

:global(.profile-dialog) {
  overflow: hidden;
  border: 0;
  border-radius: var(--radius-lg);
  box-shadow: 0 24px 70px rgba(18, 53, 83, 0.18), inset 0 0 0 1px rgba(18, 53, 83, 0.06);
}

:global(.profile-dialog .p-dialog-header) {
  padding: 1.35rem 1.6rem;
  border-bottom: 1px solid var(--border-color);
}

:global(.profile-dialog .p-dialog-header-icon) {
  width: 2.5rem;
  height: 2.5rem;
  border: 1px solid var(--border-color);
  color: var(--text-color-secondary);
  transition: border-color var(--motion-fast) var(--motion-ease), background-color var(--motion-fast) var(--motion-ease), color var(--motion-fast) var(--motion-ease);
}

:global(.profile-dialog .p-dialog-header-icon:hover) {
  border-color: var(--border-strong);
  background: var(--surface-soft);
  color: var(--primary-color-dark);
}

:global(.profile-dialog .p-dialog-header-icon:focus-visible) {
  box-shadow: var(--focus-ring);
}

:global(.profile-dialog .p-dialog-content) {
  padding: 1.6rem;
  color: var(--text-color-primary);
}

:global(.profile-dialog .p-dialog-footer) {
  display: flex;
  justify-content: flex-end;
  gap: 0.7rem;
  padding: 1rem 1.6rem 1.2rem;
  border-top: 1px solid var(--border-color);
}

.profile-cancel,
.profile-save {
  min-width: 6.5rem;
  min-height: 2.75rem;
  border-radius: 8px;
  font-weight: 700;
  transition: transform var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), background-color var(--motion-fast) var(--motion-ease);
}

.profile-cancel {
  border-color: var(--border-strong);
  background: #fff;
  color: var(--primary-color);
}

.profile-cancel:hover {
  border-color: var(--primary-color);
  background: var(--primary-color-light);
  color: var(--primary-color-dark);
}

.profile-save {
  border-color: var(--primary-color);
  background: var(--primary-color);
}

.profile-save:hover:not(:disabled) {
  border-color: var(--primary-color-dark);
  background: var(--primary-color-dark);
}

.profile-cancel:active,
.profile-save:active:not(:disabled) {
  transform: translateY(1px);
}

@media (max-width: 720px) {
  :global(.profile-dialog .p-dialog-header),
  :global(.profile-dialog .p-dialog-content),
  :global(.profile-dialog .p-dialog-footer) {
    padding-right: 1.25rem;
    padding-left: 1.25rem;
  }

  :global(.profile-dialog .p-dialog-content) {
    flex: 1;
  }

  .profile-cancel,
  .profile-save {
    flex: 1;
    min-width: 0;
  }
}
</style>
