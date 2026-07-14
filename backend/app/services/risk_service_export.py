from __future__ import annotations

import asyncio
import csv
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select

from app.models.risk import RiskAssessment


class ExportMixin:
    """风险数据导出相关方法 Mixin。

    包含 CSV/JSON/PDF 三种格式的风险评估导出方法,以及 PDF 异步生成的并发限流逻辑。

    依赖主类 RiskService 提供 `self.db`，以及主模块 risk_service 提供的模块级工具:
    - `_sanitize_csv_cell`: CSV 公式注入防护
    - `_pdf_executor`: PDF 生成线程池
    - `_pdf_semaphore`: PDF 生成并发限流信号量

    这些模块级工具通过延迟导入 (方法内 import) 访问, 避免与主模块形成循环导入。
    还依赖 ReportMixin 提供的 `_since_datetime`、`_level_to_severity`、`_build_advice`
    staticmethod (通过 self 访问)。
    """

    async def export_risk(self, user_id: int, days: int, fmt: str) -> dict:
        since = self._since_datetime(days)
        stmt = (
            select(RiskAssessment)
            .where(
                RiskAssessment.user_id == user_id, RiskAssessment.created_at >= since
            )
            .order_by(RiskAssessment.created_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        raw_items = [
            {
                "id": row.id,
                "risk_score": round(row.risk_score, 2),
                "risk_level": row.risk_level,
                "severity": self._level_to_severity(row.risk_level),
                "assessment_type": row.assessment_type,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

        normalized_fmt = (fmt or "csv").strip().lower()
        if normalized_fmt == "json":
            return {"format": "json", "items": raw_items}

        if normalized_fmt == "pdf":
            pdf_bytes = await self._generate_pdf_report_async(user_id, raw_items)
            return {
                "format": "pdf",
                "filename": f"risk_report_{user_id}_{days}d.pdf",
                "content": pdf_bytes,
            }

        # C-Svc-4 修复：对 raw_items 中所有 str 字段做 CSV 公式注入防护
        # 延迟导入避免与主模块 risk_service.py 形成循环导入
        from app.services.risk_service import _sanitize_csv_cell

        sanitized_items = [
            {k: _sanitize_csv_cell(v) for k, v in item.items()} for item in raw_items
        ]

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id",
                "risk_score",
                "risk_level",
                "severity",
                "assessment_type",
                "created_at",
            ],
        )
        writer.writeheader()
        writer.writerows(sanitized_items)

        return {
            "format": "csv",
            "filename": f"risk_export_{user_id}_{days}d.csv",
            "content": output.getvalue(),
        }

    def _generate_pdf_report(self, user_id: int, items: list[dict]) -> bytes:
        # C-Svc-5 修复：使用 with 上下文管理 BytesIO，确保异常或正常返回时都能释放底层缓冲。
        # 原实现 buffer = io.BytesIO() 后未 close()，在 PDF 生成异常时（reportlab 抛错）
        # 会导致内存中 BytesIO 实例无法立即回收，大量并发导出可能加剧内存压力。
        with io.BytesIO() as buffer:
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                topMargin=20 * mm,
                bottomMargin=20 * mm,
                leftMargin=15 * mm,
                rightMargin=15 * mm,
            )
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "ReportTitle", parent=styles["Title"], fontSize=18, spaceAfter=12
            )
            heading_style = ParagraphStyle(
                "ReportHeading", parent=styles["Heading2"], fontSize=14, spaceAfter=8
            )
            body_style = ParagraphStyle(
                "ReportBody", parent=styles["Normal"], fontSize=10, leading=14
            )

            elements = []
            elements.append(Paragraph("Risk Assessment Report", title_style))
            elements.append(
                Paragraph(
                    f"User ID: {user_id}  |  Report Period: {len(items)} records",
                    body_style,
                )
            )
            elements.append(Spacer(1, 10 * mm))

            if items:
                table_data = [["ID", "Risk Score", "Level", "Severity", "Type", "Date"]]
                for item in items:
                    table_data.append(
                        [
                            str(item["id"]),
                            str(item["risk_score"]),
                            str(item["risk_level"]),
                            item["severity"],
                            item["assessment_type"],
                            item["created_at"][:10],
                        ]
                    )
                table = Table(table_data, colWidths=[30, 60, 40, 60, 80, 80])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#409EFF")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            (
                                "ROWBACKGROUNDS",
                                (0, 1),
                                (-1, -1),
                                [colors.white, colors.HexColor("#F5F7FA")],
                            ),
                        ]
                    )
                )
                elements.append(table)
            else:
                elements.append(
                    Paragraph(
                        "No risk assessment records found in this period.", body_style
                    )
                )

            elements.append(Spacer(1, 10 * mm))
            if items:
                latest = items[-1]
                elements.append(Paragraph("Latest Assessment Summary", heading_style))
                elements.append(
                    Paragraph(
                        f"Risk Score: {latest['risk_score']}  |  Level: {latest['risk_level']}  |  Severity: {latest['severity']}",
                        body_style,
                    )
                )
                advice = self._build_advice(latest["risk_level"])
                elements.append(Paragraph("Recommendations:", heading_style))
                for a in advice:
                    elements.append(Paragraph(f"  - {a}", body_style))

            doc.build(elements)
            return buffer.getvalue()

    async def _generate_pdf_report_async(
        self, user_id: int, items: list[dict]
    ) -> bytes:
        # RES-P2-004: 在 submit 前获取 Semaphore, 限制待处理 PDF 任务数
        # 使用 run_in_executor 包装同步 _generate_pdf_report, Semaphore 在调用线程获取/释放
        loop = asyncio.get_running_loop()

        # 延迟导入避免与主模块 risk_service.py 形成循环导入
        from app.services.risk_service import _pdf_executor, _pdf_semaphore

        # 在 executor 线程中获取/释放 Semaphore, 避免 async 事件循环阻塞
        def _pdf_with_semaphore() -> bytes:
            _pdf_semaphore.acquire()
            try:
                return self._generate_pdf_report(user_id, items)
            finally:
                _pdf_semaphore.release()

        return await loop.run_in_executor(_pdf_executor, _pdf_with_semaphore)
