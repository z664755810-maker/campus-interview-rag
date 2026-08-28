"""多格式文档解析层：把上传的原始字节 -> 纯文本。

设计要点（面试时能讲清楚的那种）：
1. **解析与切分解耦**：这里只负责「字节 -> 文本」，切分交给 ingestion。
   这样以后加新格式不用碰 RAG 主流程，符合单一职责。
2. **依赖按需导入（lazy import）**：docx/pptx/pdf 这类第三方库在模块顶部不 import，
   而是在用到时才 import。好处：用户只传 .md/.txt 时，
   即使环境里没装 python-docx 也能正常跑，不会因为一个可选依赖缺失导致整个服务起不来。
3. **编码兜底**：中文 Windows 用户拿记事本存的 .txt 常常是 GBK，
   直接 utf-8 decode 会抛 UnicodeDecodeError —— 这是新手项目最常见的线上 500 之一。
   这里按 utf-8 -> utf-8-sig -> gbk -> gb18030 -> latin-1 逐级回退。
4. **容量与体积限制**：在 API 层做（见 documents.py），这里只管解析。
"""
from __future__ import annotations

import csv
import io
import json
from html.parser import HTMLParser

# ── 支持的扩展名 -> 解析器类型（前端也在用同一份白名单，见 /api/documents/formats）
SUPPORTED_EXTENSIONS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".text": "text",
    ".docx": "docx",
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".json": "json",
    ".html": "html",
    ".htm": "html",
    ".log": "text",
}

# 前端 <input accept> 直接复用，避免前后端两份名单不一致
ACCEPT_ATTR = ",".join(sorted(SUPPORTED_EXTENSIONS.keys()))

# 中文说明（用于错误提示 / 前端展示）
EXT_LABEL = {
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".txt": "纯文本",
    ".text": "纯文本",
    ".log": "日志文本",
    ".docx": "Word 文档",
    ".pdf": "PDF",
    ".pptx": "PPT 演示文稿",
    ".xlsx": "Excel 表格",
    ".csv": "CSV 表格",
    ".json": "JSON 数据",
    ".html": "网页",
    ".htm": "网页",
}

# 明确不支持但用户很可能传的格式 -> 给出可执行的转换建议
UNSUPPORTED_HINTS = {
    ".doc": "老版 Word(.doc) 是二进制格式，请用 Word/WPS 打开后「另存为 .docx」再上传",
    ".xls": "老版 Excel(.xls) 请用 Excel/WPS「另存为 .xlsx」再上传",
    ".ppt": "老版 PPT(.ppt) 请用 PowerPoint/WPS「另存为 .pptx」再上传",
    ".pages": "请导出为 .docx 或 .pdf 后上传",
    ".wps": "请用 WPS「另存为 .docx」后上传",
    ".rtf": "请用 Word/WPS 另存为 .docx 后上传",
    ".zip": "请先解压，再逐个上传里面的文档",
    ".rar": "请先解压，再逐个上传里面的文档",
    ".png": "图片需先做 OCR 转成文字；本项目暂不支持直接识图",
    ".jpg": "图片需先做 OCR 转成文字；本项目暂不支持直接识图",
    ".jpeg": "图片需先做 OCR 转成文字；本项目暂不支持直接识图",
}

# 解码顺序：utf-8 优先，兼容带 BOM，再退到中文 GBK 系，最后 latin-1 兜底不报错
_DECODINGS = ("utf-8", "utf-8-sig", "gbk", "gb18030", "big5", "latin-1")


class UnsupportedFileError(ValueError):
    """不支持的文件类型。message 会直接展示给用户，所以要写人话。"""


class ParseError(ValueError):
    """文件本身损坏 / 解析失败。"""


def _decode(raw: bytes) -> str:
    """带编码回退的解码，杜绝中文 txt 的常见 UnicodeDecodeError。"""
    for enc in _DECODINGS:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 理论上 latin-1 永不失败，这里只是防御性兜底
    return raw.decode("utf-8", errors="ignore")


class _HTMLTextExtractor(HTMLParser):
    """抽取 HTML 正文：跳过 script/style，保留段落换行。"""

    _SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data.strip() + " ")

    def get_text(self) -> str:
        import re

        text = "".join(self.parts)
        # 压缩 3 个以上连续换行为 2 个，避免空行过多
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def _parse_text(raw: bytes) -> str:
    return _decode(raw)


def _parse_docx(raw: bytes) -> str:
    try:
        from docx import Document  # python-docx
    except ImportError as exc:  # pragma: no cover
        raise ParseError("服务器缺少 python-docx，无法解析 .docx") from exc

    try:
        doc = Document(io.BytesIO(raw))
    except Exception as exc:
        raise ParseError(f".docx 解析失败，文件可能已损坏：{exc}") from exc

    lines: list[str] = []
    # 段落：保留 Word 的「标题」层级信息（Heading 1/2/3 -> #/##/###），
    # 这样上传的 Word 若本身就是题库排版，下游 parse_markdown 能直接按题切分。
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if style.startswith("heading 1") or style == "title":
            lines.append(f"# {text}")
        elif style.startswith("heading 2"):
            lines.append(f"## {text}")
        elif style.startswith("heading 3"):
            lines.append(f"### {text}")
        elif style.startswith("heading"):
            lines.append(f"#### {text}")
        else:
            lines.append(text)
        lines.append("")

    # 表格：每行拼成一行文本，避免表格内容整块丢失
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            cells = [c for c in cells if c]
            if cells:
                lines.append(" | ".join(cells))
        lines.append("")

    return "\n".join(lines).strip()


