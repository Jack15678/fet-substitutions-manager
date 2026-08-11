<template>
  <div id="app">
    <Toast />

    <div v-if="!autenticat" class="login-screen">
      <div class="login-card">
        <div class="language-control login-language">
          <label for="login-language">{{ $t('app.nav.language') }}</label>
          <select id="login-language" v-model="currentLocale">
            <option value="zh-HK">繁體中文（香港）</option>
            <option value="en">English</option>
          </select>
        </div>
        <h1 class="login-title">{{ $t('app.login.title') }}</h1>
        <p class="login-subtitle">{{ $t('app.login.subtitle') }}</p>

        <form class="login-form" @submit.prevent="ferLogin">
          <div class="login-field">
            <label for="login-user">{{ $t('app.login.username') }}</label>
            <InputText
              id="login-user"
              v-model="loginUser"
              autocomplete="username"
              class="w-full"
            />
          </div>
          <div class="login-field">
            <label for="login-pass">{{ $t('app.login.password') }}</label>
            <Password
              id="login-pass"
              v-model="loginPass"
              :feedback="false"
              class="w-full password-with-eye"
              toggleMask
              autocomplete="current-password"
            />
          </div>

          <p v-if="loginError" class="login-error">{{ loginError }}</p>

          <Button
            type="submit"
            :label="$t('app.login.submit')"
            icon="pi pi-sign-in"
            :loading="loginLoading"
            :disabled="loginRetrySeconds !== null"
            class="login-submit"
          />
        </form>
      </div>
    </div>

    <div v-else>
      <!-- Navbar superior -->
      <header v-if="!isMobile" class="navbar">
        <div class="navbar-left">
          <div class="date-selector">
            <Button
              icon="pi pi-chevron-left"
              class="p-button-rounded p-button-text p-button-plain nav-date-btn"
              v-tooltip.bottom="$t('app.nav.prevDay')"
              @click="diaAnterior"
            />
            <Calendar
              v-model="dataSeleccionada"
              dateFormat="dd/mm/yy"
              :showIcon="true"
              :showButtonBar="true"
              :placeholder="$t('app.nav.selectDate')"
              :inputProps="{ autocomplete: 'nope', 'data-form-type': 'other', 'data-lpignore': 'true' }"
            />
            <Button
              icon="pi pi-chevron-right"
              class="p-button-rounded p-button-text p-button-plain nav-date-btn"
              v-tooltip.bottom="$t('app.nav.nextDay')"
              @click="diaSeguent"
            />
          </div>
        </div>

        <div class="navbar-center">
          <h1 class="logo">{{ $t('app.title') }}</h1>
          <div class="config-info" v-if="cursos.length">
            <span
              v-if="cursos.length"
              class="curs-indicador"
              :class="{ 'curs-indicador--cap': !cursDeLaData }"
              v-tooltip.bottom="$t('app.nav.course')"
            >
              📅 {{ cursDeLaData ? cursDeLaData.nom : $t('app.nav.courseNone') }}
            </span>
          </div>
        </div>

        <div class="navbar-right">
          <div class="language-control navbar-language">
            <label for="navbar-language" class="sr-only">{{ $t('app.nav.language') }}</label>
            <select id="navbar-language" v-model="currentLocale">
              <option value="zh-HK">繁中</option>
              <option value="en">EN</option>
            </select>
          </div>
          <Button
            v-if="isAdmin"
            icon="pi pi-cog"
            class="p-button-rounded p-button-text p-button-plain"
            v-tooltip.bottom="$t('app.nav.settings')"
            @click="obrirConfiguracio"
          />
          <Button
            icon="pi pi-user"
            class="p-button-rounded p-button-text p-button-plain"
            v-tooltip.bottom="$t('app.nav.profile')"
            @click="obrirPerfil"
          />
          <Button
            icon="pi pi-sign-out"
            class="p-button-rounded p-button-text p-button-plain"
            v-tooltip.bottom="$t('app.nav.logout')"
            @click="ferLogout"
          />
        </div>
      </header>

      <header v-else class="mobile-header">
        <div class="mobile-header-top">
          <h1 class="logo">{{ $t('app.title') }}</h1>
          <div class="mobile-header-actions">
            <select v-model="currentLocale" :aria-label="$t('app.nav.language')">
              <option value="zh-HK">繁中</option>
              <option value="en">EN</option>
            </select>
            <Button icon="pi pi-bars" class="p-button-rounded p-button-text p-button-plain" v-tooltip.bottom="$t('app.nav.menu')" @click="mostrarMenuMobil = true" />
          </div>
        </div>
        <div class="mobile-date-row">
          <Button
            icon="pi pi-chevron-left"
            class="p-button-rounded p-button-text p-button-plain nav-date-btn"
            v-tooltip.bottom="$t('app.nav.prevDay')"
            @click="diaAnterior"
          />
          <Calendar
            v-model="dataSeleccionada"
            dateFormat="dd/mm/yy"
            :showIcon="true"
            :showButtonBar="true"
            :placeholder="$t('app.nav.selectDate')"
            :inputProps="{ autocomplete: 'nope', 'data-form-type': 'other', 'data-lpignore': 'true' }"
          />
          <Button
            icon="pi pi-chevron-right"
            class="p-button-rounded p-button-text p-button-plain nav-date-btn"
            v-tooltip.bottom="$t('app.nav.nextDay')"
            @click="diaSeguent"
          />
        </div>
      </header>

      <div class="tabs-container">
        <div class="tabs">
          <button class="tab" :class="{ active: paginaActiva === 'workbench' }" @click="paginaActiva = 'workbench'">{{ $t('app.pages.workbench') }}</button>
          <button class="tab" :class="{ active: paginaActiva === 'records' }" @click="paginaActiva = 'records'">{{ $t('app.pages.records') }}</button>
          <button v-if="isAdmin" class="tab" :class="{ active: paginaActiva === 'import' }" @click="paginaActiva = 'import'">{{ $t('app.pages.import') }}</button>
        </div>
      </div>

      <!-- La demo és pública i compartida: qui hi entra ha de saber que el que
           escrigui el veuran altres visitants i que s'esborra cada nit. -->
      <div v-if="esDemo" class="demo-avis">
        <i class="pi pi-info-circle" aria-hidden="true"></i>
        <span>
          <strong>{{ $t('config.system.demoBannerTitle') }}.</strong>
          {{ $t('config.system.demoBannerText') }}
        </span>
      </div>

      <!-- Contingut -->
      <main class="main-content">
        <ReschedulingView
          v-if="paginaActiva === 'workbench'"
          :dataGlobal="dataSeleccionada"
          :isAdmin="isAdmin"
        />
        <RecordsView v-else-if="paginaActiva === 'records'" :isAdmin="isAdmin" />
        <TimetableImportView v-else-if="paginaActiva === 'import' && isAdmin" />
      </main>

      <footer class="footer">
        <p>{{ $t('app.footer') }}</p>
      </footer>

      <!-- Diàlegs -->
      <ConfiguracioDialog
        v-model:visible="mostrarConfiguracio"
        :currentRole="userProfile?.role"
        :currentInstitucio="userProfile?.institucio"
        :dataGlobal="dataSeleccionada"
        @cursos-canviats="carregarCursos"
      />
      <ProfileDialog
        v-model:visible="mostrarPerfil"
        :username="userProfile?.username"
      />

      <Dialog
        v-model:visible="mostrarMenuMobil"
        :header="$t('app.nav.menu')"
        :modal="true"
        :style="{ width: '320px' }"
      >
        <div class="mobile-menu">
          <Button
            v-if="isAdmin"
            icon="pi pi-cog"
            class="p-button-text"
            :label="$t('app.nav.settings')"
            @click="obrirConfiguracio(); mostrarMenuMobil = false"
          />
          <Button
            icon="pi pi-user"
            class="p-button-text"
            :label="$t('app.nav.profile')"
            @click="obrirPerfil(); mostrarMenuMobil = false"
          />
          <Button
            icon="pi pi-sign-out"
            class="p-button-text"
            :label="$t('app.nav.logout')"
            @click="ferLogout(); mostrarMenuMobil = false"
          />
        </div>
      </Dialog>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import Calendar from 'primevue/calendar'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Dialog from 'primevue/dialog'
