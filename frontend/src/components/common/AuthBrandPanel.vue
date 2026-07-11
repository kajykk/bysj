<template>
  <aside class="auth-brand">
    <div class="auth-brand__grain" />
    <div class="auth-brand__orb auth-brand__orb--primary" />
    <div class="auth-brand__orb auth-brand__orb--accent" />

    <header class="auth-brand__top">
      <div class="auth-brand__logo">
        <span class="auth-brand__logo-mark" />
        <span class="auth-brand__logo-text">Mindwatch</span>
      </div>
      <span class="auth-brand__version">v3.1</span>
    </header>

    <div class="auth-brand__body">
      <h1 class="auth-brand__headline">
        <span class="auth-brand__headline-line">{{ headline[0] }}</span>
        <span
          v-if="headline[1]"
          class="auth-brand__headline-line auth-brand__headline-line--accent"
        >{{ headline[1] }}</span>
      </h1>
      <p class="auth-brand__lede">
        {{ lede }}
      </p>

      <ul
        v-if="signals.length"
        class="auth-brand__signals"
      >
        <li
          v-for="(signal, idx) in signals"
          :key="signal.key"
          class="auth-brand__signal"
          :style="{ '--signal-index': idx }"
        >
          <span
            class="auth-brand__signal-dot"
            :class="{ 'breathe-dot': signal.live }"
            :aria-hidden="true"
          />
          <span class="auth-brand__signal-text">{{ signal.label }}</span>
        </li>
      </ul>
    </div>

    <footer class="auth-brand__foot">
      <span
        class="auth-brand__foot-dot breathe-dot"
        aria-hidden="true"
      />
      <span>{{ footStatus }}</span>
    </footer>
  </aside>
</template>

<script setup lang="ts">
export interface BrandSignal {
  key: string
  label: string
  live?: boolean
}

withDefaults(
  defineProps<{
    headline: [string, string?]
    lede: string
    signals?: BrandSignal[]
    footStatus?: string
  }>(),
  {
    signals: () => [],
    footStatus: '实时风险监测中',
  }
)
</script>

<style scoped>
/* ===== 左侧品牌面板（与 LoginPage 共享） ===== */
/* ISS-079 修复：品牌面板色板提取为局部 CSS 变量，便于统一调整与主题切换 */
.auth-brand {
  /* 品牌面板局部色板令牌 */
  --brand-text: #f3f6fb;
  --brand-text-muted: rgba(243, 246, 251, 0.62);
  --brand-text-dim: rgba(243, 246, 251, 0.5);
  --brand-bg-start: #1d2a3a;
  --brand-bg-mid: #131c28;
  --brand-bg-end: #0f1620;
  --brand-accent-blue: #4a9bd6;
  --brand-accent-soft: #6bb4e8;
  --brand-accent-green: #9fd0a8;

  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 3rem 3.5rem;
  color: var(--brand-text);
  background:
    radial-gradient(ellipse at 20% 0%, var(--brand-bg-start) 0%, var(--brand-bg-mid) 55%, var(--brand-bg-end) 100%);
  overflow: hidden;
  isolation: isolate;
}

.auth-brand__grain {
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
  pointer-events: none;
  z-index: 0;
}

.auth-brand__orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  pointer-events: none;
  z-index: 0;
}

.auth-brand__orb--primary {
  width: 420px;
  height: 420px;
  top: -120px;
  right: -100px;
  background: radial-gradient(circle, rgba(74, 155, 214, 0.55), transparent 70%);
  animation: orb-drift-1 14s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

.auth-brand__orb--accent {
  width: 320px;
  height: 320px;
  bottom: -80px;
  left: -60px;
  background: radial-gradient(circle, rgba(90, 158, 58, 0.32), transparent 70%);
  animation: orb-drift-2 18s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes orb-drift-1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-30px, 40px) scale(1.08); }
}

@keyframes orb-drift-2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(40px, -30px) scale(1.12); }
}

.auth-brand__top,
.auth-brand__body,
.auth-brand__foot {
  position: relative;
  z-index: 1;
}

.auth-brand__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.auth-brand__logo {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.auth-brand__logo-mark {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--brand-accent-blue);
  box-shadow: 0 0 16px rgba(74, 155, 214, 0.7);
}

.auth-brand__logo-text {
  font-family: var(--font-family-display);
  font-size: 1.0625rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--brand-text);
}

.auth-brand__version {
  font-family: var(--font-family-mono);
  font-size: 0.75rem;
  color: rgba(243, 246, 251, 0.45);
  letter-spacing: 0.08em;
}

.auth-brand__body {
  max-width: 460px;
  margin-top: -2rem;
}

.auth-brand__headline {
  margin: 0 0 1.5rem;
  font-family: var(--font-family-display);
  font-size: clamp(2.5rem, 4.2vw, 3.75rem);
  font-weight: 700;
  line-height: 1.02;
  letter-spacing: -0.035em;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.auth-brand__headline-line {
  display: block;
  color: rgba(243, 246, 251, 0.92);
}

.auth-brand__headline-line--accent {
  color: transparent;
  background: linear-gradient(120deg, var(--brand-accent-soft) 0%, var(--brand-accent-green) 100%);
  -webkit-background-clip: text;
  background-clip: text;
}

.auth-brand__lede {
  margin: 0 0 2.25rem;
  font-size: 0.9375rem;
  line-height: 1.65;
  color: var(--brand-text-muted);
  max-width: 42ch;
}

.auth-brand__signals {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.auth-brand__signal {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.875rem;
  color: rgba(243, 246, 251, 0.78);
  opacity: 0;
  animation: signal-in 0.6s var(--transition-ease-out) forwards;
  animation-delay: calc(0.3s + var(--signal-index) * 0.12s);
}

@keyframes signal-in {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}

.auth-brand__signal-dot {
  position: relative;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(243, 246, 251, 0.32);
  flex-shrink: 0;
}

.auth-brand__signal-dot.breathe-dot {
  background: var(--brand-accent-soft);
  box-shadow: 0 0 10px rgba(107, 180, 232, 0.6);
}

.auth-brand__foot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--font-family-mono);
  font-size: 0.75rem;
  color: var(--brand-text-dim);
  letter-spacing: 0.04em;
}

.auth-brand__foot-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-accent-green);
  box-shadow: 0 0 8px rgba(159, 208, 168, 0.7);
}

/* 移动端隐藏品牌面板 */
@media (max-width: 960px) {
  .auth-brand {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-brand__orb--primary,
  .auth-brand__orb--accent,
  .auth-brand__signal,
  .auth-brand__foot-dot {
    animation: none !important;
  }

  .auth-brand__signal {
    opacity: 1;
  }
}
</style>
