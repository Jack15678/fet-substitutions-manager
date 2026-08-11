<template>
  <Dialog
    :visible="visible"
    @update:visible="handleVisibleChange"
    :modal="true"
    :style="{ width: '440px' }"
    :contentStyle="{ padding: '1rem 1.25rem' }"
    :closable="true"
  >
    <template #header>
      <div class="profile-header">
        <i class="pi pi-user" />
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
          id="current-password"
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
          id="new-password"
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
          id="confirm-password"
          v-model="confirmPassword"
          :feedback="false"
          toggleMask
          autocomplete="new-password"
          :inputProps="{ 'data-form-type': 'other', 'data-lpignore': 'true' }"
          class="w-full password-with-eye"
        />
      </div>

      <p v-if="errorMessage" class="profile-error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="profile-success">{{ successMessage }}</p>
    </div>

    <template #footer>
      <Button
        :label="$t('common.cancel')"
        class="p-button-text"
        @click="handleVisibleChange(false)"
      />
      <Button
        :label="$t('common.save')"
        class="p-button-success"
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
  gap: 0.9rem;
}

.profile-form .field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.profile-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.4rem;
}

.profile-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f3f4f6;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  font-size: 0.9rem;
}

.profile-label {
  color: #6b7280;
  font-weight: 600;
}

.profile-value {
  color: #111827;
  font-weight: 600;
}

.profile-error {
  color: #b91c1c;
  font-size: 0.9rem;
}

.profile-success {
  color: #166534;
  font-size: 0.9rem;
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
  height: 2.25rem;
  line-height: 2.25rem;
  padding-right: 2.75rem;
}

:deep(.password-with-eye .p-input-icon),
:deep(.password-with-eye .p-password-show-icon),
:deep(.password-with-eye .p-password-hide-icon) {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  right: 0.75rem;
  line-height: 1;
  cursor: pointer;
}

.profile-header {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
}
</style>
