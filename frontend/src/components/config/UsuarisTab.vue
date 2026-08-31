<template>
  <div class="tab-content">
    <div class="users-layout" :class="{ 'mobile-editing': mobileEditing }">
      <aside ref="masterListRef" class="user-master" :aria-label="$t('config.users.userList')">
        <div class="master-heading">
          <div>
            <h2>{{ $t('config.users.title') }}</h2>
            <small>{{ $t('config.users.count', { count: usersFiltered.length }) }}</small>
          </div>
          <Button
            icon="pi pi-plus"
            class="p-button-sm"
            :label="$t('config.users.add')"
            @click="obrirNouUsuari"
          />
        </div>

        <div class="list-tools">
          <label class="sr-only" for="user-search">{{ $t('config.users.search') }}</label>
          <span class="search-field">
            <i class="pi pi-search" aria-hidden="true"></i>
            <InputText
              id="user-search"
              v-model="userSearch"
              :placeholder="$t('config.users.searchPlaceholder')"
            />
          </span>
          <Dropdown
            v-if="props.currentRole === 'super_admin'"
            v-model="userInstitutionFilter"
            :options="userInstitutionOptions"
            optionLabel="label"
            optionValue="value"
            :placeholder="$t('config.users.filterInstitution')"
            class="w-full"
          />
          <Button
            :icon="userSortAsc ? 'pi pi-sort-alpha-down' : 'pi pi-sort-alpha-up'"
            class="p-button-sm p-button-text sort-button"
            :label="$t('config.users.sort')"
            @click="toggleUserSort"
          />
        </div>

        <div v-if="usersLoading" class="list-message">{{ $t('common.loading') }}</div>
        <div v-else-if="!usersFiltered.length" class="list-message">{{ $t('config.users.empty') }}</div>
        <TransitionGroup v-else name="motion-list" tag="div" class="user-list" role="list">
          <button
            v-for="user in usersFiltered"
            :key="user.id"
            type="button"
            class="user-list-item"
            :class="{ selected: selectedUserId === user.id }"
            :data-user-id="user.id"
            :aria-current="selectedUserId === user.id ? 'true' : undefined"
            @click="selectUser(user)"
          >
            <span class="user-avatar" aria-hidden="true">{{ (user.username || '?').charAt(0).toUpperCase() }}</span>
            <span class="user-summary">
              <strong>{{ user.username }}</strong>
              <small>
                {{ roleLabel(user.role) }}
                <template v-if="props.currentRole === 'super_admin'">
                  · {{ user.institucio_display_name || user.institucio }}
                </template>
              </small>
            </span>
            <i v-if="!user.active" class="pi pi-ban inactive-icon" :title="$t('config.users.inactive')"></i>
            <i class="pi pi-chevron-right chevron" aria-hidden="true"></i>
          </button>
        </TransitionGroup>
      </aside>

      <main class="user-detail">
        <Transition name="motion-fade" mode="out-in">
        <UserPermissionsPanel
          v-if="selectedUser"
          :key="selectedUser.id"
          ref="permissionsPanelRef"
          :user="selectedUser"
          :institutions="institucionsOptions"
          :current-role="props.currentRole"
          :saving="userSaving"
          @save="desarUsuariSeleccionat"
          @back="tornarAUsuaris"
          @deactivate="desactivarUsuari"
          @delete="eliminarUsuari"
        />
        <div v-else key="empty" class="empty-detail">
          <i class="pi pi-users" aria-hidden="true"></i>
          <p>{{ $t('config.users.selectUser') }}</p>
        </div>
        </Transition>
      </main>
    </div>

    <Dialog
      v-model:visible="mostrarDialogUsuari"
      :modal="true"
      :style="{ width: 'min(96vw, 760px)' }"
      :header="$t('config.users.addTitle')"
      class="user-dialog"
      @hide="newUser = null"
    >
      <UserPermissionsPanel
        v-if="newUser"
        :user="newUser"
        :institutions="institucionsOptions"
        :current-role="props.currentRole"
        :saving="userSaving"
        is-new
        @save="crearUsuari"
        @cancel="mostrarDialogUsuari = false"
      />
    </Dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Dropdown from 'primevue/dropdown'
import InputText from 'primevue/inputtext'
import UserPermissionsPanel from './UserPermissionsPanel.vue'

const props = defineProps({
  visible: { type: Boolean, default: true },
  currentRole: { type: String, default: null },
  currentInstitucio: { type: String, default: null }
})

const { t, locale } = useI18n()
const confirm = useConfirm()
const toast = useToast()
const institucions = ref([])
const users = ref([])
const userSearch = ref('')
const userInstitutionFilter = ref('')
const userSortAsc = ref(true)
const usersLoading = ref(false)
const userSaving = ref(false)
const selectedUserId = ref(null)
const mobileEditing = ref(false)
const mostrarDialogUsuari = ref(false)
const newUser = ref(null)
const masterListRef = ref(null)
const permissionsPanelRef = ref(null)

