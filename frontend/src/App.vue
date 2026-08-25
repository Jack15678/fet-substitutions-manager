<template>
  <div id="app">
    <Toast />
    <ConfirmDialog />
    <Dialog
      v-model:visible="feedbackDialog.visible"
      :header="feedbackDialog.title"
      :modal="true"
      :draggable="false"
      :style="{ width: 'min(92vw, 460px)' }"
    >
      <div :class="['feedback-dialog-body', feedbackDialog.severity]" role="alert">
        <i :class="['pi', feedbackDialog.severity === 'warn' ? 'pi-exclamation-triangle' : 'pi-times-circle']" aria-hidden="true"></i>
        <p>{{ feedbackDialog.detail }}</p>
      </div>
      <template #footer>
        <Button :label="$t('common.close')" @click="feedbackDialog.visible = false" />
      </template>
    </Dialog>

    <div v-if="!autenticat" class="login-screen">
      <div class="login-card">
        <div class="login-brand">
          <span class="school-mark" aria-hidden="true"><img src="/school-logo.png" alt="" /></span>
          <span>{{ $t('brand.school') }}</span>
        </div>
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

    <div v-else :class="['app-shell', { 'is-mobile': isMobile }]">
      <header v-if="!isMobile" class="navbar">
        <div class="navbar-brand">
          <h1 class="logo">{{ $t('app.title') }}</h1>
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
            :label="$t('app.nav.settings')"
            class="p-button-text p-button-plain nav-action"
            v-tooltip.bottom="$t('app.nav.settings')"
            @click="obrirConfiguracio"
          />
          <Button
            :label="$t('app.nav.profile')"
            class="p-button-text p-button-plain nav-action"
            v-tooltip.bottom="$t('app.nav.profile')"
            @click="obrirPerfil"
          />
          <Button
            :label="$t('app.nav.logout')"
            class="p-button-text p-button-plain nav-action"
            v-tooltip.bottom="$t('app.nav.logout')"
            @click="ferLogout"
          />
        </div>
      </header>

      <header v-else class="mobile-header">
        <div class="mobile-header-top">
          <div class="mobile-brand">
            <span class="school-mark" aria-hidden="true"><img src="/school-logo.png" alt="" /></span>
            <h1 class="logo">{{ $t('app.title') }}</h1>
          </div>
          <div class="mobile-header-actions">
            <select v-model="currentLocale" :aria-label="$t('app.nav.language')">
              <option value="zh-HK">繁中</option>
              <option value="en">EN</option>
            </select>
            <Button icon="pi pi-bars" class="p-button-rounded p-button-text p-button-plain" v-tooltip.bottom="$t('app.nav.menu')" @click="mostrarMenuMobil = true" />
          </div>
        </div>
      </header>

      <aside v-if="!isMobile" class="sidebar">
        <div class="sidebar-brand">
          <span class="school-mark" aria-hidden="true"><img src="/school-logo.png" alt="" /></span>
          <span>{{ $t('brand.schoolShort') }}</span>
        </div>
        <nav class="sidebar-nav" :aria-label="$t('app.nav.menu')">
          <button class="sidebar-link" :class="{ active: paginaActiva === 'workbench' }" :aria-current="paginaActiva === 'workbench' ? 'page' : undefined" @click="paginaActiva = 'workbench'">
            <span>{{ $t('app.pages.workbench') }}</span>
          </button>
          <button class="sidebar-link" :class="{ active: paginaActiva === 'records' }" :aria-current="paginaActiva === 'records' ? 'page' : undefined" @click="paginaActiva = 'records'">
            <span>{{ $t('app.pages.records') }}</span>
          </button>
          <button v-if="isAdmin" class="sidebar-link" :class="{ active: paginaActiva === 'statistics' }" :aria-current="paginaActiva === 'statistics' ? 'page' : undefined" @click="paginaActiva = 'statistics'">
            <span>{{ $t('app.pages.statistics') }}</span>
          </button>
          <button v-if="isAdmin" class="sidebar-link" :class="{ active: paginaActiva === 'settings' }" :aria-current="paginaActiva === 'settings' ? 'page' : undefined" @click="paginaActiva = 'settings'">
            <span>{{ $t('app.pages.settings') }}</span>
          </button>
          <button v-if="isAdmin" class="sidebar-link" :class="{ active: paginaActiva === 'import' }" :aria-current="paginaActiva === 'import' ? 'page' : undefined" @click="paginaActiva = 'import'">
            <span>{{ $t('app.pages.import') }}</span>
          </button>
        </nav>
      </aside>

      <section class="app-workspace">
        <div class="content-toolbar">
          <div class="date-navigator">
            <div class="date-current">
              <span class="date-main">{{ todayDateLabel }}</span>
              <span class="date-weekday">{{ todayWeekdayLabel }}</span>
            </div>
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

        <main class="main-content">
          <ReschedulingView
            v-show="paginaActiva === 'workbench'"
            ref="reschedulingView"
            :dataGlobal="dataSeleccionada"
            :isAdmin="isAdmin"
          />
          <RecordsView v-if="paginaActiva === 'records'" :isAdmin="isAdmin" @resume-absence="resumeAbsence" />
          <StatisticsView v-if="isAdmin && paginaActiva === 'statistics'" :dataGlobal="dataSeleccionada" />
          <SettingsView v-if="isAdmin && paginaActiva === 'settings'" />
          <TimetableImportView v-if="isAdmin" v-show="paginaActiva === 'import'" />
        </main>

        <footer class="footer">
          <p>{{ $t('app.footer') }}</p>
        </footer>
      </section>

      <!-- Diàlegs -->
      <ConfiguracioDialog
        v-model:visible="mostrarConfiguracio"
        :currentRole="userProfile?.role"
        :currentInstitucio="userProfile?.institucio"
        :dataGlobal="dataSeleccionada"
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
        class="mobile-menu-dialog"
      >
        <div class="mobile-menu">
          <Button class="p-button-text" :label="$t('app.pages.workbench')" @click="paginaActiva = 'workbench'; mostrarMenuMobil = false" />
          <Button class="p-button-text" :label="$t('app.pages.records')" @click="paginaActiva = 'records'; mostrarMenuMobil = false" />
          <Button v-if="isAdmin" class="p-button-text" :label="$t('app.pages.statistics')" @click="paginaActiva = 'statistics'; mostrarMenuMobil = false" />
          <Button v-if="isAdmin" class="p-button-text" :label="$t('app.pages.settings')" @click="paginaActiva = 'settings'; mostrarMenuMobil = false" />
          <Button v-if="isAdmin" class="p-button-text" :label="$t('app.pages.import')" @click="paginaActiva = 'import'; mostrarMenuMobil = false" />
          <hr />
          <Button
            v-if="isAdmin"
            class="p-button-text"
            :label="$t('app.nav.settings')"
            @click="obrirConfiguracio(); mostrarMenuMobil = false"
          />
          <Button
            class="p-button-text"
            :label="$t('app.nav.profile')"
            @click="obrirPerfil(); mostrarMenuMobil = false"
          />
          <Button
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
import ConfirmDialog from 'primevue/confirmdialog'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Dialog from 'primevue/dialog'
import ReschedulingView from './views/ReschedulingView.vue'
import RecordsView from './views/RecordsView.vue'
import StatisticsView from './views/StatisticsView.vue'
import SettingsView from './views/SettingsView.vue'
import TimetableImportView from './views/TimetableImportView.vue'
import ConfiguracioDialog from './components/ConfiguracioDialog.vue'
import ProfileDialog from './components/ProfileDialog.vue'
import { setLocale } from './i18n'

