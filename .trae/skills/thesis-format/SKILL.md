---
name: "thesis-format"
description: "毕业论文格式修改。当用户需要修改毕业论文格式、调整标题层级、设置页眉页脚、生成目录、规范图表编号或参考文献格式时调用。"
---

# 毕业论文格式修改技能 (thesis-format)

## Description

基于湖北商贸学院本科毕业论文模板开发的格式修改技能。能够识别并处理毕业论文中的常见格式元素，包括标题层级、段落样式、引用格式、页眉页脚、目录生成、图表编号与标题规范等。根据学术论文的标准格式要求，对文档进行自动化或半自动化的格式调整，提高论文格式修改的效率和准确性。

## 适用场景

当用户需要以下操作时，应立即调用此技能：
- 修改毕业论文格式
- 调整论文标题层级样式
- 设置页眉页脚和页码
- 生成或更新目录
- 规范图表编号和标题
- 调整参考文献格式
- 检查论文格式是否符合模板要求
- 批量修改段落样式

---

## 一、模板格式规范速查表

以下是从模板文件中提取的完整格式规范，所有修改操作必须严格遵循。

### 1.1 页面设置

| 项目 | 值 | 说明 |
|------|-----|------|
| 纸张大小 | A4 (11906×16838 twips) | 即 210mm × 297mm |
| 上边距 | 1440 twips (2.54cm) | |
| 下边距 | 1440 twips (2.54cm) | |
| 左边距 | 1800 twips (3.17cm) | |
| 右边距 | 1800 twips (3.17cm) | |
| 页眉距边界 | 851 twips (1.49cm) | |
| 页脚距边界 | 992 twips (1.74cm) | |
| 装订线 | 0 | |
| 文档网格 | lines, linePitch=312 | |

### 1.2 分节结构

文档分为以下节（Section），每节有不同的页眉页脚和页码设置：

| 节 | 内容 | 页眉 | 页脚/页码 |
|----|------|------|-----------|
| 第1节 | 封面（中文） | 无 | 无 |
| 第2节 | 封面（英文） | 无 | 无 |
| 第3节 | 原创性声明 | 无 | 无 |
| 第4节 | 摘要 + ABSTRACT | 无 | footer2.xml（居中页码，小五号） |
| 第5节 | 目录 | 无 | footer2.xml（居中页码，小五号） |
| 第6节 | 正文（绪论～致谢） | header1.xml（"湖北商贸学院本科毕业论文(设计)"） | footer3.xml（居中页码，从1开始，小四号宋体） |

### 1.3 默认字体与正文样式

| 项目 | 值 |
|------|-----|
| 默认中文字体 | DengXian（等线） |
| 默认英文字体 | DengXian |
| 默认CS字体 | Times New Roman |
| 正文字号 | 10.5pt (sz=21)，即五号字 |
| 正文字号CS | 11pt (szCs=22) |
| 对齐方式 | 两端对齐 (both) |
| 行距 | 固定值 23pt (line=460, exact) |
| 首行缩进 | 2字符 (firstLineChars=200) |

### 1.4 标题层级样式

#### 标题1 (heading 1) — 章标题

| 项目 | 值 |
|------|-----|
| 样式ID | 2 |
| 字号 | 18pt (sz=36)，即小二号 |
| 字体 | 中文：SimHei（黑体）；英文：继承默认 DengXian |
| 加粗 | 是 (b, bCs) |
| 对齐 | 左对齐 (left) |
| 行距 | 固定值 23pt (line=460, exact) |
| 段前段后 | 各 25pt (before=50, after=50) |
| 大纲级别 | Level 0 |
| keepNext | 是 |
| keepLines | 是 |
| 编号格式 | "1 绪 论"、"2 系统分析" 等（数字+空格+标题） |
| 示例 | `1 绪 论` |

#### 标题2 (heading 2) — 节标题

| 项目 | 值 |
|------|-----|
| 样式ID | 3 |
| 字号 | 14pt (sz=28)，即四号 |
| 字体 | 中文：SimHei（黑体）；英文：DengXian Light |
| 加粗 | 是 (b, bCs) |
| 对齐 | 继承（两端对齐） |
| 行距 | 固定值 23pt (line=460, exact) |
| 段前段后 | 各 25pt (before=50, after=50) |
| 大纲级别 | Level 1 |
| keepNext | 是 |
| keepLines | 是 |
| 编号格式 | "1.1 课题的来源" 等 |
| 示例 | `1.1 课题的来源` |

#### 标题3 (heading 3) — 小节标题

