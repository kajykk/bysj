"""Generate the optimized resume PDF using fpdf2 with CJK font (SimHei)."""
from fpdf import FPDF
import sys

# ---------- Content ----------
NAME = "邝振华"
INTRO = "男 | 21 岁 | 15623089361 | 1754902912@qq.com"
JOB = "求职意向：全栈开发实习生（AI 编程方向） | 可实习时长：6 个月（2025.11 起全职，每周 ≥3 天）"
LINK = "AI 作品链接：https://github.com/kajykk/bysj"

EDU = [
    ("湖北商贸学院 | 数据科学与大数据技术 | 本科 | 2022.09 - 2026.06", [
        "主修课程：数据结构、Python 程序设计、机器学习基础、数据库原理、数据仓库与数据挖掘",
        "学业表现：专业排名前 10%，大学英语六级 460 分",
    ]),
]

AI_SKILLS = [
    "AI 编程工具重度用户：熟练使用 Trae、Cursor、Claude Code 三款主流 AI 编程工具，具备从需求拆解、代码生成、调试重构到自动化测试的端到端 AI 辅助开发能力",
    "AI 工程方法论：掌握 Skill 化 Prompt 工程、Agentic Workflow（规划→执行→验证→回归）、AI 驱动的 TDD/契约测试流程；熟悉 Schemathesis、Playwright 等工具与 AI 编程结合的测试闭环",
    "AI 交付实证：独立使用 AI 编程工具完整交付一个生产级全栈系统（含 23 个 API、30+ 张表、200+ 测试用例、9 个 Docker 服务），详见项目经历",
    "效率提升：通过 AI 编程工具将需求到交付周期缩短约 60%，单日可完成 3-5 个端到端功能模块（含测试）",
]

PRO_SKILLS = [
    "后端开发：Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic 2.7 + Celery 5.4；熟悉 RESTful API、JWT 鉴权、异步任务调度、断路器与降级",
    "前端开发：Vue 3.5 + TypeScript 5.6 + Vite 6 + Element Plus + ECharts + Pinia + Vue Router；熟悉 PWA、虚拟列表、懒加载、骨架屏等性能优化",
    "数据库与缓存：PostgreSQL 15 / SQLite、Redis 7（缓存 + Celery broker + WebSocket pubsub）、MySQL；熟练 SQL，熟悉 Alembic 迁移",
    "ML 工程：scikit-learn、PyTorch、Transformers、NumPy/Pandas；具备多模态融合、模型注册、金丝雀发布、漂移检测、自动回滚实战经验",
    "DevOps 与可观测性：Docker + docker-compose、GitHub Actions（12 条 CI）、Prometheus + Grafana + Sentry、Lighthouse CI",
    "数据技能：Hadoop/Hive/PyHive、Pandas/NumPy、Matplotlib/Seaborn、数据清洗与 ETL",
]

# ---------- Projects ----------
PROJ_DWS = {
    "title": "心理健康风险评估系统（DWS） | AI 全栈个人项目 | 2025.10 - 至今",
    "link": "AI 作品链接：https://github.com/kajykk/bysj",
    "intro": "面向高校的心理健康筛查与干预平台，采用前后端分离 + 多模态 ML 融合 + 异步任务调度 + 全链路可观测性的全栈架构。全程使用 Trae AI 编程工具独立完成从需求分析、架构设计、编码实现到测试交付的端到端开发，产出 C4 架构图 4 份、ADR 决策记录 10 份、200+ 自动化测试用例。",
    "stack": "技术栈：FastAPI + Vue 3.5 + TypeScript + PyTorch + PostgreSQL + Redis + Celery + Docker + Prometheus + Grafana",
    "modules": [
        "多模态风险评估：结构化问卷 + 文本分析（BERT/TF-IDF）+ 生理信号三模态加权融合，使用 AI 工具完成融合引擎、特征工程、4 层回退策略（BERT → TF-IDF/LR → 启发式）的全流程开发",
        "模型治理：金丝雀发布、漂移检测（PSI/KL 散度）、自动回滚、断路器熔断（DB/ML/SMTP/Celery 四类），实现成功率 < 98% 自动回滚",
        "实时预警：WebSocket + Redis pubsub 实时推送，告警生命周期管理（New → Confirmed → Fixing → Pending Review → Closed），多渠道通知",
        "合规与安全：GDPR 数据导出/被遗忘权、PII 字段 Fernet 加密、路径遍历防护、TOCTOU 竞态修复、CSP/XSS/速率限制",
        "可观测性：Prometheus 指标 + Grafana 11.6 仪表盘 + Sentry 错误追踪 + 分布式链路，前端 Core Web Vitals 采集",
        "测试与 CI/CD：单元/集成/契约（Schemathesis）/E2E（Playwright）/性能（Locust）/稳定性测试全链路覆盖，12 条 GitHub Actions 流水线",
    ],
    "scale": "项目规模：23 个 API 路由、33 个核心模块、30+ 张数据表、29 个业务服务、27 个 ML 文件、9 个 Docker 服务、200+ 测试用例、88% 契约测试通过率",
    "ai_highlights": [
        "搭建个人 Skill 库（Ralph 规划框架、Sysopt 系统优化、Superpowers 工程方法论），形成可复用 AI 编程工作流",
        "实践「规划→实现→审计→整改→回归→验收」六阶段 AI 驱动开发流程，产出深度审计报告 4 份、整改清单与修复优先级表",
        "通过 AI 工具完成 P0/P1/P2 三级问题修复（路径遍历、TOCTOU、单类 y_true、Dropout 线程安全等），验证用例全量回归通过",
    ],
}