const { t, locale } = useI18n()
const toast = useToast()
const nativeToastAdd = toast.add.bind(toast)
const feedbackDialog = ref({ visible: false, severity: 'error', title: '', detail: '' })
const feedbackToastAdd = (message) => {
  if (!['error', 'warn'].includes(message?.severity)) return nativeToastAdd(message)
  const severity = message.severity
  const title = severity === 'warn' ? t('common.warning') : t('app.errors.title')
  feedbackDialog.value = {
    visible: true,
    severity,
    title,
    detail: message.detail || (message.summary !== title ? message.summary : '') || t('app.errors.unexpected')
  }
}
// ponytail: one blocking dialog keeps the latest failure; add a queue only if concurrent failures must be reviewed.
toast.add = feedbackToastAdd
const currentLocale = computed({
  get: () => locale.value,
  set: (value) => setLocale(value)
})

const autenticat = ref(false)
const paginaActiva = ref('workbench')
const reschedulingView = ref(null)
const hongKongToday = () => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en', {
    timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts().filter(part => part.type !== 'literal').map(part => [part.type, part.value]))
  return new Date(Number(parts.year), Number(parts.month) - 1, Number(parts.day), 12)
}
const dataSeleccionada = hongKongToday()
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

const todayDateLabel = computed(() => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  year: 'numeric', month: 'long', day: 'numeric',
}).format(dataSeleccionada))
const todayWeekdayLabel = computed(() => new Intl.DateTimeFormat(locale.value === 'en' ? 'en-HK' : 'zh-HK', {
  weekday: 'long',
}).format(dataSeleccionada))

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
    aplicarToken()
  } catch (error) {
    // Cookie absent o expirada — es queda a la pantalla de login
  }
})