| 项目 | 值 |
|------|-----|
| 样式ID | 4 |
| 字号 | 12pt (sz=24)，即小四号 |
| 字体 | 中文：SimHei（黑体） |
| 加粗 | 是 (b, bCs) |
| 对齐 | 左对齐 (left) |
| 行距 | 固定值 23pt (line=460, exact) |
| 段前段后 | 无 |
| 大纲级别 | Level 2 |
| keepNext | 是 |
| keepLines | 是 |
| 示例 | `1.3.1 国内研究现状` |

### 1.5 正文段落样式

| 项目 | 值 |
|------|-----|
| 字号 | 12pt (sz=24)，即小四号 |
| 字体 | 中文：SimSun（宋体）；英文：Times New Roman |
| 行距 | 固定值 23pt (line=460, exact) |
| 首行缩进 | 2字符 (firstLineChars=200, firstLine=480) |
| 对齐 | 两端对齐 |

### 1.6 摘要标题样式

| 项目 | 值 |
|------|-----|
| 字号 | 18pt (sz=36)，即小二号 |
| 字体 | 中文：SimHei（黑体）；英文：Times New Roman |
| 加粗 | 是 |
| 对齐 | 居中 |
| 首行缩进 | 2字符 |
| 行距 | 固定值 23pt |

### 1.7 关键词样式

| 项目 | 值 |
|------|-----|
| 标签"关键词：" | 加粗，宋体，小四号 |
| 关键词内容 | 宋体，小四号 |
| 分隔符 | 中文分号"；" |

### 1.8 图表标题样式 (caption)

| 项目 | 值 |
|------|-----|
| 样式ID | 5 |
| 字号 | 继承正文 (szCs=20) |
| 字体 | 英文：Times New Roman；中文：SimHei（黑体） |
| 行距 | 固定值 23pt (line=460, exact) |
| 首行缩进 | 2字符 (firstLineChars=200) |
| 对齐 | 居中 |
| 编号格式 | 图X-Y / 表X-Y（X=章号，Y=序号） |
| 示例 | `图3-1 管理员用例图` |

### 1.9 目录样式

| 样式 | 字体 | 字号 | 缩进 |
|------|------|------|------|
| TOC 1 (toc 1) | SimHei | 12pt (sz=24) | 无 |
| TOC 2 (toc 2) | SimSun | 12pt (sz=24) | 左缩进 200 twips |
| TOC 3 (toc 3) | SimSun | 12pt (sz=24) | 左缩进 400 twips |

目录生成指令：`TOC \o "1-3" \h \z \u`（显示1-3级标题，含超链接）

### 1.10 页眉样式

| 项目 | 值 |
|------|-----|
| 样式ID | 8 (header) |
| 字号 | 9pt (sz=18)，即小五号 |
| 对齐 | 居中 |
| 内容 | "湖北商贸学院本科毕业论文(设计)" |
| 字体 | SimSun（宋体） |
| 下边框 | 单线 (single, sz=4) |
| 首行缩进 | 2字符 |

### 1.11 页脚样式

| 类型 | 字号 | 对齐 | 内容 |
|------|------|------|------|
| 摘要/目录页脚 (footer2) | 小五号 (继承) | 居中 | PAGE 域代码（自动页码） |
| 正文页脚 (footer3) | 小四号 (sz=24) | 居中 | PAGE 域代码（从1开始），Times New Roman + SimSun |

### 1.12 参考文献样式

| 项目 | 值 |
|------|-----|
| 标题样式 | heading 1 (居中) |
| 条目样式 | List Paragraph (styleId=17) |
| 编号格式 | [%1]（方括号+数字） |
| 字号 | 小四号 (sz=24) |
| 字体 | Times New Roman + SimSun |
| 行距 | 固定值 23pt |
| 编号缩进 | 左缩进 440 twips，悬挂 440 twips |

### 1.13 表格样式

#### 三线表 (styleId=22)

| 项目 | 值 |
|------|-----|
| 基于样式 | Normal Table |
| 顶线 | 单线，12磅 (sz=12) |
| 底线 | 单线，12磅 (sz=12) |
| 首行底线 | 单线，4磅 (sz=4) |
| 其他边框 | 无 |
| 字体 | SimSun（宋体） |

#### 表格字体样式 (styleId=23)

| 项目 | 值 |
|------|-----|
| 字体 | Times New Roman + SimSun |
| 字号 | 继承正文 (szCs=21) |
| 行距 | 固定值 17pt (line=340, exact) |