import ReschedulingView from './views/ReschedulingView.vue'
import RecordsView from './views/RecordsView.vue'
import TimetableImportView from './views/TimetableImportView.vue'
import ConfiguracioDialog from './components/ConfiguracioDialog.vue'
import ProfileDialog from './components/ProfileDialog.vue'
import { setLocale } from './i18n'

const { t, locale } = useI18n()
const toast = useToast()
const currentLocale = computed({
  get: () => locale.value,
  set: (value) => setLocale(value)
})

const autenticat = ref(false)
const paginaActiva = ref('workbench')
const hongKongToday = () => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en', {
    timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts().filter(part => part.type !== 'literal').map(part => [part.type, part.value]))
  return new Date(Number(parts.year), Number(parts.month) - 1, Number(parts.day), 12)
}
const dataSeleccionada = ref(hongKongToday())
const mostrarConfiguracio = ref(false)
const mostrarPerfil = ref(false)
const mostrarMenuMobil = ref(false)
const loginUser = ref('')
const loginPass = ref('')
const loginError = ref('')
const loginLoading = ref(false)
const loginRetrySeconds = ref(null)
let loginRetryTimer = null
const isMobile = ref(false)
let mediaQuery = null
const userProfile = ref(null)
const isAdmin = computed(() => ['admin', 'super_admin'].includes(userProfile.value?.role || ''))
const esDemo = computed(() => userProfile.value?.institucio === 'demo')

