"""Generate a professional PDF resume from the markdown source."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# Register Chinese font (use system SimSun/SimHei)
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

# Try to register a Chinese-capable font
font_paths = [
    ("STSong", r"C:\Windows\Fonts\simsun.ttc"),
    ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
    ("MSYaHei", r"C:\Windows\Fonts\msyh.ttc"),
    ("MSYaHeiBold", r"C:\Windows\Fonts\msyhbd.ttc"),
]

chinese_font = None
chinese_bold_font = None
for name, path in font_paths:
    if os.path.exists(path):
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            if name == "STSong" and chinese_font is None:
                chinese_font = name
            elif name == "MSYaHei" and chinese_font is None:
                chinese_font = name
            elif name == "SimHei":
                chinese_bold_font = name
        except Exception:
            pass

# Fallbacks
if chinese_font is None:
    chinese_font = "Helvetica"
if chinese_bold_font is None:
    chinese_bold_font = chinese_font if chinese_font != "Helvetica" else "Helvetica-Bold"

# Colors
COLOR_PRIMARY = HexColor("#1a1a2e")
COLOR_ACCENT = HexColor("#0f3460")
COLOR_TEXT = HexColor("#333333")
COLOR_LIGHT = HexColor("#666666")
COLOR_DIVIDER = HexColor("#0f3460")

# Styles
styles = getSampleStyleSheet()

style_name = ParagraphStyle(
    "Name", parent=styles["Normal"],
    fontName=chinese_bold_font, fontSize=20, leading=24,
    textColor=COLOR_PRIMARY, alignment=TA_CENTER, spaceAfter=4
)

style_contact = ParagraphStyle(
    "Contact", parent=styles["Normal"],
    fontName=chinese_font, fontSize=9, leading=13,
    textColor=COLOR_LIGHT, alignment=TA_CENTER, spaceAfter=2
)

style_section = ParagraphStyle(
    "Section", parent=styles["Normal"],
    fontName=chinese_bold_font, fontSize=12, leading=16,
    textColor=COLOR_ACCENT, spaceBefore=10, spaceAfter=6
)

style_subheader = ParagraphStyle(
    "SubHeader", parent=styles["Normal"],
    fontName=chinese_bold_font, fontSize=10.5, leading=14,
    textColor=COLOR_PRIMARY, spaceBefore=6, spaceAfter=2
)

style_meta = ParagraphStyle(
    "Meta", parent=styles["Normal"],
    fontName=chinese_font, fontSize=8.5, leading=12,
    textColor=COLOR_LIGHT, spaceAfter=2
)

style_body = ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontName=chinese_font, fontSize=9, leading=13,
    textColor=COLOR_TEXT, spaceAfter=2
)

style_bullet = ParagraphStyle(
    "Bullet", parent=style_body,
    leftIndent=12, bulletIndent=2, spaceAfter=2
)

style_quote = ParagraphStyle(
    "Quote", parent=style_body,
    fontName=chinese_font, fontSize=8.5, leading=12,
    textColor=COLOR_ACCENT, leftIndent=8, rightIndent=8,
    spaceBefore=4, spaceAfter=4, borderColor=COLOR_DIVIDER,
    borderWidth=0, backColor=HexColor("#f5f7fa"),
    borderPadding=6
)


def make_bullet(text):
    """Create a bullet paragraph with proper formatting."""
    return Paragraph(f"• {text}", style_bullet)


def divider():
    return HRFlowable(
        width="100%", thickness=0.8, color=COLOR_DIVIDER,
        spaceBefore=4, spaceAfter=4
    )


def build_resume():
    """Build the resume document flowables."""
    story = []

    # Header
    story.append(Paragraph("邝振华", style_name))
    story.append(Paragraph(
        '男 | 21岁 | 15623089361 | 1754902912@qq.com',
        style_contact
    ))
    story.append(Paragraph(
        'GitHub: <a href="https://github.com/kajykk" color="#0f3460">https://github.com/kajykk</a> | '
        '<b>AI 作品</b>: <a href="https://github.com/kajykk/bysj" color="#0f3460">https://github.com/kajykk/bysj</a>',
        style_contact
    ))
    story.append(Paragraph(
        '求职意向: 全栈开发实习生（AI 编程方向）| 可实习时长: 4 个月',
        style_contact
    ))
    story.append(divider())

    # Education
    story.append(Paragraph("教育背景", style_section))
    story.append(Paragraph(
        "<b>湖北商贸学院</b> | 数据科学与大数据技术 | 本科 | 2022.09 - 2026.06",
        style_subheader
    ))
    story.append(make_bullet("主修课程: 数据结构、Python 程序设计、机器学习基础、数据库原理、数据仓库与数据挖掘"))
    story.append(make_bullet("学业表现: 专业排名前 10%，大学英语六级 460 分"))

    # Skills
    story.append(Paragraph("专业技能", style_section))
    story.append(Paragraph("<b>AI 编码工具（核心优势 · 重度用户）</b>", style_subheader))
    story.append(make_bullet(
        "<b>重度使用 Trae IDE、Cursor、Claude Code、GitHub Copilot</b>，能借助 AI 完成需求拆解、代码生成、调试、重构与测试补全，加速从想法到交付的全流程"
    ))
    story.append(make_bullet(
        "沉淀 <b>35+ 个 AI 协作 Skill</b>（Ralph 规划系列 / Sysopt 优化系列 / 审计协调器），让 AI 作为工程伙伴而非补全工具"
    ))
    story.append(make_bullet(
        "具备 AI 驱动的 6 阶段开发流程经验: 需求拆解 → 架构设计 → 任务规划 → 实现+测试 → 审计 → 验收"
    ))

    story.append(Paragraph("<b>全栈开发</b>", style_subheader))
    story.append(make_bullet("前端: Vue 3 (Composition API) + TypeScript + Vite + Pinia + Element Plus + ECharts"))
    story.append(make_bullet("后端: Python + FastAPI + SQLAlchemy 2.0 (async) + Pydantic + Celery + Redis"))
    story.append(make_bullet("数据库: PostgreSQL / SQLite + Alembic 迁移"))
    story.append(make_bullet("工程化: Git、Docker、GitHub Actions CI/CD、Vitest、Playwright、pytest"))

    story.append(Paragraph("<b>数据与 ML</b>", style_subheader))
    story.append(make_bullet("Python 数据处理: Pandas、NumPy、scikit-learn"))
    story.append(make_bullet("ML 工程: 模型训练、融合、漂移检测（PSI/KL）、金丝雀发布、自动回滚"))
    story.append(make_bullet("数据可视化: Matplotlib、Seaborn、ECharts"))

    # Project - DWS
    story.append(Paragraph("项目经历", style_section))
    story.append(Paragraph(
        "<b>心理健康风险评估系统（DWS）</b> | 全栈开发 / AI 辅助独立交付",
        style_subheader
    ))
    story.append(Paragraph(
        '<b>AI 作品链接</b>: <a href="https://github.com/kajykk/bysj" color="#0f3460">https://github.com/kajykk/bysj</a>',
        style_meta
    ))
    story.append(Paragraph(
        "<b>技术栈</b>: Vue 3 + TypeScript + FastAPI + SQLAlchemy + Celery + Redis + PostgreSQL + Docker",
        style_meta
    ))
    story.append(Paragraph("<b>时间</b>: 2026.03 - 2026.07", style_meta))
    story.append(Paragraph(
        "<b>项目规模</b>: 24 个 API 路由 · 46 个核心模块 · 33 个业务服务 · 27 个 ML 文件 · 9 个 Docker 服务 · ~2000 测试用例",
        style_body
    ))
    story.append(Paragraph("<b>AI 工具关键贡献</b>:", style_body))
    story.append(make_bullet(
        "使用 <b>Trae IDE + 35 个个人 Skill 库</b> 独立完成从需求分析、架构设计（C4 模型 + 10 个 ADR）、前后端实现到测试验证的端到端开发"
    ))
    story.append(make_bullet(
        "后端基于 FastAPI 构建异步 API 服务，集成 Celery 异步任务、Redis 缓存/pubsub、WebSocket 实时推送、多模态 ML 融合引擎"
    ))
    story.append(make_bullet(
        "前端基于 Vue 3 + TypeScript 构建 3 端界面（用户/咨询师/管理员），含虚拟列表、骨架屏、PWA 离线支持、i18n 国际化"
    ))
    story.append(make_bullet(
        "<b>金丝雀发布引擎</b>: AI 辅助完成 200+ 行 ML 治理代码（PSI/KL 漂移检测 + 自动回滚 + 断路器熔断）"
    ))
    story.append(make_bullet(
        "<b>可观测性集成</b>: AI 设计 Prometheus metrics + Grafana dashboard + Sentry 告警规则"
    ))
    story.append(make_bullet(
        "<b>前端性能优化</b>: AI 辅助虚拟列表/懒加载/骨架屏，Lighthouse Performance 从 35 提升至 98"
    ))
    story.append(Paragraph("<b>交付质量证据</b>:", style_body))
    story.append(make_bullet(
        "AI 驱动 6 阶段审计闭环: 发现 164 个问题，关闭 121 个（P0/P1/P2 全部清零），详见仓库审计文档"
    ))
    story.append(make_bullet(
        "契约测试 100% 通过（620/620），Lighthouse Performance 98 / Accessibility 100，FCP 0.8s / LCP 1.0s"
    ))
    story.append(make_bullet(
        "9 条 GitHub Actions 流水线（契约/E2E/性能/容器扫描/依赖扫描/质量门禁）"
    ))
    story.append(make_bullet(
        "使用 AI 工具完成安全修复: 路径遍历防护、TOCTOU 竞态修复（原子 UPDATE）、PII Fernet 加密、Dropout 线程安全"
    ))

    # Project - Employee system
    story.append(Paragraph(
        "<b>员工信息管理系统</b> | 后端开发实习生 | 2025.07 - 2025.10",
        style_subheader
    ))
    story.append(Paragraph("<b>技术栈</b>: SpringBoot + MyBatis + MySQL", style_meta))
    story.append(make_bullet("与企业方深入沟通，将业务需求转化为系统功能方案"))
    story.append(make_bullet("负责后端核心功能开发，使用 MyBatis 实现 MySQL 增删改查，通过声明式事务保证数据一致性"))
    story.append(make_bullet("使用 SpringBoot 整合 MyBatis 和 SpringMVC 搭建架构，完成单元测试并修复 3 个数据异常 Bug"))
    story.append(make_bullet("系统上线后查询效率较原手工管理提升 80%，获得企业方认可"))

    # Internship
    story.append(Paragraph("实习经历", style_section))
    story.append(Paragraph(
        "<b>武汉中软卓越科技有限公司</b> | 数据分析实习生 | 2025.03 - 2025.06",
        style_subheader
    ))
    story.append(Paragraph("<b>项目</b>: 高校教育大数据整合与分析系统", style_meta))
    story.append(Paragraph("<b>技术栈</b>: Hadoop、Hive、PyHive、Python、Pandas、Matplotlib", style_meta))
    story.append(make_bullet("主动与教学管理部门对接，调研数据现状与业务需求，提出数据管理解决方案"))
    story.append(make_bullet("使用 Pandas 对 10 万+条多源数据进行清洗、异常剔除与标准化处理"))
    story.append(make_bullet("基于 Hadoop 搭建分布式存储，构建 Hive 数据仓库，编写 HiveSQL 完成多维度查询分析"))
    story.append(make_bullet("利用 Matplotlib/Seaborn 制作可视化图表，以数据报告形式向管理部门汇报"))

    # Campus
    story.append(Paragraph("校园经历", style_section))
    story.append(Paragraph(
        "<b>图书馆管理委员会外联部部长</b> | 2023.09 - 2025.06",
        style_subheader
    ))
    story.append(make_bullet("对接 5 家校外书店和 2 家出版社，达成 3 项图书捐赠合作，争取 1200 余册图书资源"))
    story.append(make_bullet("组织 4 次跨校社团交流，锻炼了出色的跨部门沟通协调能力"))

    story.append(Paragraph(
        "<b>北京大学医学部心理咨询基础研学营</b> | 2025.01 - 2025.02",
        style_subheader
    ))
    story.append(make_bullet("系统学习心理咨询基础理论等 8 门核心课程，获得结业证书"))
    story.append(make_bullet("提升共情能力，有助于在 DWS 项目中理解心理健康业务需求"))

    # Self evaluation
    story.append(Paragraph("自我评价", style_section))
    story.append(make_bullet(
        "<b>AI 编程重度用户</b>: 使用 Trae/Cursor/Claude Code 完成完整项目交付，沉淀 35+ 个 AI 协作 Skill，将 AI 作为工程伙伴而非补全工具"
    ))
    story.append(make_bullet(
        "<b>全栈交付能力</b>: 独立完成 DWS 系统从需求到上线全流程，覆盖前端+后端+ML+DevOps，~2000 测试用例验证质量"
    ))
    story.append(make_bullet(
        "<b>工程质量管理</b>: AI 驱动 6 阶段审计闭环（164 问题/121 关闭/P0-P2 清零），重视测试、安全与可观测性"
    ))
    story.append(make_bullet(
        "<b>沟通与快速学习</b>: 外联部部长经验培养跨部门沟通能力，研学营经历加深对心理健康业务的理解"
    ))

    return story


def main():
    output_path = r"e:\code\bysj\邝振华_简历_AI全栈优化版.pdf"
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.2*cm, bottomMargin=1.2*cm,
        title="邝振华 - 简历 (AI 全栈优化版)",
        author="邝振华"
    )
    story = build_resume()
    doc.build(story)
    print(f"PDF generated: {output_path}")
    print(f"File size: {os.path.getsize(output_path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
