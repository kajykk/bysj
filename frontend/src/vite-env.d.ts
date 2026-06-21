/// <reference types="vite/client" />
/// <reference path="./types/vite-env.d.ts" />

export {}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// vue-i18n type declarations
declare module 'vue-i18n' {
  export * from 'vue-i18n/dist/vue-i18n.d.ts'
}

// Extend Vue component instance to include $t
declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $t: (key: string, ...args: any[]) => string
    $i18n: any
  }
}

// Performance API types
declare interface LayoutShift extends PerformanceEntry {
  value: number
  hadRecentInput: boolean
}

// Element Plus icon types are declared in src/types/element-plus-icons.d.ts