<template>
  <div class="risk-page">
    <el-tabs
      v-model="activeTab"
      type="border-card"
    >
      <el-tab-pane
        label="概览报告"
        name="report"
      >
        <StatefulContainer
          :loading="reportLoading"
          :empty="false"
          :error-message="reportError"
          @retry="loadReport"
        >
          <template v-if="report">
            <el-row :gutter="16">
              <el-col :span="8">
                <el-card>
                  <div class="report-score-wrap">
                    <el-progress
                      type="dashboard"
                      :percentage="report.risk_score"
                      :color="scoreColor"
                      :width="140"
                    >
                      <template #default="{ percentage }">
                        <div class="dashboard-score">
                          <span class="score-num">{{ percentage }}</span>
                          <span class="score-label">概览分</span>
                        </div>
                      </template>
                    </el-progress>
                  </div>
                  <div class="report-meta">
                    <el-tag :type="severityTagType">
                      {{ severityLabel }}
                    </el-tag>
                    <el-tag
                      v-if="report.review_required"
                      type="warning"
                      effect="dark"
                    >
                      需要人工审核
                    </el-tag>
                    <el-tag
                      v-if="report.crisis_override"
                      type="danger"
                      effect="dark"
                    >
                      危机表达覆盖
                    </el-tag>
                    <span class="trend-text">
                      趋势：
                      <el-icon
                        v-if="report.trend === 'up'"
                        color="#f56c6c"
                      ><Top /></el-icon>
                      <el-icon
                        v-else-if="report.trend === 'down'"
                        color="#67c23a"
                      ><Bottom /></el-icon>
                      <span v-else>稳定</span>
                    </span>
                  </div>
                  <el-descriptions
                    v-if="report.physiological_score != null || report.modality_contributions"
                    :column="1"
                    border
                    size="small"
                    style="margin-top: 12px"
                  >
                    <el-descriptions-item label="生理分数">
                      {{ report.physiological_score ?? '暂无' }}
                    </el-descriptions-item>
                    <el-descriptions-item label="模态贡献">
                      <span v-if="report.modality_contributions">
                        {{ Object.entries(report.modality_contributions).map(([key, value]) => `${modalityLabelMap[key] || key}: ${value ?? '暂无'}`).join('；') }}
                      </span>
                      <span v-else>暂无</span>
                    </el-descriptions-item>
                    <el-descriptions-item
                      v-if="report.risk_factors?.length"
                      label="风险因子"
                    >
                      <el-tag
                        v-for="factor in report.risk_factors"
                        :key="factor.feature"
                        type="danger"
                        size="small"
                        style="margin-right: 4px; margin-bottom: 4px"
                      >
                        {{ featureLabelMap[factor.feature] || factor.feature }}
                      </el-tag>
                    </el-descriptions-item>
                    <el-descriptions-item
                      v-if="report.protective_factors?.length"
                      label="保护因素"
                    >
                      <el-tag
                        v-for="factor in report.protective_factors"
                        :key="factor.feature"
                        type="success"
                        size="small"
                        style="margin-right: 4px; margin-bottom: 4px"
                      >
                        {{ featureLabelMap[factor.feature] || factor.feature }}
                      </el-tag>
                    </el-descriptions-item>
                    <el-descriptions-item
                      v-if="report.review_flags?.length"
                      label="审核原因"
                    >
                      <el-tag
                        v-for="flag in report.review_flags"
                        :key="flag.feature"
                        type="warning"
                        size="small"
                        style="margin-right: 4px; margin-bottom: 4px"
                      >
                        {{ flag.feature }}
                      </el-tag>
                    </el-descriptions-item>
                  </el-descriptions>
                </el-card>
              </el-col>

              <el-col :span="16">
                <el-card>
                  <template #header>
                    <span class="card-title">因子与建议</span>
                  </template>
                  <el-table
                    v-if="report.main_factors?.length"
                    :data="report.main_factors"
                    size="small"
                    stripe
                    sortable="custom"
                  >
                    <el-table-column
                      prop="feature"
                      label="因子"
                      min-width="140"
                      sortable
                    >
                      <template #default="{ row }">
                        {{ featureLabelMap[row.feature] || row.feature }}
                      </template>
                    </el-table-column>
                    <el-table-column
                      prop="importance"
                      label="重要性"
                      width="120"
                      sortable
                      :sort-method="(a: ReportFactor, b: ReportFactor) => a.importance - b.importance"
                    >
                      <template #default="{ row }">
                        <el-progress
                          :percentage="Math.min(row.importance * 100, 100)"
                          :show-text="false"
                          :stroke-width="8"
                        />
                      </template>
                    </el-table-column>
                    <el-table-column
                      prop="direction"
                      label="方向"
                      width="100"
                    >
                      <template #default="{ row }">
                        <el-tag
                          :type="getFactorDirectionTagType(row.direction)"
                          size="small"
                        >
                          {{ getFactorDirectionLabel(row.direction) }}
                        </el-tag>
                      </template>
                    </el-table-column>
                  </el-table>
                  <el-empty
                    v-else
                    description="暂无因子数据"
                    :image-size="60"
                  />
                </el-card>
              </el-col>
            </el-row>

            <el-card style="margin-top: 16px">
              <template #header>
                <span class="card-title">建议</span>
              </template>
              <div
                v-if="report.advice?.length"
                class="advice-cards"
              >
                <el-card
                  v-for="(a, i) in report.advice"
                  :key="i"
                  shadow="hover"
                  class="advice-card"
                  :body-style="{ padding: '14px 16px' }"
                >
                  <div class="advice-index">
                    {{ Number(i) + 1 }}
                  </div>
                  <div class="advice-text">
                    {{ a }}
                  </div>
                </el-card>
              </div>
              <p
                v-else
                class="text-muted"
              >
                暂无建议
              </p>
            </el-card>

            <el-card style="margin-top: 16px">
              <template #header>
                <div class="header-row">
                  <span class="card-title">概览趋势</span>
                  <el-dropdown
                    v-if="canExportRisk"
                    @command="handleExport"
                  >
                    <el-button
                      type="primary"
                      size="small"
                    >
                      导出概览<el-icon class="el-icon--right">
                        <ArrowDown />
                      </el-icon>
                    </el-button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="json">
                          JSON 概览
                        </el-dropdown-item>
                        <el-dropdown-item command="csv">
                          CSV 概览
                        </el-dropdown-item>
                        <el-dropdown-item command="pdf">
                          PDF 概览
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </template>
              <div
                ref="reportTrendRef"
                style="height: 260px"
              />
            </el-card>
          </template>
        </StatefulContainer>
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        label="结构化概览"
        name="structured"
      >
        <el-row :gutter="16">
          <el-col :span="24">
            <el-card class="panel-card">
              <template #header>
                <div class="header-row">
                  <span class="card-title">结构化概览表单</span>
                  <div class="header-actions">
                    <el-radio-group
                      v-model="structuredMode"
                      size="small"
                    >
                      <el-radio-button value="single">
                        单页模式
                      </el-radio-button>
                      <el-radio-button value="stepper">
                        分步向导
                      </el-radio-button>
                    </el-radio-group>
                    <el-tag
                      type="warning"
                      effect="light"
                    >
                      新版结构化模型
                    </el-tag>
                  </div>
                </div>
              </template>

              <!-- 单页模式 -->
              <el-form
                v-if="structuredMode === 'single'"
                ref="structuredFormRef"
                :model="structuredForm"
                :rules="structuredRules"
                label-width="120px"
                class="compact-form"
              >
                <el-form-item
                  label="当前身份"
                  prop="identity_type"
                >
                  <el-radio-group v-model="structuredForm.identity_type">
                    <el-radio value="student">
                      在校学生
                    </el-radio>
                    <el-radio value="worker">
                      已工作/非在校
                    </el-radio>
                  </el-radio-group>
                </el-form-item>
                <el-form-item
                  label="年龄"
                  prop="age"
                >
                  <el-input-number
                    v-model="structuredForm.age"
                    :min="15"
                    :max="60"
                  />
                </el-form-item>
                <el-form-item
                  label="性别"
                  prop="gender"
                >
                  <el-select
                    v-model="structuredForm.gender"
                    style="width: 100%"
                  >
                    <el-option
                      label="男"
                      :value="1"
                    />
                    <el-option
                      label="女"
                      :value="0"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item
                  v-if="structuredForm.identity_type === 'student'"
                  label="年级"
                  prop="study_year"
                >
                  <el-input-number
                    v-model="structuredForm.study_year"
                    :min="1"
                    :max="6"
                  />
                </el-form-item>
                <el-form-item
                  label="GPA"
                  prop="cgpa"
                >
                  <div class="slider-with-value">
                    <el-slider
                      v-model="structuredForm.cgpa"
                      :min="0"
                      :max="10"
                      :step="0.1"
                      show-input
                    />
                    <span class="slider-value-label">{{ structuredForm.cgpa.toFixed(1) }} / 10</span>
                  </div>
                </el-form-item>
                <el-form-item
                  label="压力水平"
                  prop="stress_level"
                >
                  <div class="slider-with-value">
                    <el-slider
                      v-model="structuredForm.stress_level"
                      :min="0"
                      :max="5"
                      :step="1"
                      show-input
                    />
                    <span class="slider-value-label">{{ structuredForm.stress_level }} / 5</span>
                  </div>
                </el-form-item>
                <el-form-item
                  label="睡眠时长(h)"
                  prop="sleep_duration"
                >
                  <div class="slider-with-value">
                    <el-slider
                      v-model="structuredForm.sleep_duration"
                      :min="0"
                      :max="12"
                      :step="0.5"
                      show-input
                    />
                    <span class="slider-value-label">{{ structuredForm.sleep_duration }} 小时</span>
                  </div>
                </el-form-item>
                <el-form-item
                  label="社会支持"
                  prop="social_support"
                >
                  <div class="slider-with-value">
                    <el-slider
                      v-model="structuredForm.social_support"
                      :min="0"
                      :max="5"
                      :step="1"
                      show-input
                    />
                    <span class="slider-value-label">{{ structuredForm.social_support }} / 5</span>
                  </div>
                </el-form-item>
                <el-form-item
                  label="经济压力"
                  prop="financial_pressure"
                >
                  <div class="slider-with-value">
                    <el-slider
                      v-model="structuredForm.financial_pressure"
                      :min="0"
                      :max="5"
                      :step="1"
                      show-input
                    />
                    <span class="slider-value-label">{{ structuredForm.financial_pressure }} / 5</span>
                  </div>
                </el-form-item>
                <el-form-item
                  label="家族史"
                  prop="family_history"
                >
                  <el-select
                    v-model="structuredForm.family_history"
                    style="width: 100%"
                  >
                    <el-option
                      label="无"
                      :value="0"
                    />
                    <el-option
                      label="有"
                      :value="1"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item
                  label="学业压力"
                  prop="academic_pressure"
                >
                  <div class="slider-with-value">
                    <el-slider
                      v-model="structuredForm.academic_pressure"
                      :min="0"
                      :max="5"
                      :step="1"
                      show-input
                    />
                    <span class="slider-value-label">{{ structuredForm.academic_pressure }} / 5</span>
                  </div>
                </el-form-item>
                <el-form-item
                  label="运动频率"
                  prop="exercise_frequency"
                >
                  <div class="slider-with-value">
                    <el-slider
                      v-model="structuredForm.exercise_frequency"
                      :min="0"
                      :max="7"
                      :step="1"
                      show-input
                    />
                    <span class="slider-value-label">{{ structuredForm.exercise_frequency }} 次/周</span>
                  </div>
                </el-form-item>
                <el-form-item
                  label="焦虑程度"
                  prop="anxiety"
                >
                  <div class="slider-with-value">
                    <el-slider
                      v-model="structuredForm.anxiety"
                      :min="0"
                      :max="5"
                      :step="1"
                      show-input
                    />
                    <span class="slider-value-label">{{ structuredForm.anxiety }} / 5</span>
                  </div>
                </el-form-item>
                <el-form-item
                  label="恐慌发作"
                  prop="panic_attack"
                >
                  <el-select
                    v-model="structuredForm.panic_attack"
                    style="width: 100%"
                  >
                    <el-option
                      label="无"
                      :value="0"
                    />
                    <el-option
                      label="有"
                      :value="1"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item
                  label="寻求治疗"
                  prop="treatment_seeking"
                >
                  <el-select
                    v-model="structuredForm.treatment_seeking"
                    style="width: 100%"
                  >
                    <el-option
                      label="否"
                      :value="0"
                    />
                    <el-option
                      label="是"
                      :value="1"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item>
                  <el-button
                    type="primary"
                    :loading="structuredSubmitting"
                    @click="submitStructured"
                  >
                    提交概览
                  </el-button>
                  <el-button
                    style="margin-left: 8px"
                    @click="resetStructuredForm"
                  >
                    恢复默认
                  </el-button>
                </el-form-item>
              </el-form>

              <!-- 分步向导模式 -->
              <el-form
                v-else
                ref="structuredStepFormRef"
                :model="structuredForm"
                :rules="structuredRules"
                label-width="120px"
                class="compact-form"
              >
                <el-steps
                  :active="structuredStep"
                  finish-status="success"
                  simple
                >
                  <el-step title="基本信息" />
                  <el-step title="学业/工作" />
                  <el-step title="生活状态" />
                  <el-step title="心理状况" />
                </el-steps>

                <div
                  v-show="structuredStep === 0"
                  class="step-content"
                >
                  <el-form-item
                    label="当前身份"
                    prop="identity_type"
                  >
                    <el-radio-group v-model="structuredForm.identity_type">
                      <el-radio label="student">
                        在校学生
                      </el-radio>
                      <el-radio label="worker">
                        已工作/非在校
                      </el-radio>
                    </el-radio-group>
                  </el-form-item>
                  <el-form-item
                    label="年龄"
                    prop="age"
                  >
                    <el-input-number
                      v-model="structuredForm.age"
                      :min="15"
                      :max="60"
                    />
                  </el-form-item>
                  <el-form-item
                    label="性别"
                    prop="gender"
                  >
                    <el-select
                      v-model="structuredForm.gender"
                      style="width: 100%"
                    >
                      <el-option
                        label="男"
                        :value="1"
                      />
                      <el-option
                        label="女"
                        :value="0"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item
                    v-if="structuredForm.identity_type === 'student'"
                    label="年级"
                    prop="study_year"
                  >
                    <el-input-number
                      v-model="structuredForm.study_year"
                      :min="1"
                      :max="6"
                    />
                  </el-form-item>
                </div>

                <div
                  v-show="structuredStep === 1"
                  class="step-content"
                >
                  <el-form-item
                    label="GPA"
                    prop="cgpa"
                  >
                    <div class="slider-with-value">
                      <el-slider
                        v-model="structuredForm.cgpa"
                        :min="0"
                        :max="10"
                        :step="0.1"
                        show-input
                      />
                      <span class="slider-value-label">{{ structuredForm.cgpa.toFixed(1) }} / 10</span>
                    </div>
                  </el-form-item>
                  <el-form-item
                    label="学业压力"
                    prop="academic_pressure"
                  >
                    <div class="slider-with-value">
                      <el-slider
                        v-model="structuredForm.academic_pressure"
                        :min="0"
                        :max="5"
                        :step="1"
                        show-input
                      />
                      <span class="slider-value-label">{{ structuredForm.academic_pressure }} / 5</span>
                    </div>
                  </el-form-item>
                  <el-form-item
                    label="经济压力"
                    prop="financial_pressure"
                  >
                    <div class="slider-with-value">
                      <el-slider
                        v-model="structuredForm.financial_pressure"
                        :min="0"
                        :max="5"
                        :step="1"
                        show-input
                      />
                      <span class="slider-value-label">{{ structuredForm.financial_pressure }} / 5</span>
                    </div>
                  </el-form-item>
                </div>

                <div
                  v-show="structuredStep === 2"
                  class="step-content"
                >
                  <el-form-item
                    label="睡眠时长(h)"
                    prop="sleep_duration"
                  >
                    <div class="slider-with-value">
                      <el-slider
                        v-model="structuredForm.sleep_duration"
                        :min="0"
                        :max="12"
                        :step="0.5"
                        show-input
                      />
                      <span class="slider-value-label">{{ structuredForm.sleep_duration }} 小时</span>
                    </div>
                  </el-form-item>
                  <el-form-item
                    label="运动频率"
                    prop="exercise_frequency"
                  >
                    <div class="slider-with-value">
                      <el-slider
                        v-model="structuredForm.exercise_frequency"
                        :min="0"
                        :max="7"
                        :step="1"
                        show-input
                      />
                      <span class="slider-value-label">{{ structuredForm.exercise_frequency }} 次/周</span>
                    </div>
                  </el-form-item>
                  <el-form-item
                    label="社会支持"
                    prop="social_support"
                  >
                    <div class="slider-with-value">
                      <el-slider
                        v-model="structuredForm.social_support"
                        :min="0"
                        :max="5"
                        :step="1"
                        show-input
                      />
                      <span class="slider-value-label">{{ structuredForm.social_support }} / 5</span>
                    </div>
                  </el-form-item>
                </div>

                <div
                  v-show="structuredStep === 3"
                  class="step-content"
                >
                  <el-form-item
                    label="压力水平"
                    prop="stress_level"
                  >
                    <div class="slider-with-value">
                      <el-slider
                        v-model="structuredForm.stress_level"
                        :min="0"
                        :max="5"
                        :step="1"
                        show-input
                      />
                      <span class="slider-value-label">{{ structuredForm.stress_level }} / 5</span>
                    </div>
                  </el-form-item>
                  <el-form-item
                    label="焦虑程度"
                    prop="anxiety"
                  >
                    <div class="slider-with-value">
                      <el-slider
                        v-model="structuredForm.anxiety"
                        :min="0"
                        :max="5"
                        :step="1"
                        show-input
                      />
                      <span class="slider-value-label">{{ structuredForm.anxiety }} / 5</span>
                    </div>
                  </el-form-item>
                  <el-form-item
                    label="家族史"
                    prop="family_history"
                  >
                    <el-select
                      v-model="structuredForm.family_history"
                      style="width: 100%"
                    >
                      <el-option
                        label="无"
                        :value="0"
                      />
                      <el-option
                        label="有"
                        :value="1"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item
                    label="恐慌发作"
                    prop="panic_attack"
                  >
                    <el-select
                      v-model="structuredForm.panic_attack"
                      style="width: 100%"
                    >
                      <el-option
                        label="无"
                        :value="0"
                      />
                      <el-option
                        label="有"
                        :value="1"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item
                    label="寻求治疗"
                    prop="treatment_seeking"
                  >
                    <el-select
                      v-model="structuredForm.treatment_seeking"
                      style="width: 100%"
                    >
                      <el-option
                        label="否"
                        :value="0"
                      />
                      <el-option
                        label="是"
                        :value="1"
                      />
                    </el-select>
                  </el-form-item>
                </div>

                <div class="step-actions">
                  <el-button
                    v-if="structuredStep > 0"
                    @click="structuredStep--"
                  >
                    上一步
                  </el-button>
                  <el-button
                    v-if="structuredStep < 3"
                    type="primary"
                    @click="handleStepNext"
                  >
                    下一步
                  </el-button>
                  <el-button
                    v-else
                    type="primary"
                    :loading="structuredSubmitting"
                    @click="submitStructured"
                  >
                    提交评估
                  </el-button>
                  <el-button
                    style="margin-left: 8px"
                    @click="resetStructuredForm"
                  >
                    恢复默认
                  </el-button>
                </div>
              </el-form>
            </el-card>
          </el-col>
        </el-row>

        <el-card
          v-if="structuredResult || modelTabResult"
          style="margin-top: 16px"
          class="result-panel"
        >
          <template #header>
            <div class="header-row">
              <span class="card-title">概览结果</span>
              <el-tag
                type="success"
                effect="light"
              >
                双层结果展示
              </el-tag>
            </div>
          </template>

          <div
            v-if="modelTabResult?.requires_human_review"
            style="margin-bottom: 12px"
          >
            <el-alert
              type="warning"
              :closable="false"
              show-icon
            >
              <template #title>
                检测到危机关键词，建议人工审核
                <span v-if="modelTabResult?.crisis_keywords_matched?.length">
                  ：{{ modelTabResult.crisis_keywords_matched.join('、') }}
                </span>
              </template>
            </el-alert>
          </div>

          <div
            v-if="modelTabResult?.routing_info"
            class="routing-info-bar"
          >
            <el-tag
              :type="routeFamilyTagType(modelTabResult.routing_info.selected_model_family)"
              size="small"
              effect="dark"
            >
              {{ routeFamilyLabel(modelTabResult.routing_info.selected_model_family) }}
            </el-tag>
            <span class="routing-reason">{{ routeReasonLabel(modelTabResult.routing_info.routing_reason) }}</span>
            <el-tag
              v-if="modelTabResult.routing_info.prediction_confidence_band"
              :type="confidenceTagType(modelTabResult.routing_info.prediction_confidence_band)"
              size="small"
              effect="plain"
            >
              {{ confidenceLabel(modelTabResult.routing_info.prediction_confidence_band) }}
            </el-tag>
          </div>

          <el-row
            :gutter="16"
            class="result-grid"
          >
            <el-col :span="12">
              <el-card
                shadow="never"
                class="mini-result-card"
              >
                <template #header>
                  <span class="mini-title">模型概览</span>
                </template>
                <el-result
                  :icon="(modelTabResult?.risk_level ?? 0) <= 1 ? 'success' : (modelTabResult?.risk_level ?? 0) <= 2 ? 'warning' : 'error'"
                  :title="severityFromLevel(modelTabResult?.risk_level ?? 0)"
                >
                  <template #sub-title>
                    <p>风险分数：{{ modelTabResult?.risk_score != null ? modelTabResult.risk_score.toFixed(2) : '-' }}</p>
                    <p>业务等级：{{ modelTabResult ? severityFromLevel(modelTabResult.risk_level ?? 0) : '-' }}</p>
                    <p>模型名称：{{ modelTabResult?.model_used || '-' }}</p>
                  </template>
                </el-result>
                <el-descriptions
                  v-if="modelTabResult"
                  :column="1"
                  border
                  size="small"
                  style="margin-top: 12px"
                >
                  <el-descriptions-item label="模型版本">
                    {{ modelTabResult.model_version || '暂无' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="模型家族">
                    {{ routeFamilyLabel(modelTabResult.model_family) }}
                  </el-descriptions-item>
                  <el-descriptions-item label="是否回退">
                    {{ modelTabResult.fallback_used ? '是' : '否' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="回退原因">
                    {{ modelTabResult.fallback_reason || '暂无' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="人工复核">
                    {{ modelTabResult.requires_human_review ? '需要' : '不需要' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="安全标记">
                    {{ formatArrayText(modelTabResult.safety_flags, '、') }}
                  </el-descriptions-item>
                  <el-descriptions-item label="危机关键词">
                    {{ formatArrayText(modelTabResult.crisis_keywords_matched, '、') }}
                  </el-descriptions-item>
                  <el-descriptions-item label="系统提示">
                    {{ modelTabResult.warning || '暂无' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="数据质量">
                    {{ modelTabResult.data_quality?.quality_level || 'unknown' }}
                    <span v-if="modelTabResult.data_quality?.missing_fields?.length">
                      ，缺失字段：{{ formatArrayText(modelTabResult.data_quality.missing_fields, '、') }}
                    </span>
                  </el-descriptions-item>
                </el-descriptions>
                <div
                  v-if="modelTabResult?.routing_info"
                  class="experimental-ref"
                >
                  <el-divider style="margin: 8px 0" />
                  <el-tag
                    type="info"
                    size="small"
                    effect="plain"
                  >
                    路由信息
                  </el-tag>
                  <p style="margin-top: 6px">
                    选中模型 ID：{{ modelTabResult.routing_info.selected_model_id || '-' }}<br>
                    选中模型家族：{{ routeFamilyLabel(modelTabResult.routing_info.selected_model_family) }}<br>
                    路由原因：{{ routeReasonLabel(modelTabResult.routing_info.routing_reason) }}<br>
                    特征覆盖率：{{ modelTabResult.routing_info.feature_coverage_ratio != null ? (modelTabResult.routing_info.feature_coverage_ratio * 100).toFixed(1) + '%' : '-' }}<br>
                    置信区间：{{ confidenceLabel(modelTabResult.routing_info.prediction_confidence_band) }}
                  </p>
                </div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card
                shadow="never"
                class="mini-result-card"
              >
                <template #header>
                  <span class="mini-title">业务概览</span>
                </template>
                <el-result
                  :icon="(structuredResult?.risk_level ?? 0) <= 1 ? 'success' : (structuredResult?.risk_level ?? 0) <= 2 ? 'warning' : 'error'"
                  :title="severityFromLevel(structuredResult?.risk_level ?? 0)"
                >
                  <template #sub-title>
                    <p>风险分数：{{ structuredResult ? structuredResult.risk_score : '-' }}</p>
                    <p>严重程度：{{ structuredResult ? structuredResult.severity : '-' }}</p>
                    <p>预警触发：{{ structuredResult ? (structuredResult.warning_generated ? '是' : '否') : '-' }}</p>
                  </template>
                </el-result>
              </el-card>
            </el-col>
          </el-row>
          <div class="result-actions">
            <el-button
              type="primary"
              @click="activeTab = 'report'"
            >
              查看概览报告
            </el-button>
            <el-button
              :disabled="!structuredResult && !modelTabResult"
              @click="copyLatestStructuredResult"
            >
              复制结果
            </el-button>
          </div>
        </el-card>

        <el-card style="margin-top: 16px">
          <template #header>
            <div class="header-row">
              <span class="card-title">概览历史</span>
              <div style="display:flex; gap:8px;">
                <el-button
                  size="small"
                  :disabled="!predictionHistory.length"
                  @click="exportPredictionHistoryCsv"
                >
                  导出历史概览 CSV
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="!predictionHistory.length"
                  @click="clearPredictionHistory"
                >
                  清空概览历史
                </el-button>
              </div>
            </div>
          </template>
          <el-table
            :data="predictionHistory"
            size="small"
            stripe
          >
            <el-table-column
              prop="time"
              label="时间"
              min-width="170"
            />
            <el-table-column
              prop="risk_score"
              label="概览分数"
              width="110"
            />
            <el-table-column
              prop="risk_level"
              label="业务等级"
              width="90"
            >
              <template #default="{ row }">
                {{ severityFromLevel(row.risk_level) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="severity"
              label="风险强度"
              width="120"
            >
              <template #default="{ row }">
                {{ severityLabelMap[row.severity] || row.severity }}
              </template>
            </el-table-column>
            <el-table-column
              label="审核触发"
              width="100"
            >
              <template #default="{ row }">
                {{ row.warning_generated ? '是' : '否' }}
              </template>
            </el-table-column>
          </el-table>
          <el-empty
            v-if="!predictionHistory.length"
            description="暂无概览历史"
            :image-size="60"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        label="文本概览"
        name="text"
      >
        <el-card>
          <el-form
            :model="textForm"
            label-width="100px"
            style="max-width: 600px"
          >
            <el-form-item label="记录类型">
              <el-select
                v-model="textForm.entry_type"
                style="width: 100%"
              >
                <el-option
                  label="日记"
                  value="diary"
                />
                <el-option
                  label="社交动态"
                  value="social"
                />
                <el-option
                  label="倾诉"
                  value="vent"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="内容">
              <el-input
                v-model="textForm.content"
                type="textarea"
                :rows="6"
                placeholder="请输入你想记录的文字内容..."
                maxlength="500"
                show-word-limit
              />
            </el-form-item>
            <el-form-item label="情绪标签">
              <el-select
                v-model="textForm.emotion_tags"
                multiple
                allow-create
                style="width: 100%"
                placeholder="选择或输入情绪标签"
              >
                <el-option
                  label="焦虑"
                  value="anxiety"
                >
                  <el-tag
                    type="warning"
                    size="small"
                  >
                    焦虑
                  </el-tag>
                </el-option>
                <el-option
                  label="抑郁"
                  value="depression"
                >
                  <el-tag
                    type="danger"
                    size="small"
                  >
                    抑郁
                  </el-tag>
                </el-option>
                <el-option
                  label="愤怒"
                  value="anger"
                >
                  <el-tag
                    type="danger"
                    size="small"
                    effect="light"
                  >
                    愤怒
                  </el-tag>
                </el-option>
                <el-option
                  label="平静"
                  value="calm"
                >
                  <el-tag
                    type="success"
                    size="small"
                  >
                    平静
                  </el-tag>
                </el-option>
                <el-option
                  label="开心"
                  value="happy"
                >
                  <el-tag
                    type="success"
                    size="small"
                    effect="light"
                  >
                    开心
                  </el-tag>
                </el-option>
                <el-option
                  label="悲伤"
                  value="sad"
                >
                  <el-tag
                    type="info"
                    size="small"
                  >
                    悲伤
                  </el-tag>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item label="心情评分">
              <el-rate
                v-model="textForm.mood_score"
                :max="5"
                show-score
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="textSubmitting"
                :disabled="!textForm.content.trim()"
                @click="submitText"
              >
                提交概览
              </el-button>
              <el-button
                v-if="canUsePrediction"
                style="margin-left: 8px"
                type="success"
                :loading="textPredictSubmitting"
                :disabled="!textForm.content.trim()"
                @click="submitTextPredict"
              >
                模型概览
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <Transition name="fade-slide">
          <el-card
            v-if="textResult"
            style="margin-top: 16px"
          >
            <template #header>
              <span class="card-title">分析概览</span>
            </template>
            <el-descriptions
              :column="2"
              border
            >
              <el-descriptions-item label="情感标签">
                <el-tag :type="textResult.sentiment_label === 'negative' ? 'danger' : 'success'">
                  {{ textResult.sentiment_label === 'negative' ? '消极' : '积极' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="情感分数">
                {{ textResult.sentiment_score }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </Transition>

        <Transition name="fade-slide">
          <el-card
            v-if="textPredictResult"
            style="margin-top: 16px"
            class="result-panel"
          >
            <template #header>
              <div class="header-row">
                <span class="card-title">模型概览结果</span>
                <el-tag
                  type="success"
                  effect="light"
                >
                  新训练文本模型
                </el-tag>
              </div>
            </template>
            <el-row
              :gutter="16"
              class="result-grid"
            >
              <el-col :span="12">
                <el-card
                  shadow="never"
                  class="mini-result-card"
                >
                  <template #header>
                    <span class="mini-title">文本概览结果</span>
                  </template>
                  <el-result
                    :icon="textPredictResult.prediction === 1 ? 'warning' : 'success'"
                    :title="textPredictResult.prediction === 1 ? '模型判定为 1（高风险）' : '模型判定为 0（低风险）'"
                  >
                    <template #sub-title>
                      <p>概览概率：{{ (textPredictResult.probability * 100).toFixed(2) }}%</p>
                      <p>情感标签：{{ textPredictResult.sentiment_label || '暂无' }}</p>
                      <p>情感分数：{{ textPredictResult.sentiment_score.toFixed(2) }}</p>
                      <p>模型名称：{{ textPredictResult.model_used }}</p>
                    </template>
                  </el-result>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card
                  shadow="never"
                  class="mini-result-card"
                >
                  <template #header>
                    <span class="mini-title">文本概览详情</span>
                  </template>
                  <el-descriptions
                    :column="1"
                    border
                    size="small"
                  >
                    <el-descriptions-item label="预测标签">
                      {{ textPredictResult.prediction === 1 ? '1（高风险）' : '0（低风险）' }}
                    </el-descriptions-item>
                    <el-descriptions-item label="预测概率">
                      {{ textPredictResult.probability != null ? (textPredictResult.probability * 100).toFixed(2) + '%' : '暂无' }}
                    </el-descriptions-item>
                    <el-descriptions-item label="情感标签">
                      {{ textPredictResult.sentiment_label || '暂无' }}
                    </el-descriptions-item>
                    <el-descriptions-item label="情感分数">
                      {{ textPredictResult.sentiment_score != null ? textPredictResult.sentiment_score.toFixed(2) : '暂无' }}
                    </el-descriptions-item>
                    <el-descriptions-item label="模型名称">
                      {{ textPredictResult.model_used }}
                    </el-descriptions-item>
                  </el-descriptions>
                </el-card>
              </el-col>
            </el-row>
          </el-card>
        </Transition>

        <el-card style="margin-top: 16px">
          <template #header>
            <div class="header-row">
              <span class="card-title">文本概览历史</span>
              <div style="display:flex; gap:8px;">
                <el-button
                  size="small"
                  :disabled="!textPredictionHistory.length"
                  @click="exportTextPredictionHistoryCsv"
                >
                  导出概览历史 CSV
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="!textPredictionHistory.length"
                  @click="clearTextPredictionHistory"
                >
                  清空概览历史
                </el-button>
              </div>
            </div>
          </template>
          <el-table
            :data="textPredictionHistory"
            size="small"
            stripe
          >
            <el-table-column
              prop="time"
              label="时间"
              min-width="170"
            />
            <el-table-column
              prop="content_preview"
              label="文本片段"
              min-width="220"
            />
            <el-table-column
              label="概览结果"
              width="130"
            >
              <template #default="{ row }">
                {{ row.prediction === 1 ? '1（高风险）' : '0（低风险）' }}
              </template>
            </el-table-column>
            <el-table-column
              label="概览概率"
              width="120"
            >
              <template #default="{ row }">
                {{ (row.probability * 100).toFixed(2) }}%
              </template>
            </el-table-column>
            <el-table-column
              prop="model_used"
              label="模型名称"
              min-width="170"
            />
          </el-table>
          <el-empty
            v-if="!textPredictionHistory.length"
            description="暂无文本预测历史"
            :image-size="60"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        label="融合概览"
        name="fusion"
      >
        <el-card>
          <el-form
            :model="fusionForm"
            label-width="120px"
            style="max-width: 760px"
          >
            <el-form-item label="融合文本">
              <el-input
                v-model="fusionForm.text"
                type="textarea"
                :rows="5"
                placeholder="请输入用于融合预测的文本内容"
              />
            </el-form-item>
            <el-form-item label="问卷特征">
              <el-input
                v-model="fusionForm.featuresJson"
                type="textarea"
                :rows="6"
                placeholder="例如 {&quot;age&quot;:20,&quot;stress_level&quot;:3,&quot;sleep_duration&quot;:6}"
              />
            </el-form-item>
            <el-form-item label="生理特征">
              <el-input
                v-model="fusionForm.physiologicalJson"
                type="textarea"
                :rows="6"
                placeholder="例如 {&quot;sleep_hours&quot;:6.5,&quot;heart_rate&quot;:78,&quot;steps&quot;:4200}"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="fusionSubmitting"
                @click="() => submitFusion()"
              >
                一键融合概览
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card
          v-if="fusionResult"
          style="margin-top: 16px"
        >
          <template #header>
            <div class="header-row">
              <span class="card-title">融合概览结果</span>
              <div style="display: flex; gap: 8px;">
                <el-tag
                  v-if="fusionResult.crisis_override"
                  type="danger"
                  effect="dark"
                >
                  危机覆盖
                </el-tag>
                <el-tag
                  v-if="fusionResult.review_required"
                  type="warning"
                  effect="dark"
                >
                  需要复核
                </el-tag>
              </div>
            </div>
          </template>
          <el-result
            :icon="fusionResult.risk_level <= 1 ? 'success' : fusionResult.risk_level <= 2 ? 'warning' : 'error'"
            :title="fusionResult.severity"
          >
            <template #sub-title>
              <p>概览分数：{{ fusionResult.risk_score.toFixed(2) }}</p>
              <p>业务等级：{{ severityFromLevel(fusionResult.risk_level) }}</p>
              <p>模型版本：{{ fusionResult.model_version || '暂无' }}</p>
              <p>模型名称：{{ formatArrayText(fusionResult.model_used, ' / ') }}</p>
            </template>
          </el-result>
          <el-descriptions
            :column="2"
            border
            style="margin-top: 12px"
          >
            <el-descriptions-item label="复核状态">
              {{ fusionResult.review_required ? '需要复核' : '无需复核' }}
            </el-descriptions-item>
            <el-descriptions-item label="危机覆盖">
              {{ fusionResult.crisis_override ? '是' : '否' }}
            </el-descriptions-item>
            <el-descriptions-item label="复核原因" :span="2">
              <el-tag
                v-for="reason in fusionResult.review_triggers"
                :key="reason"
                type="warning"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px"
              >
                {{ reason }}
              </el-tag>
              <span v-if="!fusionResult.review_triggers?.length">暂无</span>
            </el-descriptions-item>
            <el-descriptions-item label="干预等级">
              {{ fusionResult.intervention_level || '暂无' }}
            </el-descriptions-item>
            <el-descriptions-item label="门控权重">
              {{ formatArrayText(fusionResult.fusion_detail?.gate_weights) }}
            </el-descriptions-item>
            <el-descriptions-item
              label="模态得分"
              :span="2"
            >
              {{ fusionResult.fusion_detail?.modality_scores ? JSON.stringify(fusionResult.fusion_detail.modality_scores) : '暂无' }}
            </el-descriptions-item>
            <el-descriptions-item
              label="权重信息"
              :span="2"
            >
              {{ fusionResult.fusion_detail?.weights ? JSON.stringify(fusionResult.fusion_detail.weights) : '暂无' }}
            </el-descriptions-item>
            <el-descriptions-item label="模型名称" :span="2">
              {{ formatArrayText(fusionResult.model_used, ' / ') }}
            </el-descriptions-item>
            <el-descriptions-item label="模型版本" :span="2">
              {{ fusionResult.model_version || '暂无' }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        v-if="canUsePrediction"
        label="模型评估"
        name="experiment"
      >
        <el-card>
          <template #header>
            <div class="header-row">
              <span class="card-title">模型评估面板</span>
              <el-tag type="success">
                HuggingFace Trainer
              </el-tag>
            </div>
          </template>
          <el-row :gutter="16">
            <el-col :span="14">
              <el-form
                :model="experimentForm"
                label-width="120px"
                style="max-width: 720px"
              >
                <el-form-item label="数据集名称">
                  <el-input
                    v-model="experimentForm.dataset_name"
                    placeholder="bert_training_template"
                  />
                </el-form-item>
                <el-form-item label="导入来源">
                  <el-select
                    v-model="experimentForm.source_type"
                    style="width: 100%"
                  >
                    <el-option
                      label="本地文件"
                      value="local"
                    />
                    <el-option
                      label="数据库"
                      value="database"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="训练比例">
                  <el-slider
                    v-model="experimentForm.train_ratio"
                    :min="0.5"
                    :max="0.9"
                    :step="0.05"
                    show-input
                  />
                </el-form-item>
                <el-form-item label="验证比例">
                  <el-slider
                    v-model="experimentForm.val_ratio"
                    :min="0.05"
                    :max="0.3"
                    :step="0.05"
                    show-input
                  />
                </el-form-item>
                <el-form-item label="测试比例">
                  <el-slider
                    v-model="experimentForm.test_ratio"
                    :min="0.05"
                    :max="0.3"
                    :step="0.05"
                    show-input
                  />
                </el-form-item>
                <el-form-item>
                  <el-space wrap>
                    <el-button
                      :loading="experimentLoading && experimentAction === 'import'"
                      @click="importDataset"
                    >
                      导入数据集
                    </el-button>
                    <el-button
                      type="primary"
                      :loading="experimentLoading && experimentAction === 'train'"
                      @click="trainBert"
                    >
                      训练 BERT
                    </el-button>
                    <el-button
                      type="success"
                      :loading="experimentLoading && experimentAction === 'evaluate'"
                      @click="evaluateBert"
                    >
                      验证集概览
                    </el-button>
                    <el-button
                      type="warning"
                      :loading="experimentLoading && experimentAction === 'compare'"
                      @click="compareModels"
                    >
                      对比概览
                    </el-button>
                  </el-space>
                </el-form-item>
                <el-form-item v-if="experimentLoading && experimentProgress > 0">
                  <div class="experiment-progress">
                    <span class="progress-label">{{ experimentActionLabel }}中...</span>
                    <el-progress
                      :percentage="experimentProgress"
                      :status="experimentProgress >= 100 ? 'success' : undefined"
                    />
                  </div>
                </el-form-item>
              </el-form>
            </el-col>
            <el-col :span="10">
              <el-card
                shadow="never"
                class="template-card"
              >
                <template #header>
                  <span class="card-title">标准 CSV 模板说明</span>
                </template>
                <el-alert
                  type="info"
                  :closable="false"
                  show-icon
                  title="至少包含 text 与 label 两列，label 为 0/1 二分类标签。"
                />
                <el-divider />
                <div class="template-path">
                  模板文件：backend/models/datasets/bert_training_template.csv
                </div>
                <ul class="template-list">
                  <li><code>text</code>：用于 BERT 文本输入</li>
                  <li><code>label</code>：0 表示低风险，1 表示高风险</li>
                  <li><code>age</code> / <code>stress_level</code> / <code>sleep_duration</code>：可选辅助特征</li>
                  <li><code>social_support</code>：社会支持得分，可用于扩展实验</li>
                </ul>
              </el-card>
            </el-col>
          </el-row>
        </el-card>
        <el-row
          :gutter="16"
          style="margin-top: 16px"
        >
          <el-col :span="12">
            <el-card v-if="experimentCharts.loss.length || experimentLoading">
              <template #header>
                <span class="card-title">Loss 曲线</span>
              </template>
              <div
                v-if="experimentLoading"
                class="chart-skeleton"
              >
                <el-skeleton
                  :rows="5"
                  animated
                />
              </div>
              <div
                v-else
                ref="lossChartRef"
                class="chart-box"
              />
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card v-if="experimentCharts.accuracy.length || experimentLoading">
              <template #header>
                <span class="card-title">Accuracy 曲线</span>
              </template>
              <div
                v-if="experimentLoading"
                class="chart-skeleton"
              >
                <el-skeleton
                  :rows="5"
                  animated
                />
              </div>
              <div
                v-else
                ref="accuracyChartRef"
                class="chart-box"
              />
            </el-card>
          </el-col>
        </el-row>

        <el-row
          :gutter="16"
          style="margin-top: 16px"
        >
          <el-col :span="14">
            <el-card v-if="experimentCharts.compare.length || experimentLoading">
              <template #header>
                <span class="card-title">模型对比概览图</span>
              </template>
              <div
                v-if="experimentLoading"
                class="chart-skeleton"
              >
                <el-skeleton
                  :rows="5"
                  animated
                />
              </div>
              <div
                v-else
                ref="compareChartRef"
                class="chart-box chart-box-lg"
              />
            </el-card>
          </el-col>
          <el-col :span="10">
            <el-card v-if="experimentCharts.confusion.length || experimentLoading">
              <template #header>
                <span class="card-title">混淆矩阵</span>
              </template>
              <div
                v-if="experimentLoading"
                class="chart-skeleton"
              >
                <el-skeleton
                  :rows="5"
                  animated
                />
              </div>
              <div
                v-else
                ref="confusionChartRef"
                class="chart-box chart-box-lg"
              />
            </el-card>
          </el-col>
        </el-row>

        <el-card
          v-if="experimentRawResult"
          style="margin-top: 16px"
        >
          <template #header>
            <div class="header-row">
              <span class="card-title">评估结果概览</span>
              <el-button
                size="small"
                @click="copyJson({ experimentSummary, confusionMatrix, evalLogRows, trainLogRows })"
              >
                复制结果
              </el-button>
            </div>
          </template>
          <el-descriptions
            v-if="experimentSummary"
            :column="2"
            border
          >
            <el-descriptions-item label="训练损失">
              {{ experimentSummary.train_loss }}
            </el-descriptions-item>
            <el-descriptions-item label="验证损失">
              {{ experimentSummary.val_loss }}
            </el-descriptions-item>
            <el-descriptions-item label="验证准确率">
              {{ experimentSummary.val_accuracy }}
            </el-descriptions-item>
            <el-descriptions-item label="模型状态">
              {{ experimentSummary.status || 'completed' }}
            </el-descriptions-item>
          </el-descriptions>
          <div
            v-if="trainLogRows.length || evalLogRows.length"
            class="log-viewer-grid"
          >
            <el-card
              v-if="trainLogRows.length"
              shadow="never"
              class="log-viewer-card"
            >
              <template #header>
                <div class="header-row">
                  <span class="card-title">训练日志查看器</span>
                  <div class="log-actions">
                    <el-input
                      v-model="trainLogFilter"
                      size="small"
                      placeholder="过滤日志..."
                      clearable
                      style="width: 140px"
                    />
                    <el-button
                      size="small"
                      @click="copyJson(trainLogRows)"
                    >
                      复制日志
                    </el-button>
                  </div>
                </div>
              </template>
              <el-scrollbar height="220px">
                <el-table
                  :data="filteredTrainLogRows"
                  size="small"
                  stripe
                >
                  <el-table-column
                    prop="epoch"
                    label="Epoch"
                    width="80"
                  />
                  <el-table-column
                    prop="loss"
                    label="Loss"
                    width="100"
                  />
                  <el-table-column
                    prop="eval_loss"
                    label="Eval Loss"
                    width="100"
                  />
                  <el-table-column
                    prop="eval_f1"
                    label="Eval F1"
                    width="100"
                  />
                  <el-table-column
                    prop="eval_accuracy"
                    label="Eval Acc"
                    width="100"
                  />
                  <el-table-column
                    prop="learning_rate"
                    label="LR"
                    width="120"
                  />
                </el-table>
              </el-scrollbar>
            </el-card>
            <el-card
              v-if="evalLogRows.length"
              shadow="never"
              class="log-viewer-card"
            >
              <template #header>
                <div class="header-row">
                  <span class="card-title">概览日志查看器</span>
                  <div class="log-actions">
                    <el-input
                      v-model="evalLogFilter"
                      size="small"
                      placeholder="过滤日志..."
                      clearable
                      style="width: 140px"
                    />
                    <el-button
                      size="small"
                      @click="copyJson(evalLogRows)"
                    >
                      复制日志
                    </el-button>
                  </div>
                </div>
              </template>
              <el-scrollbar height="220px">
                <el-table
                  :data="filteredEvalLogRows"
                  size="small"
                  stripe
                >
                  <el-table-column
                    prop="split"
                    label="Split"
                    width="100"
                  />
                  <el-table-column
                    prop="sample_count"
                    label="样本数"
                    width="90"
                  />
                  <el-table-column
                    prop="accuracy"
                    label="Acc"
                    width="90"
                  />
                  <el-table-column
                    prop="precision"
                    label="Prec"
                    width="90"
                  />
                  <el-table-column
                    prop="recall"
                    label="Recall"
                    width="90"
                  />
                  <el-table-column
                    prop="f1"
                    label="F1"
                    width="90"
                  />
                  <el-table-column
                    prop="auc"
                    label="AUC"
                    width="90"
                  />
                </el-table>
              </el-scrollbar>
            </el-card>
          </div>
        </el-card>

        <el-card
          v-if="filteredMisclassifiedRows.length"
          style="margin-top: 16px"
        >
          <template #header>
            <div class="header-row">
              <span class="card-title">误判样本概览</span>
              <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <el-select
                  v-model="misclassifiedTrueLabel"
                  size="small"
                  clearable
                  placeholder="真实标签"
                  style="width: 110px"
                >
                  <el-option
                    label="真实 0"
                    :value="0"
                  />
                  <el-option
                    label="真实 1"
                    :value="1"
                  />
                </el-select>
                <el-select
                  v-model="misclassifiedPredLabel"
                  size="small"
                  clearable
                  placeholder="预测标签"
                  style="width: 110px"
                >
                  <el-option
                    label="预测 0"
                    :value="0"
                  />
                  <el-option
                    label="预测 1"
                    :value="1"
                  />
                </el-select>
                <el-select
                  v-model="misclassifiedScoreRange"
                  size="small"
                  clearable
                  placeholder="概率区间"
                  style="width: 130px"
                >
                  <el-option
                    label="0.0 - 0.3"
                    value="0-30"
                  />
                  <el-option
                    label="0.3 - 0.6"
                    value="30-60"
                  />
                  <el-option
                    label="0.6 - 0.8"
                    value="60-80"
                  />
                  <el-option
                    label="0.8 - 1.0"
                    value="80-100"
                  />
                </el-select>
                <el-input
                  v-model="misclassifiedSearchText"
                  size="small"
                  placeholder="按标签/概率/索引筛选"
                  clearable
                  style="width: 180px"
                />
                <el-button
                  size="small"
                  type="primary"
                  plain
                  @click="exportSampleCsv('misclassified')"
                >
                  导出当前结果 CSV
                </el-button>
              </div>
            </div>
          </template>
          <el-table
            :data="pagedMisclassifiedRows"
            size="small"
            stripe
            max-height="320"
          >
            <el-table-column
              prop="index"
              label="#"
              width="70"
            />
            <el-table-column
              prop="true_label"
              label="真实标签"
              width="100"
            />
            <el-table-column
              prop="pred_label"
              label="预测标签"
              width="100"
            />
            <el-table-column
              prop="score"
              label="概率"
              width="100"
            />
          </el-table>
          <div class="table-footer">
            <el-pagination
              v-model:current-page="misclassifiedCurrentPage"
              v-model:page-size="misclassifiedPageSize"
              small
              background
              layout="prev, pager, next, sizes, total"
              :total="filteredMisclassifiedRows.length"
              :page-sizes="[5, 10, 20]"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        label="生理概览"
        name="physiological"
      >
        <el-card>
          <el-form
            :model="physioForm"
            label-width="120px"
            style="max-width: 600px"
          >
            <el-form-item label="数据来源">
              <el-select
                v-model="physioForm.source"
                style="width: 100%"
              >
                <el-option
                  label="手动录入"
                  value="manual"
                />
                <el-option
                  label="可穿戴设备"
                  value="wearable"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="睡眠时长(h)">
              <el-input-number
                v-model="physioForm.sleep_hours"
                :min="0"
                :max="24"
                :step="0.5"
              />
              <span class="field-hint">成年人建议 7-9 小时</span>
            </el-form-item>
            <el-form-item label="睡眠质量">
              <el-rate
                v-model="physioForm.sleep_quality"
                :max="5"
                show-score
              />
              <span class="field-hint">1-5 分，5 分表示睡眠质量最好</span>
            </el-form-item>
            <el-form-item label="运动时长(min)">
              <el-input-number
                v-model="physioForm.exercise_minutes"
                :min="0"
                :max="480"
                :step="5"
              />
              <span class="field-hint">建议每日 30-60 分钟</span>
            </el-form-item>
            <el-form-item label="心率(bpm)">
              <el-input-number
                v-model="physioForm.heart_rate"
                :min="30"
                :max="220"
              />
              <span class="field-hint">正常静息心率 60-100 bpm</span>
            </el-form-item>
            <el-form-item label="收缩压">
              <el-input-number
                v-model="physioForm.systolic_bp"
                :min="60"
                :max="250"
              />
              <span class="field-hint">正常范围 90-120 mmHg</span>
            </el-form-item>
            <el-form-item label="舒张压">
              <el-input-number
                v-model="physioForm.diastolic_bp"
                :min="40"
                :max="150"
              />
              <span class="field-hint">正常范围 60-80 mmHg</span>
            </el-form-item>
            <el-form-item label="步数">
              <el-input-number
                v-model="physioForm.steps"
                :min="0"
                :max="100000"
                :step="100"
              />
              <span class="field-hint">建议每日 8000-10000 步</span>
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="physioSubmitting"
                @click="submitPhysio"
              >
                提交记录
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card style="margin-top: 16px">
          <template #header>
            <div class="header-row">
              <span class="card-title">生理概览历史</span>
              <div style="display:flex; gap:8px;">
                <el-button
                  size="small"
                  :disabled="!physioHistory.length"
                  @click="exportPhysioHistoryCsv"
                >
                  导出生理概览 CSV
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="!physioHistory.length"
                  @click="clearPhysioHistory"
                >
                  清空概览历史
                </el-button>
              </div>
            </div>
          </template>
          <el-table
            :data="physioHistoryWithTrend"
            size="small"
            stripe
          >
            <el-table-column
              prop="time"
              label="时间"
              min-width="170"
            />
            <el-table-column
              label="睡眠(h)"
              width="110"
            >
              <template #default="{ row }">
                <span>{{ row.sleep_hours }}</span>
                <TrendArrow
                  :value="row.sleep_hours"
                  :prev="row.prev_sleep_hours"
                />
              </template>
            </el-table-column>
            <el-table-column
              prop="sleep_quality"
              label="睡眠质量"
              width="90"
            />
            <el-table-column
              label="运动(min)"
              width="120"
            >
              <template #default="{ row }">
                <span>{{ row.exercise_minutes }}</span>
                <TrendArrow
                  :value="row.exercise_minutes"
                  :prev="row.prev_exercise_minutes"
                />
              </template>
            </el-table-column>
            <el-table-column
              label="心率"
              width="110"
            >
              <template #default="{ row }">
                <span>{{ row.heart_rate }}</span>
                <TrendArrow
                  :value="row.heart_rate"
                  :prev="row.prev_heart_rate"
                />
              </template>
            </el-table-column>
            <el-table-column
              prop="systolic_bp"
              label="收缩压"
              width="90"
            />
            <el-table-column
              prop="diastolic_bp"
              label="舒张压"
              width="90"
            />
            <el-table-column
              label="步数"
              min-width="120"
            >
              <template #default="{ row }">
                <span>{{ row.steps }}</span>
                <TrendArrow
                  :value="row.steps"
                  :prev="row.prev_steps"
                />
              </template>
            </el-table-column>
          </el-table>
          <el-empty
            v-if="!physioHistory.length"
            description="暂无生理概览历史"
            :image-size="60"
          />
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>

  <!-- 危机预警弹窗 -->
  <el-dialog
    v-model="crisisDialogVisible"
    title="危机预警"
    width="500px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    align-center
    destroy-on-close
  >
    <div class="crisis-alert-content">
      <el-result
        icon="error"
        title="检测到危机表达"
        sub-title="系统检测到文本中包含可能的自伤或自杀相关表达，请立即关注。"
      />
      <el-alert
        type="error"
        :closable="false"
        show-icon
      >
        <template #title>
          <strong>如果您正处于危机中，请立即寻求帮助：</strong>
        </template>
      </el-alert>
      <div class="crisis-hotlines">
        <div class="hotline-item">
          <el-icon><PhoneFilled /></el-icon>
          <div class="hotline-info">
            <div class="hotline-name">全国24小时心理援助热线</div>
            <div class="hotline-number">400-161-9995</div>
          </div>
        </div>
        <div class="hotline-item">
          <el-icon><PhoneFilled /></el-icon>
          <div class="hotline-info">
            <div class="hotline-name">北京心理危机研究与干预中心</div>
            <div class="hotline-number">010-82951332</div>
          </div>
        </div>
        <div class="hotline-item">
          <el-icon><PhoneFilled /></el-icon>
          <div class="hotline-info">
            <div class="hotline-name">生命热线</div>
            <div class="hotline-number">400-821-1215</div>
          </div>
        </div>
      </div>
      <el-alert
        type="warning"
        :closable="false"
        style="margin-top: 12px"
      >
        <template #title>
          您也可以联系身边的亲友、老师或学校心理咨询中心获取帮助。
        </template>
      </el-alert>
    </div>
    <template #footer>
      <el-button
        type="primary"
        size="large"
        @click="crisisDialogVisible = false"
      >
        我已了解，继续浏览
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules, ProgressColor } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Top, Bottom, ArrowDown, PhoneFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import TrendArrow from '@/components/common/TrendArrow.vue'
import { userApi } from '@/api/userApi'
import { modelApi, type ModelPredictResponse, type RiskTrend, type TextPredictModelResult, type CompareResult, type EvaluateResult, type TrainResult, type FusionPredictResult } from '@/api/modelApi'
import type { ReportFactor, RiskReport, StructuredCollectResult, TextAnalyzeResult } from '@/api/userRiskApi'
import { useAuthStore } from '@/stores/auth'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { hasPermission } from '@/types/permission'
import { sanitizeCellForExcel } from '@/utils/exportUtils'
import {
  featureLabelMap,
  severityLabelMap,
  modalityLabelMap,
  severityFromLevel,
  routeFamilyLabel,
  routeFamilyTagType,
  routeReasonLabel,
  confidenceTagType,
  confidenceLabel,
  getFactorDirectionLabel,
  getFactorDirectionTagType,
  formatArrayText,
} from '@/utils/riskFormatters'

const activeTab = ref('report')
const crisisDialogVisible = ref(false)
const showPredictionFeatures = computed(() => hasPermission(auth.role, 'user.predict.use'))
const canUsePrediction = computed(() => showPredictionFeatures.value)
const showCrisisDialog = () => {
  crisisDialogVisible.value = true
}
const canExportRisk = computed(() => hasPermission(auth.role, 'user.export.risk'))

const report = ref<RiskReport | null>(null)
const reportLoading = ref(true)
const reportError = ref('')
const reportTrendRef = ref<HTMLElement>()
let reportTrendChart: echarts.ECharts | null = null
const handleReportTrendResize = () => reportTrendChart?.resize()
const disposeReportTrend = () => {
  window.removeEventListener('resize', handleReportTrendResize)
  reportTrendChart?.dispose()
  reportTrendChart = null
}

const lossChartRef = ref<HTMLElement>()
const accuracyChartRef = ref<HTMLElement>()
const compareChartRef = ref<HTMLElement>()
const confusionChartRef = ref<HTMLElement>()
let lossChart: echarts.ECharts | null = null
let accuracyChart: echarts.ECharts | null = null
let compareChart: echarts.ECharts | null = null
let confusionChart: echarts.ECharts | null = null
// 组件级标志位: 确保 resize 监听器只注册一次, 避免 renderExperimentCharts 多次调用导致重复绑定
let experimentResizeRegistered = false

const experimentCharts = reactive({
  loss: [] as number[],
  accuracy: [] as number[],
  compare: [] as Array<{ model_name: string; accuracy: number; precision: number; recall: number; f1: number; auc: number }>,
  confusion: [] as number[][]
})

const disposeExperimentCharts = () => {
  window.removeEventListener('resize', handleExperimentResize)
  experimentResizeRegistered = false
  lossChart?.dispose(); lossChart = null
  accuracyChart?.dispose(); accuracyChart = null
  compareChart?.dispose(); compareChart = null
  confusionChart?.dispose(); confusionChart = null
}

const handleExperimentResize = () => {
  lossChart?.resize()
  accuracyChart?.resize()
  compareChart?.resize()
  confusionChart?.resize()
}

// TD-022 修复：featureLabelMap, severityLabelMap, modalityLabelMap,
// severityFromLevel, routeFamilyLabel, routeFamilyTagType, routeReasonLabel,
// confidenceTagType, confidenceLabel, getFactorDirectionLabel,
// getFactorDirectionTagType, formatArrayText
// 已提取到 @/utils/riskFormatters.ts

const severityLabel = computed(() => {
  if (!report.value) return ''
  return severityLabelMap[report.value.severity] || report.value.severity
})

const severityTagType = computed(() => {
  if (!report.value) return 'info'
  const map: Record<string, string> = { none: 'info', mild: 'success', moderate: 'warning', high: 'danger', critical: 'danger' }
  return (map[report.value.severity] || 'info') as 'info' | 'success' | 'warning' | 'danger'
})

const scoreColor = computed((): string | ProgressColor[] => {
  if (!report.value) return '#67c23a'
  const s = report.value.risk_score
  if (s <= 20) return [{ color: '#67c23a', percentage: 0 }, { color: '#95d475', percentage: 100 }]
  if (s <= 40) return [{ color: '#e6a23c', percentage: 0 }, { color: '#f0c78a', percentage: 100 }]
  if (s <= 60) return [{ color: '#f56c6c', percentage: 0 }, { color: '#fab6b6', percentage: 100 }]
  return [{ color: '#c45656', percentage: 0 }, { color: '#f56c6c', percentage: 100 }]
})

const loadReport = async () => {
  reportLoading.value = true
  reportError.value = ''
  try {
    report.value = await modelApi.getRiskReport()
  } catch (error) {
    reportError.value = normalizeHttpError(error, '风险报告加载失败').detail
  } finally {
    reportLoading.value = false
    await nextTick()
    if (report.value) {
      await renderReportTrend()
    }
  }
}

const renderReportTrend = async () => {
  await nextTick()
  if (!reportTrendRef.value) return

  let trend: RiskTrend = { days: 30, direction: 'stable', points: [] }
  try {
    trend = await modelApi.getRiskTrend(30)
  } catch (error) {
    console.warn('风险趋势接口调用失败，使用空趋势图占位', error)
  }

  // ECharts 在同一 DOM 上重复 init 时会复用旧实例，先销毁再重建可以避免 tooltip、缩放和 resize 事件状态错乱。
  if (!reportTrendChart) {
    reportTrendChart = echarts.init(reportTrendRef.value)
    window.addEventListener('resize', handleReportTrendResize)
  } else {
    // 重新初始化前先销毁，避免状态混乱
    disposeReportTrend()
    reportTrendChart = echarts.init(reportTrendRef.value)
    window.addEventListener('resize', handleReportTrendResize)
  }

  const points = Array.isArray(trend.points) ? trend.points : []
  const dates = points.map(p => p.date)
  const valueOrNull = (value: number | null | undefined) => typeof value === 'number' ? value : null
  const sourceLabelMap: Record<string, string> = { fusion: '融合评估', structured: '结构化评估', text: '文本分析', physiological: '生理数据' }
  const riskLevelMap: Record<number, string> = { 0: '无风险', 1: '低风险', 2: '中风险', 3: '高风险', 4: '严重风险' }

  reportTrendChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params as Array<{ dataIndex: number; marker: string; seriesName: string; value: number | null }> : []
        const point = points[items[0]?.dataIndex ?? 0]
        if (!point) return ''
        const lines = [
          `<strong>${point.date}</strong>`,
          `主评估：${sourceLabelMap[String(point.assessment_type || '')] || point.assessment_type || '未知'}`,
          `风险等级：${riskLevelMap[point.risk_level] || `等级 ${point.risk_level}`}`,
          `当日记录：${point.record_count ?? 1} 条`,
        ]
        items.forEach(item => {
          if (item.value !== null && item.value !== undefined) {
            lines.push(`${item.marker}${item.seriesName}：${Number(item.value).toFixed(2)}`)
          }
        })
        return lines.join('<br/>')
      }
    },
    legend: { top: 0, data: ['综合风险', '结构化风险', '文本风险', '生理风险'], textStyle: { fontSize: 11 } },
    grid: { left: 40, right: 20, top: 42, bottom: 30 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 11 } },
    graphic: points.length
      ? []
      : [{
          type: 'text',
          left: 'center',
          top: 'middle',
          style: {
            text: '暂无趋势数据，请先完成一次评估',
            fill: '#909399',
            fontSize: 14
          }
        }],
    series: [
      {
        name: '综合风险', type: 'line', data: points.map(p => p.risk_score), smooth: true,
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64,158,255,0.3)' }, { offset: 1, color: 'rgba(64,158,255,0.02)' }
        ]) },
        lineStyle: { color: '#409eff', width: 2 }, itemStyle: { color: '#409eff' }
      },
      { name: '结构化风险', type: 'line', data: points.map(p => valueOrNull(p.structured_score)), smooth: true, connectNulls: true, lineStyle: { color: '#67c23a', width: 1.8 }, itemStyle: { color: '#67c23a' } },
      { name: '文本风险', type: 'line', data: points.map(p => valueOrNull(p.text_score)), smooth: true, connectNulls: true, lineStyle: { color: '#e6a23c', width: 1.8 }, itemStyle: { color: '#e6a23c' } },
      { name: '生理风险', type: 'line', data: points.map(p => valueOrNull(p.physiological_score)), smooth: true, connectNulls: true, lineStyle: { color: '#f56c6c', width: 1.8 }, itemStyle: { color: '#f56c6c' } },
    ]
  })
}

const structuredFormRef = ref<FormInstance>()
const structuredForm = reactive({
  identity_type: 'student' as 'student' | 'worker',
  age: 20,
  gender: 1,
  study_year: 2 as number | null,
  cgpa: 3.0,
  stress_level: 2,
  sleep_duration: 7,
  social_support: 3,
  financial_pressure: 2,
  family_history: 0,
  academic_pressure: 2,
  exercise_frequency: 3,
  anxiety: 1,
  panic_attack: 0,
  treatment_seeking: 0
})

const structuredRules: FormRules = {
  identity_type: [{ required: true, message: '请选择当前身份', trigger: 'change' }],
  age: [{ required: true, type: 'number', min: 15, max: 60, message: '年龄需在 15~60 之间', trigger: 'change' }],
  gender: [{ required: true, type: 'number', message: '请选择性别', trigger: 'change' }],
  study_year: [
    {
      validator: (_rule, value, callback) => {
        if (structuredForm.identity_type !== 'student') {
          callback()
          return
        }
        if (typeof value !== 'number' || Number.isNaN(value)) {
          callback(new Error('在校学生需填写年级'))
          return
        }
        if (value < 1 || value > 6) {
          callback(new Error('年级需在 1~6 之间'))
          return
        }
        callback()
      },
      trigger: 'change'
    }
  ],
  cgpa: [{ required: true, type: 'number', min: 0, max: 10, message: 'GPA需在 0~10 之间', trigger: 'change' }],
  stress_level: [{ required: true, type: 'number', min: 0, max: 5, message: '压力分值需在 0~5 之间', trigger: 'change' }],
  sleep_duration: [{ required: true, type: 'number', min: 0, max: 12, message: '睡眠时长需在 0~12 小时之间', trigger: 'change' }],
  social_support: [{ required: true, type: 'number', min: 0, max: 5, message: '社会支持分值需在 0~5 之间', trigger: 'change' }],
  financial_pressure: [{ required: true, type: 'number', min: 0, max: 5, message: '经济压力分值需在 0~5 之间', trigger: 'change' }],
  family_history: [{ required: true, type: 'number', message: '请选择家族史', trigger: 'change' }],
  academic_pressure: [{ required: true, type: 'number', min: 0, max: 5, message: '学业压力分值需在 0~5 之间', trigger: 'change' }],
  exercise_frequency: [{ required: true, type: 'number', min: 0, max: 7, message: '运动频率需在 0~7 之间', trigger: 'change' }],
  anxiety: [{ required: true, type: 'number', min: 0, max: 5, message: '焦虑程度需在 0~5 之间', trigger: 'change' }],
  panic_attack: [{ required: true, type: 'number', message: '请选择恐慌发作', trigger: 'change' }],
  treatment_seeking: [{ required: true, type: 'number', message: '请选择寻求治疗', trigger: 'change' }]
}

const auth = useAuthStore()

const historyKey = (base: string) => `${base}_u${auth.user?.id ?? 0}`
// 按用户隔离本地历史记录，避免同一浏览器切换账号后看到上一位用户的数据。
const PREDICTION_HISTORY_KEY = historyKey('prediction_history_v1')
const TEXT_PREDICTION_HISTORY_KEY = historyKey('text_prediction_history_v1')
const PHYSIO_HISTORY_KEY = historyKey('physio_history_v1')
const predictionHistory = ref<Array<StructuredCollectResult & { time: string }>>([])
const textPredictionHistory = ref<Array<TextPredictModelResult & { time: string; content_preview: string }>>([])
const physioHistory = ref<Array<{ time: string; sleep_hours: number; sleep_quality: number; exercise_minutes: number; heart_rate: number; systolic_bp: number; diastolic_bp: number; steps: number }>>([])

const physioHistoryWithTrend = computed(() => {
  return physioHistory.value.map((item, index) => {
    const prev = physioHistory.value[index + 1]
    return {
      ...item,
      prev_sleep_hours: prev?.sleep_hours ?? null,
      prev_exercise_minutes: prev?.exercise_minutes ?? null,
      prev_heart_rate: prev?.heart_rate ?? null,
      prev_steps: prev?.steps ?? null
    }
  })
})

const loadPredictionHistory = () => {
  try {
    const raw = localStorage.getItem(PREDICTION_HISTORY_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      predictionHistory.value = parsed
    }
  } catch {
    predictionHistory.value = []
  }
}

const savePredictionHistory = () => {
  localStorage.setItem(PREDICTION_HISTORY_KEY, JSON.stringify(predictionHistory.value.slice(0, 20)))
}

const loadTextPredictionHistory = () => {
  try {
    const raw = localStorage.getItem(TEXT_PREDICTION_HISTORY_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      textPredictionHistory.value = parsed
    }
  } catch {
    textPredictionHistory.value = []
  }
}

const saveTextPredictionHistory = () => {
  localStorage.setItem(TEXT_PREDICTION_HISTORY_KEY, JSON.stringify(textPredictionHistory.value.slice(0, 20)))
}

const loadPhysioHistory = () => {
  try {
    const raw = localStorage.getItem(PHYSIO_HISTORY_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      physioHistory.value = parsed
    }
  } catch {
    physioHistory.value = []
  }
}

const savePhysioHistory = () => {
  localStorage.setItem(PHYSIO_HISTORY_KEY, JSON.stringify(physioHistory.value.slice(0, 20)))
}

const clearPredictionHistory = () => {
  predictionHistory.value = []
  localStorage.removeItem(PREDICTION_HISTORY_KEY)
  ElMessage.success('预测历史已清空')
}

const clearTextPredictionHistory = () => {
  textPredictionHistory.value = []
  localStorage.removeItem(TEXT_PREDICTION_HISTORY_KEY)
  ElMessage.success('文本预测历史已清空')
}

const clearPhysioHistory = () => {
  physioHistory.value = []
  localStorage.removeItem(PHYSIO_HISTORY_KEY)
  ElMessage.success('生理记录历史已清空')
}

const exportPhysioHistoryCsv = () => {
  if (!physioHistory.value.length) {
    ElMessage.warning('暂无可导出的生理数据历史')
    return
  }

  const headers = ['时间', '睡眠时长(h)', '睡眠质量', '运动时长(min)', '心率(bpm)', '收缩压', '舒张压', '步数']
  const rows = physioHistory.value.map((row) => [
    row.time,
    row.sleep_hours,
    row.sleep_quality,
    row.exercise_minutes,
    row.heart_rate,
    row.systolic_bp,
    row.diastolic_bp,
    row.steps
  ])

  const csv = [headers, ...rows]
    // P1-FE-007 修复：对每个单元格调用 sanitizeCellForExcel 防止 CSV 公式注入
    .map((line) => line.map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `physio_history_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('生理数据历史 CSV 已导出')
}

const exportPredictionHistoryCsv = () => {
  if (!predictionHistory.value.length) {
    ElMessage.warning('暂无可导出的预测历史')
    return
  }

  const headers = ['时间', '风险分数', '风险等级(业务)', '严重程度', '预警触发']
  const rows = predictionHistory.value.map((row) => [
    row.time,
    row.risk_score,
    row.risk_level,
    row.severity,
    row.warning_generated ? '是' : '否'
  ])

  const csv = [headers, ...rows]
    // P1-FE-007 修复：对每个单元格调用 sanitizeCellForExcel 防止 CSV 公式注入
    .map((line) => line.map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `prediction_history_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('预测历史 CSV 已导出')
}

const exportTextPredictionHistoryCsv = () => {
  if (!textPredictionHistory.value.length) {
    ElMessage.warning('暂无可导出的文本预测历史')
    return
  }

  const headers = ['时间', '文本片段', 'prediction(0/1)', 'probability(%)', 'sentiment_label', 'sentiment_score', 'model_used']
  const rows = textPredictionHistory.value.map((row) => [
    row.time,
    row.content_preview,
    row.prediction,
    (row.probability * 100).toFixed(2),
    row.sentiment_label,
    row.sentiment_score != null ? row.sentiment_score.toFixed(2) : '',
    row.model_used
  ])

  const csv = [headers, ...rows]
    .map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `text_prediction_history_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('文本预测历史 CSV 已导出')
}

const structuredSubmitting = ref(false)
const structuredResult = ref<StructuredCollectResult | null>(null)
const modelTabResult = ref<ModelPredictResponse | null>(null)
const structuredMode = ref<'single' | 'stepper'>('single')
const structuredStep = ref(0)
const structuredStepFormRef = ref<FormInstance>()

const handleStepNext = async () => {
  const formRef = structuredMode.value === 'stepper' ? structuredStepFormRef.value : structuredFormRef.value
  if (!formRef) return

  const stepFields: Record<number, string[]> = {
    0: ['identity_type', 'age', 'gender', 'study_year'],
    1: ['cgpa', 'academic_pressure', 'financial_pressure'],
    2: ['sleep_duration', 'exercise_frequency', 'social_support'],
    3: ['stress_level', 'anxiety', 'family_history', 'panic_attack', 'treatment_seeking']
  }

  const fields = stepFields[structuredStep.value] || []
  const valid = await formRef.validateField(fields).catch(() => false)
  if (valid) {
    structuredStep.value++
  } else {
    ElMessage.warning('请完善当前步骤的信息后再继续')
  }
}

const submitStructured = async () => {
  // 结构化评估要先走前端校验，再拼装后端需要的数值型 payload，避免后端反复做格式修正。
  const formRef = structuredMode.value === 'stepper' ? structuredStepFormRef.value : structuredFormRef.value
  const valid = await formRef?.validate().catch(() => false)
  if (!valid) {
    ElMessage.warning('请先修正字段范围后再评估')
    return
  }

  structuredSubmitting.value = true
  try {
    const dataPayload: Record<string, number | string> = {
      age: structuredForm.age,
      gender: structuredForm.gender,
      cgpa: structuredForm.cgpa,
      stress_level: structuredForm.stress_level,
      sleep_duration: structuredForm.sleep_duration,
      social_support: structuredForm.social_support,
      financial_pressure: structuredForm.financial_pressure,
      family_history: structuredForm.family_history,
      academic_pressure: structuredForm.academic_pressure,
      exercise_frequency: structuredForm.exercise_frequency,
      anxiety: structuredForm.anxiety,
      panic_attack: structuredForm.panic_attack,
      treatment_seeking: structuredForm.treatment_seeking,
      identity_type: structuredForm.identity_type,
      is_student: structuredForm.identity_type === 'student' ? 1 : 0
    }

    if (structuredForm.identity_type === 'student' && typeof structuredForm.study_year === 'number') {
      dataPayload.study_year = structuredForm.study_year
    }

    try {
      modelTabResult.value = await modelApi.predictTabularModel(dataPayload)
    } catch (error) {
      modelTabResult.value = null
      console.warn('结构化模型预测接口调用失败，继续保存评估结果', error)
    }

    const result = await userApi.collectStructuredData({
      assessment_type: 'comprehensive',
      data_payload: dataPayload
    })
    structuredResult.value = result

    predictionHistory.value.unshift({
      ...result,
      time: new Date().toLocaleString()
    })
    savePredictionHistory()

    await loadReport()
    activeTab.value = 'report'

    autoFusionReady.structured = true
    await maybeAutoSubmitFusion()

    if (modelTabResult.value) {
      ElMessage.success('结构化评估完成，风险报告已更新')
    } else {
      ElMessage.success('结构化评估已保存，模型预测详情暂不可用')
    }
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '结构化评估失败').detail)
  } finally {
    structuredSubmitting.value = false
  }
}

const textForm = reactive({
  entry_type: 'diary', content: '', emotion_tags: [] as string[], mood_score: 3
})
const textSubmitting = ref(false)
const textPredictSubmitting = ref(false)
const textResult = ref<TextAnalyzeResult | null>(null)
const textPredictResult = ref<TextPredictModelResult | null>(null)

const submitText = async () => {
  if (!textForm.content.trim()) return
  // 文本分析会同时写入“分析结果历史”和“模型预测历史”，这里统一补记录，保证用户切换标签页后还能看到上下文。
  textSubmitting.value = true
  try {
    textResult.value = await userApi.analyzeText({
      entry_type: textForm.entry_type,
      content: textForm.content,
      emotion_tags: textForm.emotion_tags,
      mood_score: textForm.mood_score
    })

    // 提交分析后也补充一条文本历史记录，避免“提交后无历史”
    textPredictionHistory.value.unshift({
      prediction: textResult.value.sentiment_label === 'negative' ? 1 : 0,
      probability: Math.min(Math.max(textResult.value.sentiment_score, 0), 1),
      sentiment_label: textResult.value.sentiment_label,
      sentiment_score: textResult.value.sentiment_score,
      model_used: 'text_analyze',
      time: new Date().toLocaleString(),
      content_preview: textForm.content.trim().slice(0, 60)
    })
    saveTextPredictionHistory()

    autoFusionReady.text = true
    await maybeAutoSubmitFusion()

    ElMessage.success('分析完成')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '文本分析失败').detail)
  } finally {
    textSubmitting.value = false
  }
}

const submitTextPredict = async () => {
  if (!textForm.content.trim()) return
  textPredictSubmitting.value = true
  try {
    textPredictResult.value = await modelApi.predictTextModel(textForm.content)

    textPredictionHistory.value.unshift({
      ...textPredictResult.value,
      time: new Date().toLocaleString(),
      content_preview: textForm.content.trim().slice(0, 60)
    })
    textPredictionHistory.value = textPredictionHistory.value.map(item => ({
      ...item,
      model_used: item.model_used || 'text_depression_model'
    }))
    saveTextPredictionHistory()

    ElMessage.success('文本模型预测完成')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '文本模型预测失败').detail)
  } finally {
    textPredictSubmitting.value = false
  }
}

const fusionForm = reactive({
  text: '',
  featuresJson: '{"age":20,"stress_level":3,"sleep_duration":6}',
  physiologicalJson: '{"sleep_hours":6.5,"heart_rate":78,"steps":4200}'
})
const fusionSubmitting = ref(false)
const fusionResult = ref<FusionPredictResult | null>(null)
const autoFusionReady = reactive({
  structured: false,
  text: false,
  physiological: false,
})

const syncFusionInputsFromLatest = () => {
  fusionForm.text = textForm.content.trim()

  const structuredFeatures: Record<string, number | string> = {
    age: structuredForm.age,
    gender: structuredForm.gender,
    cgpa: structuredForm.cgpa,
    stress_level: structuredForm.stress_level,
    sleep_duration: structuredForm.sleep_duration,
    social_support: structuredForm.social_support,
    financial_pressure: structuredForm.financial_pressure,
    family_history: structuredForm.family_history,
    academic_pressure: structuredForm.academic_pressure,
    exercise_frequency: structuredForm.exercise_frequency,
    anxiety: structuredForm.anxiety,
    panic_attack: structuredForm.panic_attack,
    treatment_seeking: structuredForm.treatment_seeking,
    identity_type: structuredForm.identity_type,
    is_student: structuredForm.identity_type === 'student' ? 1 : 0,
  }

  if (structuredForm.identity_type === 'student' && typeof structuredForm.study_year === 'number') {
    structuredFeatures.study_year = structuredForm.study_year
  }

  fusionForm.featuresJson = JSON.stringify(structuredFeatures)
  fusionForm.physiologicalJson = JSON.stringify({
    sleep_hours: physioForm.sleep_hours,
    sleep_quality: physioForm.sleep_quality,
    exercise_minutes: physioForm.exercise_minutes,
    heart_rate: physioForm.heart_rate,
    systolic_bp: physioForm.systolic_bp,
    diastolic_bp: physioForm.diastolic_bp,
    steps: physioForm.steps,
  })
}

const maybeAutoSubmitFusion = async () => {
  if (!autoFusionReady.structured || !autoFusionReady.text || !autoFusionReady.physiological) return
  if (fusionSubmitting.value) return
  syncFusionInputsFromLatest()
  await submitFusion(true)
}

const experimentForm = reactive({
  dataset_name: 'depression_multimodal_v1',
  source_type: 'local',
  train_ratio: 0.7,
  val_ratio: 0.15,
  test_ratio: 0.15
})
const experimentLoading = ref(false)
const experimentAction = ref<'import' | 'train' | 'evaluate' | 'compare'>('train')
const experimentProgress = ref(0)
const experimentRawResult = ref<string>('')
const experimentSummary = ref<Record<string, unknown> | null>(null)
const confusionMatrix = ref<{ tn: number; fp: number; fn: number; tp: number } | null>(null)
const sampleRows = ref<Array<{ index: number; true_label: number; pred_label: number; score: number }>>([])
const trainLogRows = ref<Record<string, unknown>[]>([])
const evalLogRows = ref<Record<string, unknown>[]>([])
const trainLogFilter = ref('')
const evalLogFilter = ref('')

const experimentActionLabel = computed(() => {
  const map: Record<string, string> = { import: '导入数据集', train: '训练 BERT', evaluate: '验证集评估', compare: '对比实验' }
  return map[experimentAction.value] || '处理'
})

const filteredTrainLogRows = computed(() => {
  if (!trainLogFilter.value) return trainLogRows.value
  const keyword = trainLogFilter.value.toLowerCase()
  return trainLogRows.value.filter((row) =>
    Object.values(row).some((val) => String(val).toLowerCase().includes(keyword))
  )
})

const filteredEvalLogRows = computed(() => {
  if (!evalLogFilter.value) return evalLogRows.value
  const keyword = evalLogFilter.value.toLowerCase()
  return evalLogRows.value.filter((row) =>
    Object.values(row).some((val) => String(val).toLowerCase().includes(keyword))
  )
})
const sampleSearchText = ref('')
const sampleCurrentPage = ref(1)
const samplePageSize = ref(5)
const sampleTrueLabel = ref<number | null>(null)
const samplePredLabel = ref<number | null>(null)
const sampleScoreRange = ref('')
const misclassifiedSearchText = ref('')
const misclassifiedCurrentPage = ref(1)
const misclassifiedPageSize = ref(5)
const misclassifiedTrueLabel = ref<number | null>(null)
const misclassifiedPredLabel = ref<number | null>(null)
const misclassifiedScoreRange = ref('')
const misclassifiedRows = computed(() => sampleRows.value.filter(item => item.true_label !== item.pred_label))
const csvEscape = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`
const copyJson = async (value: unknown) => {
  try {
    await navigator.clipboard.writeText(JSON.stringify(value, null, 2))
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

const copyLatestStructuredResult = async () => {
  const payload = {
    model_predict: modelTabResult.value,
    business_result: structuredResult.value,
  }
  await copyJson(payload)
}

const resetStructuredForm = () => {
  structuredForm.identity_type = 'student'
  structuredForm.age = 20
  structuredForm.gender = 1
  structuredForm.study_year = 2
  structuredForm.cgpa = 3.0
  structuredForm.stress_level = 2
  structuredForm.sleep_duration = 7
  structuredForm.social_support = 3
  structuredForm.financial_pressure = 2
  structuredForm.family_history = 0
  structuredForm.academic_pressure = 2
  structuredForm.exercise_frequency = 3
  structuredForm.anxiety = 1
  structuredForm.panic_attack = 0
  structuredForm.treatment_seeking = 0
  ElMessage.success('已恢复默认结构化表单')
}
const toCsv = (rows: Array<{ index: number; true_label: number; pred_label: number; score: number }>) => {
  const header = ['index,true_label,pred_label,score']
  const lines = rows.map(row => [row.index, row.true_label, row.pred_label, row.score].map(csvEscape).join(','))
  return [header[0], ...lines].join('\n')
}
const downloadCsv = (filename: string, csv: string) => {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
const exportSampleCsv = (kind: 'all' | 'misclassified') => {
  const rows = kind === 'all' ? pagedSampleRows.value : pagedMisclassifiedRows.value
  const csv = toCsv(rows)
  downloadCsv(`${experimentForm.dataset_name}_${kind}_${Date.now()}.csv`, csv)
}
const getScoreRange = (range: string) => {
  if (range === '0-30') return [0, 0.3]
  if (range === '30-60') return [0.3, 0.6]
  if (range === '60-80') return [0.6, 0.8]
  if (range === '80-100') return [0.8, 1.0]
  return null
}
const filterSamples = (
  items: Array<{ index: number; true_label: number; pred_label: number; score: number }>,
  keyword: string,
  trueLabel: number | null,
  predLabel: number | null,
  scoreRange: string,
) => {
  const kw = keyword.trim().toLowerCase()
  const range = getScoreRange(scoreRange)
  return items.filter(item => {
    const hitKeyword = !kw || [item.index, item.true_label, item.pred_label, item.score].some(v => String(v).toLowerCase().includes(kw))
    const hitTrue = trueLabel === null || item.true_label === trueLabel
    const hitPred = predLabel === null || item.pred_label === predLabel
    const hitScore = !range || (item.score >= range[0] && item.score <= range[1])
    return hitKeyword && hitTrue && hitPred && hitScore
  })
}
const filteredSampleRows = computed(() => filterSamples(sampleRows.value, sampleSearchText.value, sampleTrueLabel.value, samplePredLabel.value, sampleScoreRange.value))
const filteredMisclassifiedRows = computed(() => filterSamples(misclassifiedRows.value, misclassifiedSearchText.value, misclassifiedTrueLabel.value, misclassifiedPredLabel.value, misclassifiedScoreRange.value))
const pagedSampleRows = computed(() => filteredSampleRows.value.slice((sampleCurrentPage.value - 1) * samplePageSize.value, sampleCurrentPage.value * samplePageSize.value))
const pagedMisclassifiedRows = computed(() => filteredMisclassifiedRows.value.slice((misclassifiedCurrentPage.value - 1) * misclassifiedPageSize.value, misclassifiedCurrentPage.value * misclassifiedPageSize.value))
watch([sampleSearchText, samplePageSize, sampleTrueLabel, samplePredLabel, sampleScoreRange], () => { sampleCurrentPage.value = 1 })
watch([misclassifiedSearchText, misclassifiedPageSize, misclassifiedTrueLabel, misclassifiedPredLabel, misclassifiedScoreRange], () => { misclassifiedCurrentPage.value = 1 })

const physioForm = reactive({
  source: 'manual', sleep_hours: 7, sleep_quality: 3,
  exercise_minutes: 30, heart_rate: 72, systolic_bp: 120,
  diastolic_bp: 80, steps: 5000
})
const physioSubmitting = ref(false)

const submitFusion = async (auto = false) => {
  // 融合预测允许三种模态任意组合；自动融合会先同步最近一次结构化、文本和生理输入。
  if (auto) {
    syncFusionInputsFromLatest()
  }

  fusionSubmitting.value = true
  try {
    const features = JSON.parse(fusionForm.featuresJson || '{}')
    const physiological = JSON.parse(fusionForm.physiologicalJson || '{}')
    fusionResult.value = await modelApi.predictFusionModel({ features, text: fusionForm.text, physiological })
    // 检测到危机覆盖时自动弹出预警弹窗
    if (fusionResult.value?.crisis_override) {
      showCrisisDialog()
    }
    await loadReport()
    ElMessage.success(auto ? '三类数据已完成，已自动进行多模态融合预测，风险报告已更新' : '融合预测完成，风险报告已更新')
    if (auto) activeTab.value = 'fusion'
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, auto ? '自动融合预测失败' : '融合预测失败').detail)
  } finally {
    fusionSubmitting.value = false
  }
}

const submitPhysio = async () => {
  // 生理数据既会落到服务端，也会即时写入本地历史，方便用户快速查看趋势。
  physioSubmitting.value = true
  try {
    await userApi.recordPhysiological({ ...physioForm })

    physioHistory.value.unshift({
      time: new Date().toLocaleString(),
      sleep_hours: physioForm.sleep_hours,
      sleep_quality: physioForm.sleep_quality,
      exercise_minutes: physioForm.exercise_minutes,
      heart_rate: physioForm.heart_rate,
      systolic_bp: physioForm.systolic_bp,
      diastolic_bp: physioForm.diastolic_bp,
      steps: physioForm.steps
    })
    savePhysioHistory()

    autoFusionReady.physiological = true
    await maybeAutoSubmitFusion()

    ElMessage.success('生理数据已记录')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '记录失败').detail)
  } finally {
    physioSubmitting.value = false
  }
}

type TrainExperimentResult = TrainResult

type EvaluateExperimentResult = EvaluateResult

type CompareExperimentResult = CompareResult

const applyTrainResult = (res: TrainExperimentResult) => {
  const trainLoss = Array.isArray(res.train_loss) ? res.train_loss.map((n: number) => Number(n)) : []
  const valLoss = Array.isArray(res.val_loss) ? res.val_loss.map((n: number) => Number(n)) : []
  const valAccuracy = Array.isArray(res.val_accuracy) ? res.val_accuracy.map((n: number) => Number(n)) : []
  if (trainLoss.length) experimentCharts.loss = trainLoss
  else if (valLoss.length) experimentCharts.loss = valLoss
  if (valAccuracy.length) experimentCharts.accuracy = valAccuracy
  if (res.trainer_log_history) trainLogRows.value = res.trainer_log_history
  if (res.eval_history) evalLogRows.value = res.eval_history
  experimentSummary.value = {
    train_loss: Array.isArray(res.train_loss) ? res.train_loss.join(' / ') : (res.train_loss ?? '-'),
    val_loss: Array.isArray(res.val_loss) ? res.val_loss.join(' / ') : (res.val_loss ?? '-'),
    val_accuracy: Array.isArray(res.val_accuracy) ? res.val_accuracy.join(' / ') : (res.val_accuracy ?? '-'),
    status: res.status
  }
  experimentRawResult.value = JSON.stringify(res, null, 2)
  nextTick(() => renderExperimentCharts())
}

const applyEvaluateResult = (res: EvaluateExperimentResult) => {
  const cm = res.confusion_matrix
  confusionMatrix.value = {
    tn: cm.tn,
    fp: cm.fp,
    fn: cm.fn,
    tp: cm.tp,
  }
  experimentCharts.confusion = [[cm.tn, cm.fp], [cm.fn, cm.tp]]
  sampleRows.value = res.prediction_samples
  sampleCurrentPage.value = 1
  misclassifiedCurrentPage.value = 1
  experimentSummary.value = {
    train_loss: experimentSummary.value?.train_loss ?? '-',
    val_loss: experimentSummary.value?.val_loss ?? '-',
    val_accuracy: res.metrics.accuracy,
    status: 'evaluated'
  }
  if (res.eval_history) evalLogRows.value = res.eval_history
  experimentRawResult.value = JSON.stringify(res, null, 2)
  nextTick(() => renderExperimentCharts())
}

const applyCompareResult = (res: CompareExperimentResult) => {
  experimentCharts.compare = res.results
  experimentRawResult.value = JSON.stringify(res, null, 2)
  nextTick(() => renderExperimentCharts())
}

const importDataset = async () => {
  experimentLoading.value = true
  experimentAction.value = 'import'
  experimentProgress.value = 0
  try {
    const res = await modelApi.importDataset(experimentForm)
    experimentProgress.value = 100
    experimentSummary.value = {
      train_loss: '-',
      val_loss: '-',
      val_accuracy: '-',
      status: res.message
    }
    experimentRawResult.value = JSON.stringify(res, null, 2)
    ElMessage.success('数据集导入完成')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '导入失败').detail)
  } finally {
    experimentLoading.value = false
    experimentProgress.value = 0
  }
}

const trainBert = async () => {
  experimentLoading.value = true
  experimentAction.value = 'train'
  experimentProgress.value = 10
  try {
    const res = await modelApi.trainModel({ dataset_name: experimentForm.dataset_name, model_name: 'text_bert_classifier', epochs: 3, batch_size: 16, learning_rate: 2e-5 })
    experimentProgress.value = 100
    applyTrainResult(res)
    ElMessage.success('训练完成')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '训练失败').detail)
  } finally {
    experimentLoading.value = false
    experimentProgress.value = 0
  }
}

const evaluateBert = async () => {
  experimentLoading.value = true
  experimentAction.value = 'evaluate'
  experimentProgress.value = 20
  try {
    const res = await modelApi.evaluateModel({ dataset_name: experimentForm.dataset_name, model_name: 'text_bert_classifier', split: 'validation' })
    experimentProgress.value = 100
    applyEvaluateResult(res)
    experimentSummary.value = {
      train_loss: experimentSummary.value?.train_loss ?? '-',
      val_loss: experimentSummary.value?.val_loss ?? '-',
      val_accuracy: res.metrics?.accuracy ?? '-',
      status: 'evaluated'
    }
    ElMessage.success('验证集评估完成')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '评估失败').detail)
  } finally {
    experimentLoading.value = false
    experimentProgress.value = 0
  }
}

const renderExperimentCharts = () => {
  // 训练/验证/对比图表都采用"先判断容器、再判断数据"的方式，避免因异步返回顺序不同导致空图实例和重复渲染。
  let hasNewChart = false
  if (lossChartRef.value && experimentCharts.loss.length) {
    lossChart ??= echarts.init(lossChartRef.value)
    hasNewChart = true
    lossChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: experimentCharts.loss.map((_, i) => `E${i + 1}`) },
      yAxis: { type: 'value' },
      series: [{ type: 'line', smooth: true, data: experimentCharts.loss, lineStyle: { width: 2, color: '#409eff' }, areaStyle: { opacity: 0.15 } }]
    })
  }
  if (accuracyChartRef.value && experimentCharts.accuracy.length) {
    accuracyChart ??= echarts.init(accuracyChartRef.value)
    hasNewChart = true
    accuracyChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: experimentCharts.accuracy.map((_, i) => `E${i + 1}`) },
      yAxis: { type: 'value', min: 0, max: 1 },
      series: [{ type: 'line', smooth: true, data: experimentCharts.accuracy, lineStyle: { width: 2, color: '#67c23a' }, areaStyle: { opacity: 0.15 } }]
    })
  }
  if (compareChartRef.value && experimentCharts.compare.length) {
    compareChart ??= echarts.init(compareChartRef.value)
    hasNewChart = true
    compareChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['accuracy', 'precision', 'recall', 'f1', 'auc'] },
      grid: { left: 50, right: 20, top: 30, bottom: 60 },
      xAxis: { type: 'category', data: experimentCharts.compare.map(i => i.model_name) },
      yAxis: { type: 'value', min: 0, max: 1 },
      series: ['accuracy', 'precision', 'recall', 'f1', 'auc'].map((key, idx) => ({
        name: key,
        type: 'bar',
        data: experimentCharts.compare.map(item => item[key as keyof typeof item] as number),
        itemStyle: { color: ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399'][idx] }
      }))
    })
  }
  if (confusionChartRef.value && experimentCharts.confusion.length) {
    confusionChart ??= echarts.init(confusionChartRef.value)
    hasNewChart = true
    confusionChart.setOption({
      tooltip: {},
      xAxis: { type: 'category', data: ['Pred 0', 'Pred 1'] },
      yAxis: { type: 'category', data: ['True 0', 'True 1'] },
      visualMap: { min: 0, max: Math.max(...experimentCharts.confusion.flat(), 1), calculable: true, orient: 'horizontal', left: 'center', bottom: 0 },
      series: [{ type: 'heatmap', data: [[0, 0, experimentCharts.confusion[0][0]], [1, 0, experimentCharts.confusion[0][1]], [0, 1, experimentCharts.confusion[1][0]], [1, 1, experimentCharts.confusion[1][1]]], label: { show: true } }]
    })
  }
  // P1-D-9 修复：首次创建图表时添加 resize 监听器，确保窗口尺寸变化时图表自动调整
  // 使用标志位确保只注册一次, 避免 renderExperimentCharts 多次调用导致重复绑定
  if (hasNewChart && !experimentResizeRegistered) {
    window.addEventListener('resize', handleExperimentResize)
    experimentResizeRegistered = true
  }
}

