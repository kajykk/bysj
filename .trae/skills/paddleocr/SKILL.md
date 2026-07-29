---
name: "paddleocr"
description: "OCR and document parsing toolkit using PaddleOCR. Invoke when user asks for text extraction from images/PDFs, document parsing to Markdown/JSON, multilingual OCR (100+ languages), table/formula recognition, or building RAG data pipelines from documents."
---

# PaddleOCR Skill

PaddleOCR is the global leading OCR toolkit & Document AI engine (70k+ Stars). It converts PDF documents and images into structured, LLM-ready data (JSON/Markdown) with industry-leading accuracy.

## When to Invoke

- User wants to extract text from images, scanned PDFs, or screenshots
- User needs document parsing (PDF/image → Markdown/JSON)
- User mentions OCR, text recognition, or document digitization
- User is building a RAG pipeline and needs document-to-text conversion
- User needs multilingual text recognition (100+ languages)
- User wants table extraction, formula recognition, or layout analysis
- User mentions PaddleOCR, PP-OCR, PP-Structure, or PaddleOCR-VL

## Core Capabilities

### 1. PP-OCRv6 — Universal Text Recognition (Scene OCR)
- **100+ languages**: Single model covers Chinese, English, Japanese, and 46 Latin-script languages
- **Three tiers**: tiny (1.5M) / small (7.7M) / medium (34.5M) for edge/mobile/server
- **Performance**: +4.6% detection and +5.1% recognition over PP-OCRv5; 5.2× CPU inference speedup
- **Scenarios**: IDs, street views, books, industrial components, digital displays, dot-matrix characters, tire prints

### 2. PaddleOCR-VL-1.6 — SOTA Document VLM (0.9B)
- **96.3% accuracy** on OmniDocBench v1.6
- **Structured output**: Markdown and JSON formats
- **Complex elements**: text, formula, table, chart recognition
- **Specialized**: ancient documents, rare characters, seals, handwriting
- **109 languages** supported

### 3. PP-StructureV3 — Structure-Aware Document Conversion
- Converts complex PDFs/images into **Markdown** or **JSON**
- Fine-grained coordinates: table cell coordinates, text coordinates
- Cross-page table merging and hierarchical heading identification
- DOCX export support

## Quick Start

### Installation

```bash
pip install paddleocr
```

Requirements: Python 3.8~3.12, supports Linux/Windows/Mac, CPU/GPU/XPU/NPU.

### Basic Usage — PP-OCR (Text Recognition)

```python
from paddleocr import PaddleOCR

# Initialize with medium model (best accuracy)
ocr = PaddleOCR(use_angle_cls=True, lang="ch", use_doc_ori_classify=False, use_doc_unwarping=False)

# Recognize from image
result = ocr.ocr("image.png", cls=True)

# result structure: [[[box_coords], (text, confidence)], ...]
for idx in range(len(result)):
    res = result[idx]
    if res is not None:
        for line in res:
            print(line[1][0])  # text content
```

### Document Parsing — PP-StructureV3 (PDF/Image → Markdown)

```python
from paddleocr import PPStructure

# Initialize structure analysis
engine = PPStructure(layout=True, table=True, ocr=True)

# Parse document
result = engine("document.pdf")

# Export to Markdown
from paddleocr.ppstructure.recovery.recovery_to_markdown import convert_to_markdown
md_content = convert_to_markdown(result)
```

### PaddleOCR-VL (Advanced Document Parsing)

```python
from paddleocr import PaddleOCRVL

# Initialize VLM model (requires GPU for best performance)
vl = PaddleOCRVL(model_name="PaddleOCR-VL-1.6")

# Parse complex documents
result = vl("complex_document.pdf")
# Returns structured Markdown/JSON with 96.3% accuracy
```

## Language Support

| Model | Languages | Notes |
|-------|-----------|-------|
| PP-OCRv6 | 50 (single model) | Chinese, English, Japanese + 46 Latin |
| PaddleOCR-VL | 109 | Major global languages + rare scripts |
| PP-StructureV3 | 111 | Includes Tibetan, Bengali |

For non-Latin languages, specify `lang` parameter:
```python
# Supported lang codes: ch, en, japan, korean, german, french, russian, arabic, hindi, thai, etc.
ocr = PaddleOCR(lang="japan")
```

## Output Formats

### PP-OCR Output (JSON)
```json
[
  {
    "rec_texts": ["text1", "text2"],
    "rec_scores": [0.98, 0.95],
    "dt_polys": [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], ...]
  }
]
```

### PP-StructureV3 Output (Markdown + JSON)
- Markdown: Direct LLM-ready text with table/formula rendering
- JSON: Fine-grained coordinates for each element (text, table cell, figure)

## Deployment Options

| Method | Use Case |
|--------|----------|
| Python API | Local development, scripts |
| PaddleOCR.js | Browser-based inference (PP-OCRv5) |
| C++/C#/Java Serving | Production deployment |
| Docker | Containerized deployment |
| ONNX Runtime | Cross-platform acceleration |
| OpenVINO | Intel CPU acceleration (5.2× speedup) |

## Model Selection Guide

| Scenario | Recommended Model | Size | Accuracy |
|----------|------------------|------|----------|
| Mobile/Edge | PP-OCRv6-tiny | 1.5M | Good |
| General purpose | PP-OCRv6-small | 7.7M | Better |
| Server/High-accuracy | PP-OCRv6-medium | 34.5M | Best |
| Complex documents | PaddleOCR-VL-1.6 | 0.9B | SOTA (96.3%) |
| Table-heavy docs | PP-StructureV3 | — | High |

## Integration with RAG Pipelines

PaddleOCR is the premier choice for AI Agent ecosystems, deeply integrated with Dify, RAGFlow, Pathway, and Cherry Studio.

```python
# Example: PDF → Markdown for RAG ingestion
from paddleocr import PPStructure

engine = PPStructure(layout=True, table=True, ocr=True)
result = engine("knowledge_base.pdf")

# Convert to Markdown for vector DB ingestion
from paddleocr.ppstructure.recovery.recovery_to_markdown import convert_to_markdown
markdown_chunks = convert_to_markdown(result)

# Feed into your RAG pipeline
# vector_db.insert(markdown_chunks)
```

## Common Issues & Solutions

1. **GPU not detected**: Ensure CUDA toolkit matches PaddlePaddle version
2. **Memory error on large PDF**: Use page-by-page processing
3. **Low accuracy on handwriting**: Switch to PaddleOCR-VL model
4. **Slow CPU inference**: Use OpenVINO backend or PP-OCRv6-tiny

## References

- [GitHub](https://github.com/PaddlePaddle/PaddleOCR)
- [Official Website](https://www.paddleocr.com)
- [PP-OCR Docs](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html)
- [PaddleOCR-VL Docs](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- [PP-StructureV3 Docs](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html)
- [HuggingFace Models](https://huggingface.co/PaddlePaddle)