PROJ_HIVE = {
    "title": "高校教育大数据整合与分析系统 | 数据分析实习生 | 武汉中软卓越科技 | 2025.03 - 2025.06",
    "stack": "技术栈：Hadoop、Hive、PyHive、Python、Pandas、Matplotlib、Seaborn",
    "bullets": [
        "与教学管理部门对接，调研数据现状与业务需求，梳理数据来源与标准",
        "使用 Pandas 清洗 10 万+ 条学生成绩、课程选修等多源数据，完成标准化与汇聚入库",
        "基于 Hadoop 搭建分布式存储，构建 Hive 数据仓库分层模型，编写 HiveSQL 完成多维度查询",
        "建立数据质量检查规则，利用 Matplotlib/Seaborn 制作可视化报告向管理部门汇报",
    ],
}

PROJ_EMP = {
    "title": "员工信息管理系统 | 后端开发实习生 | 2025.07 - 2025.10",
    "stack": "技术栈：SpringBoot + MyBatis + SpringMVC + MySQL",
    "bullets": [
        "与企业方沟通需求，将业务痛点转化为系统功能方案",
        "使用 MyBatis 实现 MySQL 增删改查，声明式事务保证数据一致性",
        "完成单元测试并修复 3 个数据异常 Bug，系统上线后查询效率较手工管理提升 80%",
    ],
}

CAMPUS = {
    "title": "图书馆管理委员会外联部部长 | 2023.09 - 2025.06",
    "bullets": [
        "对接 5 家校外书店、2 家出版社，达成 3 项图书捐赠合作，争取 1200+ 册图书资源",
        "组织 4 次跨校图书馆社团交流活动，带领团队完成 2 次校园读书活动赞助对接",
        "锻炼跨部门沟通协调能力，能在 AI 全栈项目中高效对接业务需求",
    ],
}

RESEARCH = {
    "title": "北京大学医学部心理咨询基础研学营 | 2025.01 - 2025.02",
    "bullets": [
        "系统学习心理咨询基础理论、人际沟通技巧等 8 门核心课程并通过考核",
        "提升共情能力，为 DWS 心理健康项目的需求理解与产品打磨提供领域知识支撑",
    ],
}

EVAL = [
    "AI 编程工具重度用户：Trae/Cursor/Claude Code 三工具深度使用，独立完成生产级全栈系统交付，具备从想法到上线的 AI 驱动全流程能力",
    "全栈工程能力扎实：FastAPI + Vue 3 双栈实战，熟悉异步、ML 工程、可观测性、合规安全等工程化主题",
    "数据背景加持：数据科学与大数据技术专业，10 万+ 条数据处理经验，能在全栈开发中融合数据治理与 ML 能力",
    "沟通与领域双优势：外联部部长经历 + 北大心理咨询研学，兼具跨部门沟通能力与心理健康领域知识",
]


# ---------- PDF ----------
class Resume(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("zh", "", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"第 {self.page_no()} 页", align="C")

    def section_title(self, text):
        self.ln(3)
        self.set_font("zh", "", 13)
        self.set_text_color(20, 60, 120)
        # left bar
        y = self.get_y()
        self.set_draw_color(20, 60, 120)
        self.set_line_width(0.8)
        self.line(10, y + 1, 10, y + 7)
        self.set_xy(13, y)
        self.cell(0, 7, text, ln=1)
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.2)
        y2 = self.get_y()
        self.line(10, y2, 200, y2)
        self.ln(1.5)

    def bullet(self, text, indent=12, h=5.2):
        self.set_x(indent)
        self.set_font("zh", "", 10)
        self.set_text_color(45, 45, 45)
        self.multi_cell(0, h, "·  " + text, new_x="LMARGIN", new_y="NEXT")

    def kv_block(self, label, lines):
        self.set_x(12)
        self.set_font("zh", "", 10.5)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.2, label, new_x="LMARGIN", new_y="NEXT")
        for ln in lines:
            self.bullet(ln)