const compareModels = async () => {
  experimentLoading.value = true
  experimentAction.value = 'compare'
  experimentProgress.value = 30
  try {
    // 对比实验优先使用统一命名后的模型 ID，减少接口层和前端的命名漂移。
    const res = await modelApi.compareModels({ dataset_name: experimentForm.dataset_name, model_names: ['text_bert_classifier', 'text_depression_model', 'fusion_dnn_best'] })
    experimentProgress.value = 100
    applyCompareResult(res)
    ElMessage.success('对比实验完成')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '对比失败').detail)
  } finally {
    experimentLoading.value = false
    experimentProgress.value = 0
  }
}

watch(activeTab, async (val) => {
  if (val !== 'report') return

  if (!report.value) {
    await loadReport()
    return
  }

  await renderReportTrend()
})

const handleExport = async (format: 'json' | 'csv' | 'pdf') => {
  try {
    const response = await userApi.exportRiskData(format, 90)
    const mimeType = format === 'pdf' ? 'application/pdf' : format === 'csv' ? 'text/csv' : 'application/json'
    const blob = new Blob([response.data], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = format === 'pdf' ? `risk_report_${Date.now()}.pdf` : `risk_export_${Date.now()}.${format}`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`${format.toUpperCase()} 导出已完成`)
  } catch {
    ElMessage.error(`${format.toUpperCase()} 导出失败`)
  }
}