const actualitzarModeMobil = () => {
  if (!mediaQuery) return
  isMobile.value = mediaQuery.matches
}

const aplicarToken = () => {
  autenticat.value = true
}

const netejarToken = () => {
  autenticat.value = false
  userProfile.value = null
  axios.post('/api/logout').catch(() => {})
}

// ===== CURSOS (per institució) =====
// Els cursos són una seqüència contígua de rangs amb nom. NO es trien: el curs es
// deriva de la data on treballes, igual que la versió d'XML. Aquí només es mostra.
const cursos = ref([])

const _isoDate = (d) => {
  if (!d) return null
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${dd}`
}

const cursDeLaData = computed(() => {
  const iso = _isoDate(dataSeleccionada.value)
  if (!iso) return null
  // Comparació lexicogràfica: les dates ISO ho permeten
  return cursos.value.find(
    c => c.data_inici <= iso && (!c.data_fi || iso <= c.data_fi)
  ) || null
})

const carregarCursos = async () => {
  try {
    const { data } = await axios.get('/api/cursos')
    cursos.value = data
  } catch (error) {
    cursos.value = []
  }
}

const carregarPerfil = async () => {
  try {
    const response = await axios.get('/api/users/profile')
    userProfile.value = response.data
  } catch (error) {
    console.error('Error carregant perfil:', error)
  }
}

onMounted(async () => {
  axios.defaults.withCredentials = true
  mediaQuery = window.matchMedia('(max-width: 720px)')
  actualitzarModeMobil()
  mediaQuery.addEventListener('change', actualitzarModeMobil)

  axios.interceptors.response.use(
    (response) => response,
    (error) => {
      const status = error?.response?.status
      if (status === 401) {
        netejarToken()
        return Promise.reject(error)
      }
      if (!error.config?._silent) {
        const detail = error.response?.data?.detail
        const msg = typeof detail === 'string' ? detail
          : !error.response ? t('app.errors.connection')
          : status >= 500 ? t('app.errors.server')
          : t('app.errors.unexpected')
        toast.add({ severity: 'error', summary: t('app.errors.title'), detail: msg, life: 5000 })
      }
      return Promise.reject(error)
    }
  )

  try {
    await carregarPerfil()
    await carregarCursos()
    aplicarToken()
  } catch (error) {
    // Cookie absent o expirada — es queda a la pantalla de login
  }
})

onBeforeUnmount(() => {
  if (mediaQuery) {
    mediaQuery.removeEventListener('change', actualitzarModeMobil)
  }
  if (loginRetryTimer) {
    clearInterval(loginRetryTimer)
  }
})

const ferLogin = async () => {
  loginError.value = ''
  loginLoading.value = true
  try {
    const response = await axios.post('/api/login', {
      username: loginUser.value,
      password: loginPass.value
    })
    aplicarToken()
    const redirectUrl = new URLSearchParams(window.location.search).get('redirect')
    if (redirectUrl) { window.location.href = redirectUrl; return; }
    await carregarPerfil()
    await carregarCursos()
  } catch (error) {
    const status = error.response?.status
    if (status === 429) {
      const retryAfter = parseInt(error.response?.headers?.['retry-after'], 10)
      loginRetrySeconds.value = Number.isFinite(retryAfter) ? retryAfter : 60
      loginError.value = t('app.login.rateLimitWithWait', { seconds: loginRetrySeconds.value })

      if (loginRetryTimer) {
        clearInterval(loginRetryTimer)
      }

      loginRetryTimer = setInterval(() => {
        if (loginRetrySeconds.value === null) return
        loginRetrySeconds.value -= 1
        if (loginRetrySeconds.value <= 0) {
          clearInterval(loginRetryTimer)
          loginRetryTimer = null
          loginRetrySeconds.value = null
          loginError.value = ''
          return
        }
        loginError.value = t('app.login.rateLimitWithWait', { seconds: loginRetrySeconds.value })
      }, 1000)
    } else {
      loginError.value = t('app.login.error')
    }
  } finally {
    loginLoading.value = false
  }
}

const ferLogout = () => {
  netejarToken()
  loginPass.value = ''
}

const obrirConfiguracio = () => {
  mostrarConfiguracio.value = true
}

const obrirPerfil = () => {
  mostrarPerfil.value = true
}

const diaAnterior = () => {
  const novaData = new Date(dataSeleccionada.value)
  novaData.setDate(novaData.getDate() - 1)
  dataSeleccionada.value = novaData
}

const diaSeguent = () => {
  const novaData = new Date(dataSeleccionada.value)
  novaData.setDate(novaData.getDate() + 1)
  dataSeleccionada.value = novaData
}
</script>

<style>
:root {
  --primary-color: #667eea;
  --primary-color-dark: #5a6ed1; /* Slightly darker for gradient end or hover */
  --primary-color-light: #8e9ffc; /* Lighter for accents */
  --text-color-primary: #1f2937;
  --text-color-secondary: #6b7280;
  --background-light: #f5f5f5;
  --card-background: white;
  --border-color: #e5e7eb;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  background: var(--background-light);
  color: var(--text-color-primary);
}

.p-datatable .p-paginator .p-dropdown {
  width: auto !important;
  height: 2.2rem !important;
  min-height: 2.2rem !important;
  max-height: 2.2rem !important;
}

.p-datatable .p-paginator .p-dropdown .p-dropdown-label {
  padding: 0.4rem 0.5rem !important;
  line-height: 1.4rem;
  font-size: 0.9rem !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
  text-align: center;
  width: 100%;
}

.p-datatable .p-paginator .p-dropdown .p-dropdown-trigger {
  width: 1.4rem !important;
  min-width: 1.4rem !important;
  padding: 0 !important;
}



.p-calendar {
  display: inline-flex;
  align-items: stretch;
}

.p-datepicker-trigger.p-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  width: 2.25rem;
  height: 2.25rem;
  align-self: stretch;
}

.p-inputtext.p-inputtext-sm ~ .p-datepicker-trigger.p-button {
  width: 2rem;
  height: 2rem;
}

.p-datepicker-trigger .p-icon {
  width: 1.1rem;
  height: 1.1rem;
  color: currentColor;
}

.p-dialog.dialog-stable-height {
  height: 86vh;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.p-dialog.dialog-stable-height .p-dialog-content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

@media (max-width: 720px) {
  .p-dialog {
    width: 100vw !important;
    max-width: 100vw !important;
    height: 100dvh !important;
    max-height: 100dvh !important;
    margin: 0 !important;
    border-radius: 0 !important;
  }

  .p-dialog-header {
    position: sticky;
    top: 0;
    z-index: 2;
    background: #fff;
  }

  .p-dialog-content {
    overflow: auto;
    max-height: calc(100dvh - 7rem);
  }

  .p-dialog-footer {
    position: sticky;
    bottom: 0;
    z-index: 2;
    background: #fff;
  }
}


#app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

input.p-inputtext {
  height: 2.25rem;
  line-height: 2.25rem;
}

input.p-inputtext.p-inputtext-sm {
  height: 2rem;
  line-height: 2rem;
}

.p-dropdown {
  display: inline-flex;
  align-items: center;
  height: 2.25rem;
}

.p-dropdown .p-dropdown-label {
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 2.25rem 0 0.75rem;
  line-height: 1.2;
}

.login-screen {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top, #f3f4ff 0%, #eef1f7 45%, #e6eaf1 100%);
  padding: 2rem;
}

.login-card {
  width: min(420px, 92vw);
  background: var(--card-background);
  border-radius: 16px;
  padding: 2.5rem;
  box-shadow: 0 20px 40px rgba(31, 41, 55, 0.12);
  border: 1px solid rgba(102, 126, 234, 0.15);
}

.language-control{display:flex;align-items:center;gap:.45rem}.language-control label{font-size:.78rem}.language-control select,.mobile-header-actions select{border:1px solid #d7dce7;border-radius:7px;background:#fff;color:#243047;padding:.35rem .5rem}.login-language{justify-content:flex-end;margin-bottom:1rem;color:var(--text-color-secondary)}.navbar-language select{border-color:rgba(255,255,255,.45)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.mobile-header-actions{display:flex;align-items:center;gap:.35rem}

.login-title {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--text-color-primary);
}

.login-subtitle {
  margin: 0.5rem 0 1.8rem;
  color: var(--text-color-secondary);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.9rem;
  color: var(--text-color-secondary);
}

.login-field label {
  font-weight: 600;
  color: var(--text-color-primary);
}

.login-field .p-inputtext {
  height: 2.25rem;
  line-height: 2.25rem;
}

.login-error {
  color: #b91c1c;
  font-size: 0.9rem;
}

.login-submit {
  justify-content: center;
  width: 100%;
}

.password-with-eye {
  width: 100%;
}

.password-with-eye.p-icon-field {
  position: relative;
  width: 100%;
}

.password-with-eye .p-password-input,
.password-with-eye.p-icon-field-right > .p-inputtext {
  width: 100%;
  height: 2.25rem;
  line-height: 2.25rem;
  padding-right: 2.75rem;
}

.password-with-eye .p-input-icon,
.password-with-eye .p-password-show-icon,
.password-with-eye .p-password-hide-icon {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  right: 0.75rem;
  line-height: 1;
  cursor: pointer;
}

/* Navbar Superior */
.navbar {
  background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-color-dark) 100%);
  color: white;
  padding: 1rem 2rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
}

.navbar-left {
  display: flex;
  align-items: center;
  flex: 1;
}

.navbar-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  flex: 0 0 auto;
}

.logo {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
  text-align: center;
}

.config-info {
  display: flex;
  gap: 1rem;
  align-items: center;
  font-size: 0.85rem;
  opacity: 0.9;
}

/* Indicador de curs a la barra: només lectura, derivat de la data seleccionada */
.curs-indicador {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
}

/* Data anterior al primer curs definit */
.curs-indicador--cap {
  opacity: 0.6;
  font-style: italic;
}

.date-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: rgba(255, 255, 255, 0.15);
  padding: 0.4rem 0.8rem;
  border-radius: 8px;
}


.nav-date-btn {
  color: white !important;
  font-size: 0.9rem !important;
}

.nav-date-btn:hover {
  background: rgba(255, 255, 255, 0.25) !important;
}

.navbar-right {
  display: flex;
  gap: 0.5rem;
  flex: 1;
  justify-content: flex-end;
}

.navbar-right .p-button {
  color: white !important;
}

.navbar-right .p-button:hover {
  background: rgba(255, 255, 255, 0.2) !important;
}

/* Tabs */
.tabs-container {
  background: var(--card-background);
  border-bottom: 2px solid var(--border-color);
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.tabs {
  display: flex;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 2rem;
}

.tab {
  background: none;
  border: none;
  padding: 1rem 1.5rem;
  font-size: 1rem;
  font-weight: 500;
  color: var(--text-color-secondary);
  cursor: pointer;
  border-bottom: 3px solid transparent;
  transition: all 0.2s ease;
  position: relative;
}

.tab:hover {
  color: var(--primary-color);
  background: var(--background-light);
}

.tab.active {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
  background: var(--background-light);
}

/* PrimeVue TabView unificat (diàlegs + scheduler) */
.app-tabview .p-tabview-nav {
  background: #f8fafc;
  border-bottom: 2px solid #e2e8f0;
  padding: 0.2rem 0.5rem 0;
  gap: 0.2rem;
  align-items: stretch;
}

.app-tabview .p-tabview-nav li {
  display: flex;
  align-items: stretch;
}

.app-tabview .p-tabview-nav li .p-tabview-nav-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 0.85rem;
  font-weight: 600;
  color: #64748b;
  background: transparent;
  border: 1px solid transparent;
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  padding: 0.72rem 1rem;
  min-height: 3.2rem;
  line-height: 1.12;
  transition: background-color 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.app-tabview .p-tabview-nav li:not(.p-highlight) .p-tabview-nav-link:hover {
  color: #334155;
  background: #eef2ff;
  border-color: #dbeafe;
}

.app-tabview .p-tabview-nav li.p-highlight .p-tabview-nav-link {
  color: #1d4ed8;
  background: #ffffff;
  border-color: #bfdbfe;
  box-shadow: 0 -1px 0 #dbeafe inset;
}

.app-tabview .p-tabview-panels {
  background: white;
  padding: 1rem 0.75rem 0.75rem;
}

/* Main Content */
.main-content {
  flex: 1;
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

/* Informatiu, no d'error: la demo funciona correctament, però convé saber
   que és compartida i efímera abans de posar-hi res. */
.demo-avis {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  max-width: 1400px;
  margin: 1rem auto 0;
  padding: 0.6rem 0.9rem;
  width: calc(100% - 4rem);
  border: 1px solid #bae6fd;
  border-left: 4px solid #0284c7;
  border-radius: 4px;
  background: #f0f9ff;
  color: #075985;
  font-size: 0.85rem;
  line-height: 1.35;
}

.demo-avis .pi {
  color: #0284c7;
  font-size: 1.1rem;
  flex-shrink: 0;
}

/* Footer */
.footer {
  background: #2c3e50;
  color: white;
  text-align: center;
  padding: 1rem;
  font-size: 0.9rem;
}

/* Millores per PrimeVue */
.p-button {
  transition: all 0.3s ease;
  /* Fer botons una mica més generosos */
  padding: 0.75rem 1.25rem; /* Augmentar padding */
  font-size: 0.95rem;     /* Lleuger augment de font size */
  min-width: unset;       /* Reset per PrimeVue que a vegades posa min-width */
}

/* Override per botons amb outline */
.p-button.p-button-outlined {
  border-width: 2px;
}

/* Botons de text, mantenir petits */
.p-button.p-button-text {
    padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
}

.p-datatable {
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  border-radius: 8px;
  overflow: hidden;
}

/* Calendar dins navbar */
.navbar .p-calendar {
  font-size: 0.95rem;
}

.navbar .p-calendar .p-inputtext {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: 0.5rem 0.75rem;
}

.navbar .p-calendar .p-inputtext:focus {
  border-color: white;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.2);
}

/* Responsive per la navbar */
@media (max-width: 992px) {
  .navbar {
    flex-direction: column;
    gap: 1rem;
    padding: 1rem 1rem;
  }

  .navbar-left, .navbar-center, .navbar-right {
    flex-basis: auto;
    width: 100%;
    justify-content: center;
  }

  .navbar-right {
    justify-content: center;
  }

  .tabs {
    padding: 0 1rem;
    flex-wrap: wrap;
    justify-content: center;
  }
}

@media (max-width: 720px) {
  .navbar {
    padding: 0.75rem 0.9rem;
    gap: 0.75rem;
  }

  .date-selector {
    width: 100%;
    flex-wrap: wrap;
    justify-content: center;
  }

  .navbar .p-calendar {
    flex: 1 1 220px;
  }

  .navbar .p-calendar .p-inputtext {
    width: 100%;
  }

  .config-info {
    display: none;
  }

  .logo {
    font-size: 1.2rem;
  }

  .navbar-right {
    flex-wrap: wrap;
    justify-content: center;
  }

  .tabs-container {
    overflow-x: auto;
  }

  .tabs {
    padding: 0 0.5rem;
    justify-content: flex-start;
    gap: 0.25rem;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  .tab {
    white-space: nowrap;
    padding: 0.8rem 1rem;
    font-size: 0.95rem;
  }

  .main-content {
    padding: 1rem 0.75rem;
  }

  .main-content {
    padding-bottom: 5.5rem;
  }

  .footer {
    font-size: 0.8rem;
    padding: 0.75rem;
  }
}

.mobile-header {
  background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-color-dark) 100%);
  color: white;
  padding: 0.75rem 1rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.mobile-header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mobile-date-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.mobile-date-row .p-calendar {
  flex: 1 1 auto;
}

.mobile-menu {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.mobile-menu .p-button {
  justify-content: flex-start;
}

.mobile-nav {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: white;
  border-top: 1px solid var(--border-color);
  box-shadow: 0 -4px 12px rgba(15, 23, 42, 0.12);
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0.25rem;
  padding: 0.4rem 0.25rem 0.5rem;
  z-index: 20;
}

.mobile-nav-item {
  background: none;
  border: none;
  color: var(--text-color-secondary);
  font-size: 0.75rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.35rem 0.15rem;
  cursor: pointer;
}

.mobile-nav-item i {
  font-size: 1.1rem;
}

.mobile-nav-item.active {
  color: var(--primary-color);
  font-weight: 600;
}
</style>