### 1.14 封面格式

| 项目 | 值 |
|------|-----|
| 校名图片 | 居中，上方 |
| 论文类型标题 | "本科毕业论文（设计）"，36pt (sz=72)，SimHei，加粗，居中 |
| 论文题目 | 22pt (sz=44)，SimSun/SimHei 加粗，左对齐，首行缩进 |
| 信息表格 | 两列，居中，14pt (sz=28)，SimHei，即四号 |
| 日期 | 10pt (sz=20)，SimSun，加粗 |

---

## 二、操作工作流

当用户请求修改论文格式时，按以下流程执行：

### 2.1 格式诊断（第一步）

在修改之前，先对文档进行全面诊断：

```bash
# Step 1: 解压文档
python scripts/unpack.py input.docx unpacked/

# Step 2: 检查关键格式元素
# - 读取 styles.xml 检查样式定义
# - 读取 document.xml 检查段落样式使用
# - 读取 header/footer 文件检查页眉页脚
# - 读取 settings.xml 检查页面设置
# - 读取 numbering.xml 检查编号定义
```

**诊断清单：**

1. **页面设置检查**
   - [ ] 纸张是否为A4 (11906×16838)
   - [ ] 页边距是否符合规范（上下2.54cm，左右3.17cm）
   - [ ] 页眉页脚距边界是否正确

2. **样式检查**
   - [ ] heading 1/2/3 样式是否正确定义
   - [ ] 正文段落是否有首行缩进
   - [ ] 行距是否为固定值23pt
   - [ ] 字体是否正确（中文宋体/黑体，英文Times New Roman）

3. **分节检查**
   - [ ] 封面、摘要、目录、正文是否正确分节
   - [ ] 各节页眉页脚是否正确
   - [ ] 页码是否正确（摘要目录用罗马数字，正文从1开始）

4. **目录检查**
   - [ ] 目录域代码是否正确 (TOC \o "1-3" \h \z \u)
   - [ ] 目录样式是否正确

5. **图表检查**
   - [ ] 图表标题是否使用caption样式
   - [ ] 编号格式是否为"图X-Y"或"表X-Y"
   - [ ] 表格是否使用三线表样式

6. **参考文献检查**
   - [ ] 是否使用List Paragraph样式
   - [ ] 编号格式是否为[%1]
   - [ ] 字体字号是否正确

### 2.2 格式修复操作

#### 修复正文段落格式

在 document.xml 中，查找正文段落（没有 pStyle 或 pStyle="1" 的段落），确保：

```xml
<!-- 正确的正文段落格式 -->
<w:pPr>
  <w:spacing w:line="460" w:lineRule="exact"/>
  <w:ind w:firstLine="480" w:firstLineChars="200"/>
  <w:rPr>
    <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
    <w:sz w:val="24"/>
  </w:rPr>
</w:pPr>
```

#### 修复标题格式

**标题1（章标题）** 应使用 `pStyle w:val="2"`：
```xml
<w:pPr>
  <w:pStyle w:val="2"/>
  <w:spacing w:before="156" w:after="156"/>
</w:pPr>
```

**标题2（节标题）** 应使用 `pStyle w:val="3"`：
```xml
<w:pPr>
  <w:pStyle w:val="3"/>
  <w:spacing w:before="156" w:after="156"/>
</w:pPr>
```

**标题3（小节标题）** 应使用 `pStyle w:val="4"`：
```xml
<w:pPr>
  <w:pStyle w:val="4"/>
</w:pPr>
```

#### 修复图表标题格式

图表标题应使用 `pStyle w:val="5"`（caption样式）：
```xml
<w:pPr>
  <w:pStyle w:val="5"/>
  <w:ind w:firstLine="420"/>
</w:pPr>
```

#### 修复参考文献格式

参考文献条目应使用 `pStyle w:val="17"`（List Paragraph）+ 编号：
```xml
<w:pPr>
  <w:pStyle w:val="17"/>
  <w:numPr>
    <w:ilvl w:val="0"/>
    <w:numId w:val="1"/>
  </w:numPr>
  <w:spacing w:line="460" w:lineRule="exact"/>
  <w:ind w:firstLineChars="0"/>
  <w:rPr>
    <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
    <w:sz w:val="24"/>
  </w:rPr>
</w:pPr>
```

#### 修复页眉页脚

