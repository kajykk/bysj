"""REV-2026-10-20 S5 回归：PDF 报告必须真正渲染中文。

改前两份 reportlab 生成路径（``generate_pdf`` / ``generate_pdf_stream``）
都用 ``getSampleStyleSheet()`` 的默认 Helvetica，且全仓没有
``registerFont`` / ``TTFont`` / ``UnicodeCIDFont`` 调用。结果是标题、
"User: 张三"、section 正文、建议列表全是空白/方块，而 ``_validate_pdf``
只检查 ``%PDF`` 头，仍返回 ``success=True`` —— 故障完全静默。

断言对象是**真实产物**（附录 C）：
1. 生成 PDF 的字节里出现 CJK 字体名；
2. 用 pypdf 抽取文本，中文原文可读（改前抽取为空/乱码）；
3. 流式路径与主路径行为一致（两处复制粘贴，漏改一处即回归）。
"""

from __future__ import annotations

import io

from pypdf import PdfReader

from app.services.pdf_report_service import PDFReportService, ReportData


def _report() -> ReportData:
    return ReportData(
        title="抑郁风险评估报告",
        subtitle="2026 年 10 月 随访报告",
        generated_at="2026-10-20 02:00",
        user_info={"用户": "张三", "班级": "计算机 2022 级 1 班"},
        sections=[
            {"title": "咨询结论", "content": "近两周情绪低落，睡眠质量下降，建议尽快复诊。"},
            {"title": "量表解读", "content": "PHQ-9 总分 17，属于中重度抑郁范围。"},
        ],
        tables=[
            {
                "headers": ["维度", "得分", "风险"],
                "rows": [["情绪", "8", "高"], ["睡眠", "5", "中"]],
            }
        ],
        recommendations=["保持规律作息", "每周与咨询师沟通一次"],
    )


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_generate_pdf_renders_chinese():
    result = PDFReportService().generate_pdf(_report())

    assert result.success is True, result.error_message
    assert result.pdf_bytes
    # 字体资源真实存在（改前只有 Helvetica / ZapfDingbats）
    assert b"STSong-Light" in result.pdf_bytes

    text = _extract_text(result.pdf_bytes)
    assert "抑郁风险评估报告" in text
    assert "张三" in text
    assert "建议尽快复诊" in text
    # 表格单元格（走 Table 而非 Paragraph，需要单独设置 FONTNAME）
    assert "情绪" in text
    assert "保持规律作息" in text


def test_generate_pdf_stream_renders_chinese():
    result = PDFReportService().generate_pdf_stream(_report())

    assert result.success is True, result.error_message
    assert result.stream is not None
    pdf_bytes = result.stream.getvalue()
    assert b"STSong-Light" in pdf_bytes

    text = _extract_text(pdf_bytes)
    assert "抑郁风险评估报告" in text
    assert "量表解读" in text
    assert "睡眠" in text