onBeforeUnmount(() => {
  if (toast.add === feedbackToastAdd) toast.add = nativeToastAdd
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

const resumeAbsence = (record) => {
  paginaActiva.value = 'workbench'
  reschedulingView.value?.resumeAbsence(record)
}
</script>

<style>
:root {
  --primary-color: #193f66;
  --primary-color-dark: #0c2948;
  --primary-color-light: #e7eff7;
  --primary-color-text: #ffffff;
  --highlight-bg: #edf3f8;
  --highlight-text-color: #173d62;
  --text-color-primary: #15263a;
  --text-color-secondary: #687588;
  --background-light: #f3f6f9;
  --card-background: #ffffff;
  --border-color: #d8e0e9;
  --surface-soft: #f7f9fb;
  --sidebar-background: #0c2948;
  --sidebar-active: #254c75;
  --focus-ring: 0 0 0 3px rgba(25, 63, 102, 0.2);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
  background: var(--background-light);
  color: var(--text-color-primary);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

html[lang="zh-HK"] body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
}

.p-button.progress-fill-button {
  position: relative;
  isolation: isolate;
  overflow: hidden;
}

.p-button.progress-fill-button::before {
  content: "";
  position: absolute;
  z-index: 0;
  inset: 0 auto 0 0;
  width: 0;
  background: rgba(255, 255, 255, 0.24);
  pointer-events: none;
}

.p-button.progress-fill-button.is-progressing::before {
  animation: estimated-button-progress 20s cubic-bezier(.12, .72, .18, 1) forwards;
}

.p-button.progress-fill-button .p-button-icon,
.p-button.progress-fill-button .p-button-label {
  position: relative;
  z-index: 1;
}

@keyframes estimated-button-progress {
  0% { width: 0; }
  45% { width: 62%; }
  100% { width: 92%; }
}

@media (prefers-reduced-motion: reduce) {
  .p-button.progress-fill-button.is-progressing::before {
    animation: estimated-button-progress 20s steps(8, end) forwards;
  }
}

button, input, select, textarea { font: inherit; }
button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline: none; box-shadow: var(--focus-ring); }

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
  border-color: var(--primary-color);
  background: var(--primary-color);
}

.p-datepicker-trigger.p-button:hover {
  border-color: var(--primary-color-dark);
  background: var(--primary-color-dark);
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
  min-height: 100dvh;
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
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #edf2f7;
  padding: 2rem;
}

.login-card {
  width: min(430px, 100%);
  background: var(--card-background);
  border-radius: 6px;
  padding: 2.25rem;
  box-shadow: 0 18px 48px rgba(12, 41, 72, 0.1);
  border: 1px solid var(--border-color);
}

