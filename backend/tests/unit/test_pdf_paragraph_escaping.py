"""P0-FIX-2026-10-11: PDF 报告中用户可控文本必须先 XML 转义再交给 Paragraph。

背景（来自 2026-10-11 全量源码审查）：

``reportlab.platypus.Paragraph`` 会把传入字符串当作 **mini-XML** 解析，
``<b>`` / ``<font ...>`` / ``<br/>`` 等内联标记会被真正解释。
``pdf_report_service`` 的 title / subtitle / user_info / sections /
recommendations 全部来自业务数据，含自由文本（学生姓名、班级、咨询师备注、
问卷开放式回答），可以合法携带 ``<`` ``>`` ``&``。

本机 reportlab 4.4.10 实测（本文件每条断言的实测依据）：
* ``'张三 <b>的测评报告'`` → ``ValueError: Parse error: saw </para>``
  → ``doc.build()`` 抛异常 → **整份 PDF 生成失败**（可用性打击）。
* ``'<font size="30" color="red">转介</font>'`` → 内容流出现 ``30 Tf``
  与 ``1 0 0 rg`` → **排版指令被真正执行**（内容篡改面）。
* 裸 ``&`` 与 ``< c >`` 形式的文本 reportlab 可容忍，不构成失败。

修复：新增 ``_para_text()``，所有进 Paragraph 的业务文本统一转义。
表格单元格不走 XML 解析（字符串按字面绘制），故**不**转义，否则 ``&`` 会
被显示成 ``&amp;``。
"""

from __future__ import annotations

import pytest

from app.services.pdf_report_service import (
    PDFReportService,
    ReportData,
    _para_text,
)

# 未闭合标签：修复前会让 reportlab 解析失败（ValueError: Parse error）
UNCLOSED_TAG_TITLE = "张三 <b>的测评报告"
# 排版指令注入：修复前会被真正套用（30 Tf / 1 0 0 rg 出现在内容流）
FONT_INJECTION_REC = '建议 <font size="30" color="red">立即转介</font>'


@pytest.fixture
def service():
    return PDFReportService()


@pytest.fixture
def reportlab_available(service):
    if not service._check_reportlab_available():
        pytest.skip("reportlab 未安装, 跳过 PDF 生成级断言")


@pytest.fixture
def uncompressed_pdf(monkeypatch):
    """关闭页面压缩，使内容流里的 Tf / rg 算子可以被字节级断言。"""
    import reportlab.rl_config as rl_config

    monkeypatch.setattr(rl_config, "pageCompression", 0, raising=False)


def _hostile_report_data() -> ReportData:
    return ReportData(
        title=UNCLOSED_TAG_TITLE,
        subtitle="子标题 & <未闭合",
        sections=[{"title": "第一节 <i>", "content": "备注: A&b < c > d"}],
        recommendations=[FONT_INJECTION_REC, "普通建议 & 复诊"],
        user_info={"姓名": "<张三>", "班级": "高三(1) & 2班"},
        generated_at="2026-10-11 & <test>",
    )


class TestParaTextEscaping:
    """_para_text 的转义语义。"""

    def test_escapes_angle_brackets_and_ampersand(self):
        assert _para_text("a < b & c > d") == "a &lt; b &amp; c &gt; d"

    def test_escapes_unclosed_tag(self):
        out = _para_text(UNCLOSED_TAG_TITLE)
        assert "<b>" not in out
        assert "&lt;b&gt;" in out

    def test_none_and_non_str_are_coerced(self):
        assert _para_text(None) == ""
        assert _para_text(42) == "42"

    def test_plain_text_unchanged(self):
        assert _para_text("普通报告标题") == "普通报告标题"


class TestGeneratePdfWithHostileText:
    """含特殊字符的业务文本不得让 PDF 生成失败、不得被当作排版指令。"""

    def test_generate_pdf_succeeds_with_unclosed_tag(
        self, service, reportlab_available
    ):
        """修复前：未闭合 <b> 让 doc.build() 抛 ValueError → success=False。"""
        result = service.generate_pdf(_hostile_report_data())
        assert result.success is True, (
            f"含未闭合标签的业务文本导致 PDF 生成失败: {result.error_message}"
        )
        assert result.pdf_bytes[:5] == b"%PDF-"

    def test_font_injection_is_not_interpreted(
        self, service, reportlab_available, uncompressed_pdf
    ):
        """修复前：<font size=30 color=red> 被真正套用（内容流出现 30 Tf / 1 0 0 rg）。"""
        result = service.generate_pdf(_hostile_report_data())
        assert result.success is True
        content = result.pdf_bytes
        assert b"30 Tf" not in content, (
            "注入的 <font size=30> 被执行 —— 业务文本未经转义即进入 Paragraph"
        )
        assert b"1 0 0 rg" not in content, "注入的 color=red 被执行"

    def test_generate_pdf_stream_succeeds_with_hostile_text(
        self, service, reportlab_available
    ):
        """流式分支是复制粘贴的同一段代码，同样需要转义。"""
        result = service.generate_pdf_stream(_hostile_report_data())
        assert result.success is True, (
            f"流式 PDF 分支同样需要转义: {result.error_message}"
        )
        assert result.file_size > 0
        if result.stream is not None:
            result.stream.close()

    def test_benign_report_still_succeeds(self, service, reportlab_available):
        """转义不得破坏正常报告（防过度转义导致 PDF 整体回退）。"""
        data = ReportData(
            title="心理健康测评报告",
            subtitle="2026 年秋季学期",
            sections=[{"title": "量表结果", "content": "PHQ-9: 12 分（中度）"}],
            recommendations=["建议两周后复评"],
            user_info={"姓名": "李四", "班级": "高二(3)班"},
            generated_at="2026-10-11",
        )
        result = service.generate_pdf(data)
        assert result.success is True
        assert result.pdf_bytes[:5] == b"%PDF-"


class TestRiskExportPdfEscaping:
    """risk_service_export 的 Latest Assessment Summary 同样需要转义。"""

    def test_latest_summary_uses_para_text(self):
        from app.services import risk_service_export as export_module

        with open(export_module.__file__, encoding="utf-8") as fh:
            source = fh.read()
        assert "_para_text(latest['severity'])" in source, (
            "risk_service_export 的 Latest Assessment Summary 仍直接拼接未转义值"
        )
        assert "_para_text(latest['risk_level'])" in source
