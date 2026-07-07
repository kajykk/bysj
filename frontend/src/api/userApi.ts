import { gdprApi } from './gdprApi'
import { userBindingApi } from './userBindingApi'
import { userContentApi } from './userContentApi'
import { userFileApi } from './userFileApi'
import { userInterventionApi } from './userInterventionApi'
import { userRiskApi } from './userRiskApi'
import { userWarningsApi } from './userWarningsApi'

export type {
  ActiveIntervention,
  AssessmentRecordItem,
  ContentDetail,
  ContentItem,
  DataHistoryItem,
  InterventionHistoryItem,
  UserBindingInfo,
  WarningItem,
  WarningSettingData,
} from './userTypes'

export type {
  RiskReport,
  RiskTrend,
  StructuredCollectResult,
  TextAnalyzeResult,
} from './userRiskApi'

export type { GdprDeleteResult } from './gdprApi'

export const userApi = {
  ...userWarningsApi,
  ...userRiskApi,
  ...userContentApi,
  ...userInterventionApi,
  ...userBindingApi,
  ...userFileApi,
  ...gdprApi,
}