const institucionsOptions = computed(() => (
  institucions.value
    .filter((institution) => institution.active !== false)
    .map((institution) => ({
      label: institution.display_name || institution.slug,
      value: institution.slug
    }))
))

const userInstitutionOptions = computed(() => ([
  { label: t('common.all'), value: '' },
  ...institucionsOptions.value
]))

const usersFiltered = computed(() => {
  const query = userSearch.value.trim().toLocaleLowerCase(locale.value || 'en')
  return users.value
    .filter((user) => !userInstitutionFilter.value || user.institucio === userInstitutionFilter.value)
    .filter((user) => {
      if (!query) return true
      return [user.username, user.role, user.institucio_display_name, user.institucio]
        .some((value) => String(value || '').toLocaleLowerCase(locale.value || 'en').includes(query))
    })
    .sort((a, b) => {
      const comparison = (a.username || '').localeCompare(
        b.username || '',
        locale.value || 'en',
        { sensitivity: 'base' }
      )
      return userSortAsc.value ? comparison : -comparison
    })
})

const selectedUser = computed(() => users.value.find((user) => user.id === selectedUserId.value) || null)
const roleLabel = (role) => t(`config.users.roles.${role}`)

const carregarInstitucions = async () => {
  const response = await axios.get('/api/settings/institucions')
  institucions.value = response.data.institucions || []
}

const carregarUsuaris = async (preferredUserId = selectedUserId.value) => {
  usersLoading.value = true
  try {
    const response = await axios.get('/api/users')
    users.value = response.data || []
    selectedUserId.value = users.value.some((user) => user.id === preferredUserId)
      ? preferredUserId
      : users.value[0]?.id ?? null
    if (!selectedUserId.value) mobileEditing.value = false
  } catch (error) {
    console.error('Error carregant usuaris:', error)
    toast.add({
      severity: 'error',
      summary: t('common.error'),
      detail: t('config.users.loadError'),
      life: 3000
    })
  } finally {
    usersLoading.value = false
  }
}

const toggleUserSort = () => {
  userSortAsc.value = !userSortAsc.value
}

const selectUser = async (user) => {
  selectedUserId.value = user.id
  mobileEditing.value = true
  await nextTick()
  permissionsPanelRef.value?.focus()
}

const tornarAUsuaris = async () => {
  mobileEditing.value = false
  await nextTick()
  masterListRef.value?.querySelector(`[data-user-id="${selectedUserId.value}"]`)?.focus()
}

const obrirNouUsuari = () => {
  newUser.value = {
    username: '',
    role: 'user',
    institucio: props.currentInstitucio || institucionsOptions.value[0]?.value || '',
    active: true
  }
  mostrarDialogUsuari.value = true
}

const payloadFor = (form, creating) => {
  const payload = {
    username: form.username,
    role: form.role,
    permissions: form.permissions
  }
  if (!creating) payload.active = form.active
  if (props.currentRole === 'super_admin') payload.institucio = form.institucio
  if (form.password) payload.password = form.password
  return payload
}

const desarUsuariSeleccionat = async (form) => {
  if (!selectedUser.value) return
  userSaving.value = true
  try {
    const response = await axios.put(`/api/users/${selectedUser.value.id}`, payloadFor(form, false))
    toast.add({ severity: 'success', summary: t('common.saved'), detail: t('config.users.saved'), life: 2500 })
    await carregarUsuaris(response.data.id)
  } catch (error) {
    console.error('Error desant usuari:', error)
    toast.add({
      severity: 'error',
      summary: t('common.error'),
      detail: error.response?.data?.detail || t('config.users.saveError'),
      life: 3000
    })
  } finally {
    userSaving.value = false
  }
}

const crearUsuari = async (form) => {
  userSaving.value = true
  try {
    const response = await axios.post('/api/users', payloadFor(form, true))
    toast.add({ severity: 'success', summary: t('common.saved'), detail: t('config.users.saved'), life: 2500 })
    mostrarDialogUsuari.value = false
    await carregarUsuaris(response.data.id)
    mobileEditing.value = true
    await nextTick()
    permissionsPanelRef.value?.focus()
  } catch (error) {
    console.error('Error creant usuari:', error)
    toast.add({
      severity: 'error',
      summary: t('common.error'),
      detail: error.response?.data?.detail || t('config.users.saveError'),
      life: 3000
    })
  } finally {
    userSaving.value = false
  }
}

