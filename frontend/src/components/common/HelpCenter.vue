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
        <el-dropdown-item command="feedback">
          <el-icon><EditPen /></el-icon>
          {{ t('help.feedbackLabel') }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <!-- FAQ 弹窗 -->
  <el-dialog
    v-model="faqVisible"
    :title="t('help.faqTitle')"
    :width="isMobile ? '90vw' : '600px'"
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
        <p class="faq-answer">
          {{ item.a }}
        </p>
      </el-collapse-item>
    </el-collapse>
  </el-dialog>

  <!-- 联系支持弹窗 -->
  <el-dialog
    v-model="contactVisible"
    :title="t('help.contactTitle')"
    :width="isMobile ? '90vw' : '440px'"
    :before-close="closeContact"
    append-to-body
  >
    <div class="contact-info">
      <div class="contact-item">
        <el-icon><Message /></el-icon>
        <div>
          <p class="contact-label">
            {{ t('help.emailLabel') }}
          </p>
          <p class="contact-value">
            support@dws.local
          </p>
        </div>
      </div>
      <div class="contact-item">
        <el-icon><Phone /></el-icon>
        <div>
          <p class="contact-label">
            {{ t('help.phoneLabel') }}
          </p>
          <p class="contact-value">
            400-000-0000
          </p>
        </div>
      </div>
      <div class="contact-item">
        <el-icon><Clock /></el-icon>
        <div>
          <p class="contact-label">
            {{ t('help.hoursLabel') }}
          </p>
          <p class="contact-value">
            {{ t('help.hoursValue') }}
          </p>
        </div>
      </div>
    </div>
  </el-dialog>

  <!-- 反馈弹窗 -->
  <el-dialog
    v-model="feedbackVisible"
    :title="t('help.feedbackTitle')"
    :width="isMobile ? '90vw' : '480px'"
    append-to-body
  >
    <el-form label-position="top">
      <el-form-item :label="t('help.feedbackCategoryLabel')">
        <el-select
          v-model="feedbackCategory"
          style="width: 100%"
        >
          <el-option
            :label="t('help.feedbackCategoryBug')"
            value="bug"
          />
          <el-option
            :label="t('help.feedbackCategoryFeature')"
            value="feature"
          />
          <el-option
            :label="t('help.feedbackCategoryOther')"
            value="other"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('help.feedbackMessageLabel')">
        <el-input
          v-model="feedbackMessage"
          type="textarea"
          :rows="4"
          :placeholder="t('help.feedbackMessagePlaceholder')"
        />
      </el-form-item>
    </el-form>
    <div class="feedback-footer">
      <el-link
        :href="githubIssuesUrl"
        target="_blank"
        type="primary"
        :underline="false"
      >
        <el-icon><Link /></el-icon>
        {{ t('help.githubIssues') }}
      </el-link>
      <el-button
        type="primary"
        @click="submitFeedback"
      >
        {{ t('help.feedbackSubmit') }}
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { QuestionFilled, Guide, Document, Message, Phone, Clock, EditPen, Link } from '@element-plus/icons-vue'

const { t } = useI18n()

const props = defineProps<{
  onRestartOnboarding: () => void
}>()

const isMobile = ref(false)
const checkMobile = () => { isMobile.value = window.matchMedia('(max-width: 768px)').matches }
onMounted(() => { checkMobile(); window.addEventListener('resize', checkMobile) })
onUnmounted(() => { window.removeEventListener('resize', checkMobile) })

const faqVisible = ref(false)
const contactVisible = ref(false)
const feedbackVisible = ref(false)
const activeFaqItems = ref<string[]>(['0'])
const feedbackCategory = ref<'bug' | 'feature' | 'other'>('bug')
const feedbackMessage = ref('')

const GITHUB_ISSUES_URL = 'https://github.com/kajykk/bysj/issues'
const githubIssuesUrl = GITHUB_ISSUES_URL

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
  } else if (command === 'feedback') {
    feedbackVisible.value = true
  }
}

const closeFaq = () => { faqVisible.value = false }
const closeContact = () => { contactVisible.value = false }

const submitFeedback = () => {
  if (!feedbackMessage.value.trim()) {
    ElMessage.warning(t('help.feedbackEmpty'))
    return
  }
  const categoryLabel = t(`help.feedbackCategory${feedbackCategory.value.charAt(0).toUpperCase()}${feedbackCategory.value.slice(1)}`)
  const title = encodeURIComponent(`[${categoryLabel}] ${feedbackMessage.value.slice(0, 50)}`)
  const body = encodeURIComponent(feedbackMessage.value)
  window.open(`${GITHUB_ISSUES_URL}/new?title=${title}&body=${body}`, '_blank')
  feedbackVisible.value = false
  feedbackMessage.value = ''
  ElMessage.success(t('help.feedbackSubmitted'))
}
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

.feedback-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: var(--spacing-md);
}
</style>