**正文页眉** (header1.xml)：
```xml
<w:p>
  <w:pPr>
    <w:pStyle w:val="8"/>
    <w:pBdr>
      <w:bottom w:val="single" w:color="auto" w:sz="4" w:space="1"/>
    </w:pBdr>
    <w:spacing w:line="460" w:lineRule="exact"/>
    <w:ind w:firstLine="360" w:firstLineChars="200"/>
    <w:rPr>
      <w:rFonts w:eastAsia="SimSun"/>
    </w:rPr>
  </w:pPr>
  <w:r>
    <w:rPr>
      <w:rFonts w:hint="eastAsia" w:eastAsia="SimSun"/>
    </w:rPr>
    <w:t>湖北商贸学院本科毕业论文(设计)</w:t>
  </w:r>
</w:p>
```

**正文页脚** (footer3.xml) — 居中页码，从1开始：
```xml
<w:p>
  <w:pPr>
    <w:pStyle w:val="7"/>
    <w:jc w:val="center"/>
  </w:pPr>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
      <w:sz w:val="24"/>
    </w:rPr>
    <w:fldChar w:fldCharType="begin"/>
  </w:r>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
      <w:sz w:val="24"/>
    </w:rPr>
    <w:instrText xml:space="preserve">PAGE   \* MERGEFORMAT</w:instrText>
  </w:r>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
      <w:sz w:val="24"/>
    </w:rPr>
    <w:fldChar w:fldCharType="separate"/>
  </w:r>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
      <w:sz w:val="24"/>
    </w:rPr>
    <w:t>1</w:t>
  </w:r>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
      <w:sz w:val="24"/>
    </w:rPr>
    <w:fldChar w:fldCharType="end"/>
  </w:r>
</w:p>
```

#### 修复分节符和页面设置

正文最后一节的 sectPr 必须包含：
```xml
<w:sectPr>
  <w:headerReference r:id="rId5" w:type="default"/>
  <w:footerReference r:id="rId6" w:type="default"/>
  <w:pgSz w:w="11906" w:h="16838"/>
  <w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800" w:header="851" w:footer="992" w:gutter="0"/>
  <w:pgNumType w:start="1"/>
  <w:cols w:space="425" w:num="1"/>
  <w:docGrid w:type="lines" w:linePitch="312" w:charSpace="0"/>
</w:sectPr>
```

#### 修复三线表

确保表格使用三线表样式 `tblStyle w:val="22"`：
```xml
<w:tblPr>
  <w:tblStyle w:val="22"/>
  <!-- 其他属性 -->
</w:tblPr>
```

### 2.3 样式定义修复

如果 styles.xml 中缺少必要的样式定义，需要添加以下关键样式：

```xml
<!-- heading 1 -->
<w:style w:type="paragraph" w:styleId="2">
  <w:name w:val="heading 1"/>
  <w:basedOn w:val="1"/>
  <w:next w:val="1"/>
  <w:link w:val="18"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/>
    <w:keepLines/>
    <w:spacing w:before="50" w:beforeLines="50" w:after="50" w:afterLines="50" w:line="460" w:lineRule="exact"/>
    <w:jc w:val="left"/>
    <w:outlineLvl w:val="0"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:eastAsia="SimHei"/>
    <w:b/>
    <w:bCs/>
    <w:kern w:val="44"/>
    <w:sz w:val="36"/>
    <w:szCs w:val="44"/>
  </w:rPr>
</w:style>

<!-- heading 2 -->
<w:style w:type="paragraph" w:styleId="3">
  <w:name w:val="heading 2"/>
  <w:basedOn w:val="1"/>
  <w:next w:val="1"/>
  <w:link w:val="19"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/>
    <w:keepLines/>
    <w:spacing w:before="50" w:beforeLines="50" w:after="50" w:afterLines="50" w:line="460" w:lineRule="exact"/>
    <w:outlineLvl w:val="1"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="DengXian Light" w:hAnsi="DengXian Light" w:eastAsia="SimHei"/>
    <w:b/>
    <w:bCs/>
    <w:sz w:val="28"/>
    <w:szCs w:val="32"/>
  </w:rPr>
</w:style>

<!-- heading 3 -->
<w:style w:type="paragraph" w:styleId="4">
  <w:name w:val="heading 3"/>
  <w:basedOn w:val="1"/>
  <w:next w:val="1"/>
  <w:link w:val="20"/>
  <w:qFormat/>
  <w:pPr>
    <w:keepNext/>
    <w:keepLines/>
    <w:spacing w:line="460" w:lineRule="exact"/>
    <w:jc w:val="left"/>
    <w:outlineLvl w:val="2"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:eastAsia="SimHei"/>
    <w:b/>
    <w:bCs/>
    <w:sz w:val="24"/>
    <w:szCs w:val="32"/>
  </w:rPr>
</w:style>

<!-- caption (图表标题) -->
<w:style w:type="paragraph" w:styleId="5">
  <w:name w:val="caption"/>
  <w:basedOn w:val="1"/>
  <w:next w:val="1"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:line="460" w:lineRule="exact"/>
    <w:ind w:firstLine="200" w:firstLineChars="200"/>
    <w:jc w:val="center"/>
  </w:pPr>
  <w:rPr>
    <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimHei"/>
    <w:szCs w:val="20"/>
  </w:rPr>
</w:style>

<!-- 三线表 -->
<w:style w:type="table" w:customStyle="1" w:styleId="22">
  <w:name w:val="三线表"/>
  <w:basedOn w:val="11"/>
  <w:qFormat/>
  <w:rPr>
    <w:rFonts w:eastAsia="SimSun"/>
  </w:rPr>
  <w:tblPr>
    <w:tblBorders>
      <w:top w:val="single" w:color="auto" w:sz="12" w:space="0"/>
      <w:bottom w:val="single" w:color="auto" w:sz="12" w:space="0"/>
    </w:tblBorders>
  </w:tblPr>
  <w:tblStylePr w:type="firstRow">
    <w:tcPr>
      <w:tcBorders>
        <w:bottom w:val="single" w:color="auto" w:sz="4" w:space="0"/>
      </w:tcBorders>
    </w:tcPr>
  </w:tblStylePr>
</w:style>
```