def build():
    pdf = Resume(orientation="P", unit="mm", format="A4")
    pdf.add_font("zh", "", r"C:\Windows\Fonts\simhei.ttf")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    # ----- Header -----
    pdf.set_font("zh", "", 22)
    pdf.set_text_color(15, 40, 90)
    pdf.cell(0, 12, NAME, ln=1, align="C")

    pdf.set_font("zh", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 5.5, INTRO, ln=1, align="C")
    pdf.cell(0, 5.5, JOB, ln=1, align="C")
    pdf.set_text_color(20, 90, 160)
    pdf.cell(0, 5.5, LINK, ln=1, align="C")
    pdf.ln(2)
    pdf.set_draw_color(15, 40, 90)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)

    # ----- Education -----
    pdf.section_title("教育背景")
    for title, lines in EDU:
        pdf.set_x(12)
        pdf.set_font("zh", "", 11)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 5.5, title, new_x="LMARGIN", new_y="NEXT")
        for ln in lines:
            pdf.bullet(ln)

    # ----- AI Skills -----
    pdf.section_title("AI 编程能力（核心）")
    for s in AI_SKILLS:
        pdf.bullet(s)

    # ----- Professional Skills -----
    pdf.section_title("专业技能")
    for s in PRO_SKILLS:
        pdf.bullet(s)

    # ----- Projects -----
    pdf.section_title("项目经历")

    # DWS
    pdf.set_x(12)
    pdf.set_font("zh", "", 11.5)
    pdf.set_text_color(15, 40, 90)
    pdf.multi_cell(0, 5.8, PROJ_DWS["title"], new_x="LMARGIN", new_y="NEXT")
    pdf.bullet(PROJ_DWS["link"])
    pdf.bullet(PROJ_DWS["intro"])
    pdf.bullet(PROJ_DWS["stack"])
    pdf.set_x(12)
    pdf.set_font("zh", "", 10)
    pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 5.2, "【核心模块与 AI 交付成果】", new_x="LMARGIN", new_y="NEXT")
    for m in PROJ_DWS["modules"]:
        pdf.bullet(m)
    pdf.bullet(PROJ_DWS["scale"])
    pdf.set_x(12)
    pdf.set_font("zh", "", 10)
    pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 5.2, "【AI 工具应用亮点】", new_x="LMARGIN", new_y="NEXT")
    for h in PROJ_DWS["ai_highlights"]:
        pdf.bullet(h)

    # Hive project
    pdf.ln(2)
    pdf.set_x(12)
    pdf.set_font("zh", "", 11.5)
    pdf.set_text_color(15, 40, 90)
    pdf.multi_cell(0, 5.8, PROJ_HIVE["title"], new_x="LMARGIN", new_y="NEXT")
    pdf.bullet(PROJ_HIVE["stack"])
    for b in PROJ_HIVE["bullets"]:
        pdf.bullet(b)

    # Employee system
    pdf.ln(2)
    pdf.set_x(12)
    pdf.set_font("zh", "", 11.5)
    pdf.set_text_color(15, 40, 90)
    pdf.multi_cell(0, 5.8, PROJ_EMP["title"], new_x="LMARGIN", new_y="NEXT")
    pdf.bullet(PROJ_EMP["stack"])
    for b in PROJ_EMP["bullets"]:
        pdf.bullet(b)

    # ----- Campus -----
    pdf.section_title("校园经历")
    pdf.set_x(12)
    pdf.set_font("zh", "", 11.5)
    pdf.set_text_color(15, 40, 90)
    pdf.multi_cell(0, 5.8, CAMPUS["title"], new_x="LMARGIN", new_y="NEXT")
    for b in CAMPUS["bullets"]:
        pdf.bullet(b)

    # ----- Research -----
    pdf.section_title("研学经历")
    pdf.set_x(12)
    pdf.set_font("zh", "", 11.5)
    pdf.set_text_color(15, 40, 90)
    pdf.multi_cell(0, 5.8, RESEARCH["title"], new_x="LMARGIN", new_y="NEXT")
    for b in RESEARCH["bullets"]:
        pdf.bullet(b)

    # ----- Self-Evaluation -----
    pdf.section_title("自我评价")
    for e in EVAL:
        pdf.bullet(e)

    out = r"e:\code\bysj\邝振华_简历_优化版.pdf"
    pdf.output(out)
    print(f"PDF generated: {out}")
    print(f"Pages: {pdf.page_no()}")


if __name__ == "__main__":
    try:
        build()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