def _parse_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader  # pypdf（PyPDF2 的现代继任者）
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # 兼容老环境
        except ImportError as exc:
            raise ParseError("服务器缺少 pypdf，无法解析 .pdf") from exc

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as exc:
        raise ParseError(f".pdf 解析失败，文件可能已损坏或被加密：{exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")  # 尝试空密码（很多"加密"PDF 其实只是空口令）
        except Exception:
            raise ParseError("该 PDF 已加密，请先去除密码后上传")

    pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if text:
            pages.append(f"<!-- page {i} -->\n{text}")

    result = "\n\n".join(pages).strip()
    if not result:
        # 扫描件 PDF：没有文字层，不是解析失败，而是文件本身没有文本
        raise ParseError(
            "这份 PDF 没有可提取的文字层（多半是扫描件/图片版）。"
            "请先用 OCR 工具转成文本，或上传原生的 Word/PDF 文件。"
        )
    return result


def _parse_pptx(raw: bytes) -> str:
    try:
        from pptx import Presentation  # python-pptx
    except ImportError as exc:  # pragma: no cover
        raise ParseError("服务器缺少 python-pptx，无法解析 .pptx") from exc

    try:
        prs = Presentation(io.BytesIO(raw))
    except Exception as exc:
        raise ParseError(f".pptx 解析失败，文件可能已损坏：{exc}") from exc

    slides: list[str] = []
    for idx, slide in enumerate(prs.slides, start=1):
        buf: list[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                text = "".join(run.text for run in para.runs).strip()
                if text:
                    buf.append(text)
            # 表格也一并抽取
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        buf.append(" | ".join(cells))
        if buf:
            slides.append(f"<!-- slide {idx} -->\n" + "\n".join(buf))

    return "\n\n".join(slides).strip()


def _parse_xlsx(raw: bytes) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise ParseError("服务器缺少 openpyxl，无法解析 .xlsx") from exc

    try:
        wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    except Exception as exc:
        raise ParseError(f".xlsx 解析失败，文件可能已损坏：{exc}") from exc

    sheets: list[str] = []
    for ws in wb.worksheets:
        rows: list[str] = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c).strip() for c in row]
            # 跳过整行全空
            if not any(cells):
                continue
            rows.append(" | ".join(c for c in cells if c))
        if rows:
            sheets.append(f"<!-- sheet {ws.title} -->\n" + "\n".join(rows))
    wb.close()

    return "\n\n".join(sheets).strip()


def _parse_csv(raw: bytes) -> str:
    text = _decode(raw)
    # 嗅探分隔符（支持 ; \t 等）
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [" | ".join(c.strip() for c in row if c.strip()) for row in reader]
    return "\n".join(r for r in rows if r).strip()


def _parse_json(raw: bytes) -> str:
    text = _decode(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f".json 不是合法 JSON：{exc}") from exc

    # 常见题库 JSON 形态：[{question, answer}, ...] / {"data": [...]} / 纯对象
    items = data if isinstance(data, list) else None
    if items is None and isinstance(data, dict):
        for key in ("data", "items", "list", "questions", "results"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    if items is None and isinstance(data, dict):
        items = [data]

    lines: list[str] = []
    if items:
        for i, item in enumerate(items, start=1):
            if isinstance(item, dict):
                q = item.get("question") or item.get("q") or item.get("title") or ""
                a = item.get("answer") or item.get("a") or item.get("content") or ""
                if q or a:
                    lines.append(f"### Q{i}. {q}")
                    lines.append(str(a))
                    lines.append("")
                else:
                    # 非题库结构：把键值平铺，保证内容不丢
                    lines.append(f"### Q{i}. 记录 {i}")
                    lines.append(
                        "\n".join(f"{k}: {v}" for k, v in item.items() if v not in (None, ""))
                    )
                    lines.append("")
            else:
                lines.append(f"### Q{i}. 记录 {i}")
                lines.append(str(item))
                lines.append("")
    else:
        lines.append(str(data))

    return "\n".join(lines).strip()


def _parse_html(raw: bytes) -> str:
    text = _decode(raw)
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(text)
    except Exception as exc:
        raise ParseError(f".html 解析失败：{exc}") from exc
    result = extractor.get_text()
    if not result:
        raise ParseError("网页里没有提取到正文内容")
    return result


_PARSERS = {
    "markdown": _parse_text,
    "text": _parse_text,
    "docx": _parse_docx,
    "pdf": _parse_pdf,
    "pptx": _parse_pptx,
    "xlsx": _parse_xlsx,
    "csv": _parse_csv,
    "json": _parse_json,
    "html": _parse_html,
}


def extract_extension(filename: str) -> str:
    """取小写扩展名；无扩展名返回空串。"""
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].strip().lower()


def extract_text(filename: str, raw: bytes) -> str:
    """统一入口：文件名 + 字节 -> 纯文本。

    抛 UnsupportedFileError（类型不支持）或 ParseError（解析失败）。
    """
    ext = extract_extension(filename)

    if not ext:
        raise UnsupportedFileError("文件没有扩展名，无法判断类型，请补充后缀（如 .docx）")

    if ext in UNSUPPORTED_HINTS and ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(f"暂不支持 {ext} 格式：{UNSUPPORTED_HINTS[ext]}")

    kind = SUPPORTED_EXTENSIONS.get(ext)
    if not kind:
        supported = "、".join(sorted(SUPPORTED_EXTENSIONS.keys()))
        raise UnsupportedFileError(f"暂不支持 {ext} 格式。当前支持：{supported}")

    text = _PARSERS[kind](raw)
    if not text or not text.strip():
        raise ParseError(f"文件 {filename} 解析后没有可入库的文字内容")
    return text
