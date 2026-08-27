<template>
  <Dialog
    class="dialog-stable-height"
    :visible="visible"
    @update:visible="handleVisibleChange"
    :header="$t('config.title')"
    :modal="true"
    :style="{ width: 'min(96vw, 1120px)', maxHeight: '90vh' }"
    :closable="true"
  >
    <div class="config-container">
      <TabView class="app-tabview app-tabview--dialog">
        <!-- TAB: GOVERNANÇA DE DADES (RGPD) -->
        <TabPanel v-if="canManageUsers">
          <template #header>
            <span class="tab-header-lines">
              <span>{{ $t('config.tabs.dataLine1') }}</span>
              <span>{{ $t('config.tabs.dataLine2') }}</span>
            </span>
          </template>
          <GestioDadesTab />
        </TabPanel>

        <!-- TAB 6: USUARIS -->
        <TabPanel v-if="canManageUsers">
          <template #header>
            <span class="tab-header-lines">
              <span>{{ $t('config.tabs.usersLine1') }}</span>
              <span>&nbsp;</span>
            </span>
          </template>
          <UsuarisTab :visible="visible" :current-role="currentRole" :current-institucio="currentInstitucio" />
        </TabPanel>

      </TabView>
    </div>

    <template #footer>
      <Button
        :label="$t('common.close')"
        icon="pi pi-times"
        @click="tancar"
        class="p-button-text"
      />
    </template>
  </Dialog>
</template>

<script setup>
import { computed } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import TabView from 'primevue/tabview'
import TabPanel from 'primevue/tabpanel'
import GestioDadesTab from './config/GestioDadesTab.vue'
import UsuarisTab from './config/UsuarisTab.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    required: true
  },
  currentRole: {
    type: String,
    default: null
  },
  currentInstitucio: {
    type: String,
    default: null
  },
  dataGlobal: {
    type: Date,
    default: () => new Date()
  }
})

const emit = defineEmits(['update:visible'])

const canManageUsers = computed(() => ['admin', 'super_admin'].includes(props.currentRole || ''))

const handleVisibleChange = (newVal) => {
  emit('update:visible', newVal)
}

const tancar = () => {
  handleVisibleChange(false)
}
</script>

<style scoped>
.config-container {
  padding: 0.75rem 0.75rem 0.5rem;
}

:deep(.p-dialog-content) {
  padding: 1rem 1rem 0.75rem !important;
}

.tab-header-lines {
  display: inline-flex;
  flex-direction: column;
  justify-content: center;
  line-height: 1.08;
}

.tab-header-lines span {
  display: block;
  white-space: nowrap;
}
</style>
