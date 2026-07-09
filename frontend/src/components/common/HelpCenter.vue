<template>
  <el-dropdown
    trigger="click"
    placement="bottom-end"
    @command="handleCommand"
  >
    <el-button
      size="small"
      :icon="QuestionFilled"
      circle
      :aria-label="t('help.buttonLabel')"
    />
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="onboarding">
          <el-icon><Guide /></el-icon>
          {{ t('help.onboarding') }}
        </el-dropdown-item>
        <el-dropdown-item command="faq">
          <el-icon><Document /></el-icon>
          {{ t('help.faqLabel') }}
        </el-dropdown-item>
        <el-dropdown-item command="contact">
          <el-icon><Message /></el-icon>
          {{ t('help.contactSupport') }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <!-- FAQ 弹窗 -->
  <el-dialog
    v-model="faqVisible"
    :title="t('help.faqTitle')"
    width="600px"
    :before-close="closeFaq"
    append-to-body
  >
    <el-collapse v-model="activeFaqItems">
      <el-collapse-item
        v-for="(item, idx) in faqList"
        :key="idx"
        :name="String(idx)"
      >
        <template #title>
          <span class="faq-question">{{ item.q }}</span>
        </template>
        <p class="faq-answer">{{ item.a }}</p>
      </el-collapse-item>
    </el-collapse>
  </el-dialog>

  <!-- 联系支持弹窗 -->
  <el-dialog
    v-model="contactVisible"
    :title="t('help.contactTitle')"
    width="440px"
    :before-close="closeContact"
    append-to-body
  >
    <div class="contact-info">
      <div class="contact-item">
        <el-icon><Message /></el-icon>
        <div>
          <p class="contact-label">{{ t('help.emailLabel') }}</p>
          <p class="contact-value">support@dws.local</p>
        </div>
      </div>
      <div class="contact-item">
        <el-icon><Phone /></el-icon>
        <div>
          <p class="contact-label">{{ t('help.phoneLabel') }}</p>
          <p class="contact-value">400-000-0000</p>
        </div>
      </div>
      <div class="contact-item">
        <el-icon><Clock /></el-icon>
        <div>
          <p class="contact-label">{{ t('help.hoursLabel') }}</p>
          <p class="contact-value">{{ t('help.hoursValue') }}</p>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionFilled, Guide, Document, Message, Phone, Clock } from '@element-plus/icons-vue'

const { t } = useI18n()

const props = defineProps<{
  onRestartOnboarding: () => void
}>()

const faqVisible = ref(false)
const contactVisible = ref(false)
const activeFaqItems = ref<string[]>(['0'])

const faqList = computed(() => [
  { q: t('help.faq.q1'), a: t('help.faq.a1') },
  { q: t('help.faq.q2'), a: t('help.faq.a2') },
  { q: t('help.faq.q3'), a: t('help.faq.a3') },
  { q: t('help.faq.q4'), a: t('help.faq.a4') },
  { q: t('help.faq.q5'), a: t('help.faq.a5') },
  { q: t('help.faq.q6'), a: t('help.faq.a6') },
])

const handleCommand = (command: string) => {
  if (command === 'onboarding') {
    props.onRestartOnboarding()
  } else if (command === 'faq') {
    faqVisible.value = true
  } else if (command === 'contact') {
    contactVisible.value = true
  }
}

const closeFaq = () => { faqVisible.value = false }
const closeContact = () => { contactVisible.value = false }
</script>

<style scoped>
.faq-question {
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.faq-answer {
  margin: 0;
  color: var(--text-regular);
  line-height: var(--line-height-relaxed);
}

.contact-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.contact-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
}

.contact-item .el-icon {
  font-size: 20px;
  color: var(--primary-color);
  margin-top: 2px;
}

.contact-label {
  margin: 0 0 2px;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.contact-value {
  margin: 0;
  font-size: var(--font-size-base);
  color: var(--text-primary);
  font-weight: var(--font-weight-medium);
}
</style>
