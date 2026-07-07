import './styles/variables.scss'

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

Object.defineProperty(navigator, 'sendBeacon', {
  writable: true,
  value: () => true,
})

const rootVariables: Record<string, string> = {
  '--primary-color': '#3b82c4',
  '--spacing-base': '8px',
  '--font-size-base': '14px',
  '--breakpoint-mobile': '768px',
  '--breakpoint-tablet': '1280px',
}

for (const [name, value] of Object.entries(rootVariables)) {
  document.documentElement.style.setProperty(name, value)
}
