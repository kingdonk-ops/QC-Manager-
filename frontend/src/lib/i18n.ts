/**
 * i18next, with each module's strings merged in from its manifest.
 * Write user-visible text as `t('key')`; put the English in the module's `messages.en`.
 */
import { MODULE_REGISTRY } from '@/modules/_registry'
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { coreMessages } from './i18n-core'

const resources: Record<string, { translation: Record<string, string> }> = {}

function merge(locale: string, messages: Record<string, string>) {
  resources[locale] ??= { translation: {} }
  Object.assign(resources[locale].translation, messages)
}

for (const [locale, messages] of Object.entries(coreMessages))
  merge(locale, messages)
for (const module of MODULE_REGISTRY)
  for (const [locale, messages] of Object.entries(module.messages ?? {}))
    merge(locale, messages)

void i18n.use(initReactI18next).init({
  resources,
  lng: localStorage.getItem('locale') ?? 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