.language-control{display:flex;align-items:center;gap:.45rem}.language-control label{font-size:.78rem}.language-control select,.mobile-header-actions select{border:1px solid #d7dce7;border-radius:4px;background:#fff;color:#243047;padding:.35rem .5rem}.login-language{justify-content:flex-end;margin-bottom:1rem;color:var(--text-color-secondary)}.navbar-language select{border-color:var(--border-color)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.mobile-header-actions{display:flex;align-items:center;gap:.35rem}

.login-brand {
  display: flex;
  align-items: center;
  gap: .7rem;
  margin-bottom: 1.35rem;
  color: var(--primary-color-dark);
  font-size: .9rem;
  font-weight: 700;
}

.login-title {
  display: flex;
  align-items: center;
  gap: .7rem;
  font-size: 1.55rem;
  font-weight: 720;
  color: var(--text-color-primary);
  letter-spacing: -.025em;
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

/* App shell */
.app-shell {
  min-height: 100dvh;
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  grid-template-rows: 72px minmax(0, 1fr);
}

.navbar {
  grid-column: 2;
  grid-row: 1;
  position: sticky;
  top: 0;
  z-index: 20;
  min-height: 72px;
  background: var(--card-background);
  color: var(--text-color-primary);
  padding: .75rem 2rem;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
}

.navbar-brand {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 1rem;
}

.logo {
  display: flex;
  align-items: center;
  gap: .65rem;
  font-size: .95rem;
  font-weight: 650;
  margin: 0;
  letter-spacing: 0;
  white-space: nowrap;
}

.school-mark {
  display: block;
  width: 42px;
  height: 42px;
  overflow: hidden;
  flex: 0 0 42px;
  border-radius: 50%;
}

.school-mark img {
  display: block;
  width: auto;
  height: 100%;
  max-width: none;
}

.navbar-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.navbar-right .p-button {
  color: var(--text-color-secondary) !important;
}

.navbar-right .p-button:hover {
  color: var(--primary-color) !important;
  background: var(--primary-color-light) !important;
}

.navbar-right .nav-action {
  padding: .45rem .65rem;
  font-size: .82rem;
  font-weight: 600;
}

.navbar-language select { border-color: var(--border-color); background: var(--surface-soft); color: var(--text-color-primary); }

.sidebar {
  grid-column: 1;
  grid-row: 1 / -1;
  position: sticky;
  top: 0;
  align-self: start;
  height: 100dvh;
  padding: 0;
  background: var(--sidebar-background);
  color: #fff;
  border-right: 0;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: .75rem;
  min-height: 88px;
  padding: 1rem 1.1rem;
  border-bottom: 1px solid rgba(255, 255, 255, .13);
  color: #fff;
  font-size: .88rem;
  font-weight: 700;
  line-height: 1.25;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 1rem .8rem;
}

.sidebar-link {
  display: block;
  align-items: center;
  width: 100%;
  padding: 0.78rem 1rem;
  border: 0;
  border-left: 3px solid transparent;
  border-radius: 3px;
  background: transparent;
  color: rgba(255, 255, 255, .72);
  font: inherit;
  font-size: 0.9rem;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
  transition: color .15s ease, background-color .15s ease;
}

.sidebar-link:hover {
  color: #fff;
  background: rgba(255, 255, 255, .07);
}

.sidebar-link.active {
  color: #fff;
  border-left-color: #9bbad5;
  background: var(--sidebar-active);
}

.app-workspace {
  grid-column: 2;
  grid-row: 2;
  min-width: 0;
  min-height: calc(100dvh - 72px);
  display: flex;
  flex-direction: column;
}

.content-toolbar {
  display: flex;
  justify-content: flex-start;
  width: 100%;
  max-width: 1400px;
  margin: 0 auto;
  padding: 1.35rem 2rem 0;
}

.date-navigator {
  display: flex;
  align-items: center;
  gap: .25rem;
  min-height: 3.15rem;
}

.date-current {
  display: flex;
  align-items: center;
  gap: .75rem;
  min-width: 0;
}

.date-main {
  color: var(--primary-color-dark);
  font-size: 1rem;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
  letter-spacing: -.01em;
}

.date-weekday {
  color: var(--text-color-secondary);
  font-size: .78rem;
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
  padding: 1.5rem 2rem 3rem;
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
  background: var(--card-background);
  color: var(--text-color-secondary);
  border-top: 1px solid var(--border-color);
  text-align: center;
  padding: 1rem;
  font-size: 0.9rem;
}

.feedback-dialog-body { display: flex; align-items: flex-start; gap: .75rem; }
.feedback-dialog-body i { color: #9b3b30; font-size: 1.45rem; }
.feedback-dialog-body.warn i { color: #8a5b16; }
.feedback-dialog-body p { margin: 0; color: var(--text-color-primary); line-height: 1.5; white-space: pre-wrap; }

/* Millores per PrimeVue */
.p-button {
  border-radius: 4px;
  transition: background-color .15s ease, border-color .15s ease, color .15s ease, transform .15s ease;
  padding: 0.65rem 1rem;
  font-size: 0.9rem;
  min-width: unset;
}

.p-button:not(.p-button-text, .p-button-outlined, .p-button-link, .p-button-success, .p-button-danger, .p-button-warning, .p-button-secondary, .p-button-info, .p-button-help) {
  border-color: var(--primary-color);
  background: var(--primary-color);
}

.p-button:not(.p-button-text, .p-button-outlined, .p-button-link, .p-button-success, .p-button-danger, .p-button-warning, .p-button-secondary, .p-button-info, .p-button-help):hover {
  border-color: var(--primary-color-dark);
  background: var(--primary-color-dark);
}

.p-button:active { transform: translateY(1px); }

/* Override per botons amb outline */
.p-button.p-button-outlined {
  border-width: 1px;
}

/* Botons de text, mantenir petits */
.p-button.p-button-text {
    padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
}

.p-datatable {
  box-shadow: none;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  overflow: hidden;
}

/* Responsive shell */
@media (max-width: 992px) {
  .app-shell {
    grid-template-columns: 210px minmax(0, 1fr);
  }

  .navbar {
    gap: .75rem;
    padding: .65rem 1rem;
  }

}

@media (max-width: 720px) {
  .app-shell.is-mobile {
    display: flex;
    flex-direction: column;
  }

  .app-workspace {
    width: 100%;
    min-height: calc(100dvh - 58px);
  }

  .content-toolbar {
    padding: 0.75rem 0.75rem 0;
  }

  .date-current { justify-content: center; }
  .date-main { font-size: .9rem; }
  .date-weekday { font-size: .72rem; }

  .logo {
    font-size: 1rem;
  }

  .mobile-brand {
    display: flex;
    align-items: center;
    gap: .65rem;
    min-width: 0;
  }

  .mobile-brand .school-mark {
    width: 36px;
    height: 36px;
    flex-basis: 36px;
  }

  .main-content {
    padding: 1.25rem 0.75rem 2rem;
  }

  .demo-avis {
    width: calc(100% - 1.5rem);
    margin-top: .75rem;
  }

  .footer {
    font-size: 0.8rem;
    padding: 0.75rem;
  }
}

.mobile-header {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--sidebar-background);
  color: #fff;
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid rgba(255, 255, 255, .14);
}

.mobile-header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mobile-header-actions select { border-color: rgba(255, 255, 255, .35); background: rgba(255, 255, 255, .08); color: #fff; }
.mobile-header-actions .p-button { color: #fff !important; }

.mobile-menu-dialog .p-dialog-header {
  background: var(--sidebar-background);
  color: #fff;
}

.mobile-menu-dialog .p-dialog-header .p-dialog-header-icon {
  color: #fff;
}

.mobile-menu-dialog .p-dialog-content {
  padding: .75rem;
}

.mobile-menu-dialog .mobile-menu .p-button {
  justify-content: flex-start;
  width: 100%;
  border-radius: 3px;
  color: var(--primary-color-dark);
}

.mobile-menu {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.mobile-menu .p-button {
  justify-content: flex-start;
}

.mobile-menu hr {
  width: 100%;
  margin: 0.25rem 0;
  border: 0;
  border-top: 1px solid var(--border-color);
}
</style>
