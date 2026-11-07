"""L-07 修复：报告导出模块共用的文本转义工具（单一实现）。

原先 ``risk_service_export.py`` 与 ``pdf_report_service.py`` 各自定义了一份
逐字相同的 ``_para_text``，转义规则各自演进时会漂移，故收敛到本模块。
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape as _xml_escape


def _para_text(value: Any) -> str:
    """P0-FIX-2026-10-11: 业务文本交给 ReportLab ``Paragraph`` 前必须转义。

    ``Paragraph`` 会把传入字符串当作 mini-XML 解析（``<b>`` / ``<i>`` /
    ``<font ...>`` / ``<br/>`` 等内联标记会被真正解释）。业务数据（severity /
    risk_level、学生姓名、咨询师备注、问卷开放式回答等自由文本）可以合法携带
    ``<`` ``>`` ``&``：裸 ``&`` 或未闭合标签会让 reportlab 解析失败、整份 PDF
    导出失败；攻击者还可借 ``<font ...>`` 注入排版指令篡改报告结论。

    注：``Table`` 的单元格不走 XML 解析（字符串按字面绘制），因此**不要**对
    表格单元格做转义，否则 ``&`` 会被显示成 ``&amp;``；本函数只用于 Paragraph 输入。
    """
    if value is None:
        return ""
    return _xml_escape(str(value))