---

## 三、常见问题与修复方案

### 3.1 标题未使用正确样式

**问题**：用户手动设置了标题格式，但没有应用 heading 样式，导致目录无法识别。

**修复**：
1. 识别标题文本（通常为"X 标题名"格式）
2. 将 `w:pStyle` 设置为对应的样式ID（2/3/4）
3. 移除手动设置的格式，让样式继承

### 3.2 正文没有首行缩进

**问题**：段落缺少 `w:ind` 设置。

**修复**：在 `w:pPr` 中添加：
```xml
<w:ind w:firstLine="480" w:firstLineChars="200"/>
```

### 3.3 行距不统一

**问题**：部分段落行距不是固定值23pt。

**修复**：统一设置：
```xml
<w:spacing w:line="460" w:lineRule="exact"/>
```

### 3.4 字体混乱

**问题**：正文中英文字体不正确。

**修复**：在 `w:rPr` 中设置：
```xml
<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun"/>
```

### 3.5 图表编号不连续

**问题**：图表编号跳号或格式不统一。

**修复方案**：
1. 检查所有 caption 样式的段落
2. 按"图X-Y"或"表X-Y"格式统一编号
3. X为当前章号，Y为该章内序号

### 3.6 参考文献编号错误

**问题**：参考文献未使用自动编号或格式不对。

**修复**：
1. 确保使用 `pStyle w:val="17"` (List Paragraph)
2. 添加编号引用 `numId w:val="1"`
3. 确保编号格式为 `[%1]`

### 3.7 页码设置错误

**问题**：正文页码没有从1开始，或摘要目录页码格式不对。

**修复**：
1. 正文 sectPr 中添加 `<w:pgNumType w:start="1"/>`
2. 摘要/目录节使用 `<w:pgNumType w:fmt="upperRoman"/>`

---

## 四、快速修复脚本

对于常见的批量格式问题，可以使用以下搜索替换模式：

### 4.1 批量修复正文行距

搜索所有缺少行距设置的正文段落，添加固定行距。

### 4.2 批量修复字体

将所有 `w:eastAsia="DengXian"` 的正文段落替换为 `w:eastAsia="SimSun"`。

### 4.3 批量添加首行缩进

对缺少首行缩进的正文段落添加缩进设置。

---

## 五、注意事项

1. **始终先备份**：修改前必须备份原始文档
2. **使用 unpack/pack 工作流**：通过解压→编辑XML→重新打包的方式修改文档
3. **保持样式继承**：尽量使用样式（pStyle）而非直接格式化，便于统一修改
4. **注意 XML 实体**：编辑 XML 时使用 `&#x201C;` 等实体表示特殊字符
5. **验证修改结果**：修改完成后运行 sanitize.py 检查，并在 Word 中打开验证
6. **分节符处理**：修改分节结构时要特别小心，避免产生多余的空白页
7. **目录更新**：格式修改完成后，提醒用户在 Word 中右键目录选择"更新域"