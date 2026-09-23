# v1.17 设计文档 — 人工复核与危机审计闭环

> **迭代名称**: v1.17-review-workflow-text-model-upgrade
> **规划日期**: 2026-05-01

---

## 1. 详细设计

### 1.1 Review Service 设计

```python
class ReviewService:
    """复核任务服务"""

    def create_review_task(self, user_id: int, prediction_result: dict) -> ReviewTask:
        """
        根据预测结果自动创建复核任务
        触发条件: review_required=True 或 crisis_override=True
        """

    def get_reviews(
        self,
        status: ReviewStatus | None = None,
        priority: ReviewPriority | None = None,
        assigned_to: int | None = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedResult[ReviewTask]:
        """查询复核任务列表"""

    def assign_review(self, review_id: int, counselor_id: int) -> ReviewTask:
        """分配复核任务给咨询师"""

    def resolve_review(
        self,
        review_id: int,
        counselor_id: int,
        resolution_note: str,
        action: ResolutionAction
    ) -> ReviewTask:
        """处理复核任务"""

    def escalate_review(self, review_id: int, counselor_id: int, reason: str) -> ReviewTask:
        """升级复核任务（危机事件）"""

    def get_review_stats(self, days: int = 30) -> ReviewStats:
        """获取复核统计"""
```

### 1.2 Crisis Event Service 设计

```python
class CrisisEventService:
    """危机事件审计服务"""

    def record_crisis_event(
        self,
        user_id: int,
        trigger_source: str,
        crisis_data: dict
    ) -> CrisisEvent:
        """
        记录危机事件
        由 CrisisDetector 或 FusionPriorityEngine 触发
        """

    def get_crisis_events(
        self,
        status: CrisisStatus | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 20
    ) -> PaginatedResult[CrisisEvent]:
        """查询危机事件（管理员权限）"""

    def handle_crisis_event(
        self,
        event_id: int,
        handled_by: int,
        action: str
    ) -> CrisisEvent:
        """处理危机事件"""

    def export_crisis_events(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> bytes:
        """导出危机事件报告（CSV）"""
```

### 1.3 关键词库扩展设计

```python
class CrisisKeywordLibrary:
    """危机关键词库（v1.17 扩展版）"""

    CATEGORIES = {
        "suicide": {"weight": 1.0, "keywords": [...]},
        "self_harm": {"weight": 0.9, "keywords": [...]},
        "despair": {"weight": 0.8, "keywords": [...]},
        "internet_slang": {"weight": 0.7, "keywords": [...]},
        "planning": {"weight": 1.0, "keywords": [...]},
        "help_seeking": {"weight": 0.6, "keywords": [...]},
    }

    FALSE_POSITIVE_FILTERS = [
        "累死了", "笑死了", "气死了", "社死了", "尴尬死了"
    ]
```

---

## 2. 前端设计

### 2.1 咨询师复核列表页

```
┌─────────────────────────────────────────────────────────────┐
│  复核任务管理                                    [筛选] [刷新]│
├─────────────────────────────────────────────────────────────┤
│  状态: [全部 ▼]  优先级: [全部 ▼]  时间: [最近7天 ▼]        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┬──────────┬────────┬──────────┬──────────────┐│
│  │ 用户     │ 风险等级  │ 优先级  │ 状态     │ 创建时间     ││
│  ├──────────┼──────────┼────────┼──────────┼──────────────┤│
│  │ 用户A    │ 严重     │ 危机   │ 待处理   │ 2026-05-01   ││
│  │ 用户B    │ 较高     │ 高风险 │ 处理中   │ 2026-05-01   ││
│  │ ...      │ ...      │ ...    │ ...      │ ...          ││
│  └──────────┴──────────┴────────┴──────────┴──────────────┘│
│                                                      [分页]  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 咨询师复核详情页

```
┌─────────────────────────────────────────────────────────────┐
│  复核详情                                        [返回列表]  │
├─────────────────────────────────────────────────────────────┤
│  用户信息                                                    │
│  ├─ 用户ID: xxx  昵称: xxx  年龄: xx                        │
│  └─ 历史风险: [查看历史记录]                                 │
├─────────────────────────────────────────────────────────────┤
│  模型预测结果                                                │
│  ├─ 风险分数: 85  风险等级: 严重                             │
│  ├─ 触发原因: [危机表达] [单模型高风险]                      │
│  ├─ 危机覆盖: 是                                             │
│  └─ 模型版本: v1.16-risk-calibration                         │
├─────────────────────────────────────────────────────────────┤
│  风险因素: [睡眠问题] [学业压力] [情绪困扰]                  │
│  保护因素: [求助意愿] [社会支持]                             │
├─────────────────────────────────────────────────────────────┤
│  处理操作                                                    │
│  ├─ [标记已处理]  [升级危机事件]                             │
│  └─ 处理备注: [____________________]                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 集成点

### 3.1 与 v1.16 模型引擎集成

```python
# 在 model_engine.py 的 predict_fusion() 中
result = fusion_engine.predict(...)

# 如果触发复核，自动创建复核任务
if result.get("review_required") or result.get("crisis_override"):
    review_task = review_service.create_review_task(
        user_id=current_user.id,
        prediction_result=result
    )
    result["review_task_id"] = review_task.id

# 如果触发危机，记录危机事件
if result.get("crisis_override"):
    crisis_event = crisis_event_service.record_crisis_event(
        user_id=current_user.id,
        trigger_source="fusion",
        crisis_data={
            "crisis_keywords": result.get("crisis_keywords", []),
            "crisis_score": result.get("crisis_score", 0),
            "input_summary": summarize_input(text_input),
            "review_task_id": review_task.id
        }
    )
```

### 3.2 与现有权限系统集成

- 复用现有的 JWT 认证
- 复用现有的角色权限系统
- 新增 `review.handle` 和 `crisis_event.view` 权限

---

## 4. 数据库迁移

### 4.1 Migration: 创建 review_tasks 表

```sql
CREATE TABLE review_tasks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    risk_report_id INTEGER,
    risk_level INTEGER NOT NULL,
    risk_score FLOAT NOT NULL,
    review_triggers JSONB DEFAULT '[]',
    crisis_override BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) DEFAULT 'pending',
    priority VARCHAR(20) DEFAULT 'normal_review',
    assigned_to INTEGER REFERENCES users(id),
    resolved_by INTEGER REFERENCES users(id),
    resolution_note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE INDEX idx_review_status ON review_tasks(status);
CREATE INDEX idx_review_priority ON review_tasks(priority);
CREATE INDEX idx_review_assigned ON review_tasks(assigned_to);
CREATE INDEX idx_review_user ON review_tasks(user_id);
CREATE INDEX idx_review_created ON review_tasks(created_at);
```

### 4.2 Migration: 创建 crisis_events 表

```sql
CREATE TABLE crisis_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    report_id INTEGER,
    trigger_source VARCHAR(20) NOT NULL,
    crisis_keywords JSONB DEFAULT '[]',
    crisis_score FLOAT,
    input_summary TEXT,
    review_task_id INTEGER REFERENCES review_tasks(id),
    status VARCHAR(20) DEFAULT 'detected',
    handled_by INTEGER REFERENCES users(id),
    handled_action TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    handled_at TIMESTAMP
);

CREATE INDEX idx_crisis_status ON crisis_events(status);
CREATE INDEX idx_crisis_user ON crisis_events(user_id);
CREATE INDEX idx_crisis_created ON crisis_events(created_at);
```

---

> **文档版本**: v1.0
> **最后更新**: 2026-05-01