const desactivarUsuari = (user) => {
  confirm.require({
    message: t('config.users.deactivateConfirm', { username: user.username }),
    header: t('config.users.deactivateTitle'),
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: t('config.users.deactivateAction'),
    rejectLabel: t('common.cancel'),
    acceptClass: 'p-button-danger',
    accept: async () => {
      try {
        await axios.delete(`/api/users/${user.id}`)
        toast.add({ severity: 'success', summary: t('common.saved'), detail: t('config.users.deactivated'), life: 2500 })
        await carregarUsuaris(user.id)
      } catch (error) {
        console.error('Error desactivant usuari:', error)
        toast.add({
          severity: 'error',
          summary: t('common.error'),
          detail: error.response?.data?.detail || t('config.users.deleteError'),
          life: 3000
        })
      }
    }
  })
}

const eliminarUsuari = (user) => {
  confirm.require({
    message: t('config.users.deleteConfirm', { username: user.username }),
    header: t('config.users.deleteTitle'),
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: t('common.delete'),
    rejectLabel: t('common.cancel'),
    acceptClass: 'p-button-danger',
    accept: async () => {
      try {
        await axios.delete(`/api/users/${user.id}/hard`)
        toast.add({ severity: 'success', summary: t('common.deleted'), detail: t('config.users.deleted'), life: 2500 })
        await carregarUsuaris(null)
      } catch (error) {
        console.error('Error eliminant usuari:', error)
        toast.add({
          severity: 'error',
          summary: t('common.error'),
          detail: error.response?.data?.detail || t('config.users.deleteError'),
          life: 3000
        })
      }
    }
  })
}

watch(() => props.visible, (visible) => {
  if (!visible) mobileEditing.value = false
})

onMounted(() => {
  carregarInstitucions()
  carregarUsuaris()
})
</script>

<style scoped>
.tab-content {
  padding: 0.5rem 0;
}

.users-layout {
  display: grid;
  grid-template-columns: minmax(250px, 0.75fr) minmax(480px, 1.75fr);
  min-height: 520px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}

.user-master {
  min-width: 0;
  padding: 1rem;
  border-right: 1px solid #e2e8f0;
  background: #f8fafc;
}

.master-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.master-heading h2 {
  margin: 0;
  color: #1e293b;
  font-size: 1.05rem;
}

.master-heading small {
  color: #64748b;
}

.list-tools {
  display: grid;
  gap: 0.6rem;
  margin-bottom: 0.75rem;
}

.search-field {
  position: relative;
  display: block;
}

.search-field i {
  position: absolute;
  z-index: 1;
  top: 50%;
  left: 0.75rem;
  transform: translateY(-50%);
  color: #94a3b8;
}

.search-field :deep(.p-inputtext) {
  width: 100%;
  padding-left: 2.25rem;
}

.w-full {
  width: 100%;
}

.sort-button {
  justify-content: flex-start;
  min-height: 2.5rem;
}

.user-list {
  position: relative;
  display: grid;
  gap: 0.4rem;
  max-height: 460px;
  overflow: auto;
}

.user-list-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 3.75rem;
  gap: 0.65rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: background-color var(--motion-fast) var(--motion-ease), border-color var(--motion-fast) var(--motion-ease), transform var(--motion-fast) var(--motion-ease);
}

.user-list-item:hover {
  background: #fff;
  transform: translateX(2px);
}

.user-list-item:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 1px;
}

.user-list-item.selected {
  border-color: var(--border-strong);
  background: var(--primary-light);
}

.user-avatar {
  display: inline-flex;
  flex: 0 0 2.25rem;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  background: #d9e7ef;
  color: var(--primary-color-dark);
  font-weight: 700;
}

.user-summary {
  min-width: 0;
  flex: 1;
}

.user-summary strong,
.user-summary small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-summary strong {
  color: #1e293b;
  font-size: var(--font-data);
}

.user-summary small {
  margin-top: 0.15rem;
  color: #64748b;
  font-size: var(--font-supporting);
}

.inactive-icon {
  color: #dc2626;
}

.chevron {
  color: #94a3b8;
  font-size: var(--font-supporting);
}

.list-message,
.empty-detail {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 10rem;
  color: #64748b;
  text-align: center;
}

.empty-detail {
  flex-direction: column;
  min-height: 100%;
  gap: 0.5rem;
}

.empty-detail i {
  font-size: 2rem;
}

.user-detail {
  min-width: 0;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

:deep(.user-dialog .p-dialog-content) {
  padding-top: 0;
}

@media (max-width: 720px) {
  .users-layout {
    display: block;
    min-height: 0;
    overflow: visible;
    border: 0;
    border-radius: 0;
  }

  .user-master {
    padding: 0;
    border: 0;
    background: #fff;
  }

  .user-detail {
    display: none;
  }

  .users-layout.mobile-editing .user-master {
    display: none;
  }

  .users-layout.mobile-editing .user-detail {
    display: block;
  }

  .user-list {
    max-height: none;
  }

  .user-list-item {
    min-height: 4.25rem;
  }
}
</style>