onMounted(() => {
  loadReport()
  loadPredictionHistory()
  loadTextPredictionHistory()
  loadPhysioHistory()
  nextTick(() => renderExperimentCharts())
})

onUnmounted(() => {
  disposeReportTrend()
  disposeExperimentCharts()
})
</script>

<style scoped>
.risk-page {
  padding: 0;
}

.panel-card {
  border-radius: 16px;
}

.compact-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.sticky-summary {
  position: sticky;
  top: 16px;
}

.hint-list {
  width: 100%;
}

.hint-item {
  padding: 12px 14px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(64,158,255,0.08), rgba(64,158,255,0.03));
  color: #303133;
  line-height: 1.6;
}

.result-panel {
  border-radius: 16px;
}

.result-grid {
  margin-bottom: 10px;
}

.mini-result-card {
  min-height: 260px;
  border-radius: 14px;
}

.mini-title {
  font-weight: 600;
  color: #303133;
}

.result-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.chart-box {
  width: 100%;
  height: 280px;
}

.chart-box-lg {
  height: 340px;
}

.template-card {
  min-height: 100%;
}

.template-path {
  font-size: 13px;
  color: #606266;
  margin-bottom: 12px;
}

.template-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}

.card-title {
  font-weight: 600;
}

.report-score-wrap {
  display: flex;
  justify-content: center;
  padding: 12px 0;
}

