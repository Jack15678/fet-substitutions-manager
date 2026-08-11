import { createI18n } from 'vue-i18n'
import zhHK from './locales/zh-HK.json'
import en from './locales/en.json'

const savedLocale = localStorage.getItem('app_locale')
const storedLocale = savedLocale === 'en' ? 'en' : 'zh-HK'
const applyDocumentLocale = (locale) => {
  document.documentElement.lang = locale
  document.title = locale === 'en' ? en.app.title : zhHK.app.title
}

export const primeLocales = {
  'zh-HK': {
    firstDayOfWeek: 1,
    dayNames: ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'],
    dayNamesShort: ['日', '一', '二', '三', '四', '五', '六'],
    dayNamesMin: ['日', '一', '二', '三', '四', '五', '六'],
    monthNames: ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'],
    monthNamesShort: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
    today: '今日', clear: '清除', weekHeader: '週', dateFormat: 'dd/mm/yy'
  },
  en: {
    firstDayOfWeek: 1,
    dayNames: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
    dayNamesShort: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
    dayNamesMin: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'],
    monthNames: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    monthNamesShort: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
    today: 'Today', clear: 'Clear', weekHeader: 'Wk', dateFormat: 'dd/mm/yy'
  }
}

const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: storedLocale,
  fallbackLocale: 'en',
  messages: { 'zh-HK': zhHK, en }
})

export const setLocale = (value) => {
  const next = value === 'en' ? 'en' : 'zh-HK'
  i18n.global.locale.value = next
  localStorage.setItem('app_locale', next)
  applyDocumentLocale(next)
}

applyDocumentLocale(storedLocale)

export default i18n