.dashboard-score {
  text-align: center;
}

.score-num {
  font-size: 28px;
  font-weight: 700;
  display: block;
}

.score-label {
  font-size: 12px;
  color: #909399;
}

.log-viewer-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.log-viewer-card {
  min-width: 0;
}

.table-footer {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.report-meta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 8px;
}

.trend-text {
  font-size: 13px;
  color: #606266;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.advice-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.advice-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border-radius: 8px;
  transition: transform 0.2s ease;
}

.advice-card:hover {
  transform: translateX(4px);
}

.advice-index {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff, #66b1ff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.advice-text {
  font-size: 13px;
  color: #303133;
  line-height: 1.6;
  flex: 1;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.slider-with-value {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.slider-with-value .el-slider {
  flex: 1;
}

.slider-value-label {
  font-size: 13px;
  color: #606266;
  font-weight: 500;
  min-width: 60px;
  text-align: right;
}

.step-content {
  margin-top: 20px;
  min-height: 200px;
}

.step-actions {
  margin-top: 20px;
  display: flex;
  justify-content: flex-start;
  gap: 8px;
}

.text-muted {
  color: #909399;
  font-size: 13px;
}

.experiment-progress {
  width: 100%;
}

.progress-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
  display: block;
}

.chart-skeleton {
  padding: 20px;
}

.log-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.field-hint {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
}

.crisis-alert-content {
  padding: 0 8px;
}

.crisis-hotlines {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hotline-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(245, 108, 108, 0.08), rgba(245, 108, 108, 0.03));
  border: 1px solid rgba(245, 108, 108, 0.15);
}

.hotline-item .el-icon {
  font-size: 24px;
  color: #f56c6c;
  flex-shrink: 0;
}

.hotline-info {
  flex: 1;
}

.hotline-name {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
}

.hotline-number {
  font-size: 18px;
  color: #f56c6c;
  font-weight: 700;
  margin-top: 4px;
}

.experimental-ref {
  font-size: 12px;
  color: #909399;
  line-height: 1.7;
  padding: 8px 10px;
  background: rgba(144, 147, 153, 0.06);
  border-radius: 8px;
  border: 1px dashed rgba(144, 147, 153, 0.3);
}

.experimental-ref p {
  margin: 0;
}

.routing-info-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: rgba(64, 158, 255, 0.06);
  border-radius: 8px;
  border: 1px solid rgba(64, 158, 255, 0.15);
  flex-wrap: wrap;
}

.routing-reason {
  font-size: 12px;
  color: #606266;
  flex: 1;
  min-width: 0;
}

.lite-ref {
  background: rgba(230, 162, 60, 0.08);
  border-color: rgba(230, 162, 60, 0.3);
}

.lite-ref p {
  margin: 0;
}
</style>
