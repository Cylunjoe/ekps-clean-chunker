"""EKPS 清洗分段器的核心：一份制度类文档的纯文本进，干净的分段出。不依赖第三方库，不联网，不调模型。

做三件事：
1. 去噪：封面落款（单独成行的机关名、文号、日期）、分隔线、页码、目录行、主送机关、与标题重复的标题行。
   含金额、期限、"不得"等关键字段的行一律保留（宁可留噪声，不删规定）。
2. 按条款分段：遇"第X条"开新段，后续段落并入该条；"第X章"、Markdown 标题记作所属章节；
   Markdown 表格整张成段；非条款的零散段落合并到长度上限；超长的按句号、分号切开。
3. 每段加上下文头：《标题》｜文号｜施行日期｜所属章节——检索命中单独一段时，也知道它出自哪份、哪个版本。

只看一份文档：新旧版本替代、跨文件去重、冲突比对做不了（要看整库），见 EKPS 本地工具。
"""
import re
from dataclasses import dataclass, field

_CN = "零〇一二两三四五六七八九十百千"
_CLAUSE = re.compile(rf"^\s*第[{_CN}\d]+条")
_CHAPTER = re.compile(rf"^\s*第[{_CN}\d]+[章节编]\s*[^。；;：，]{{0,20}}$")
_MD_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_MD_TABLE_RULE = re.compile(r"^\|[\s:|-]+\|?$")

_DATE = r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?|\d{4}[-./]\d{1,2}[-./]\d{1,2}"
_KEY = re.compile(r"\d[\d,，.]*\s*(?:元|万元|亿元|%|％|‰|厘米|毫米|米|小时|分钟|日内|个工作日)|[壹贰叁肆伍陆柒捌玖拾佰仟万]{2,}元"
                  r"|不得|禁止|严禁|不予|不准|除外|不超过|不低于|不少于|至少|最多")
_META_LABEL = re.compile(r"^(文件编号|编号|文号|发布日期|生效日期|印发日期|施行日期|签发人|签发|发文单位|发布单位|主送|抄送|报送|"
                         r"呈报|分送|印发|密级|版本号|修订号|联系人)\s*[:：]")
_DOC_NO = re.compile(r"[一-龥A-Za-z]{1,12}[〔\[(（]\d{4}[〕\])）]\d+号")
_ORG = re.compile(r"^[一-龥（）()]{2,30}(公司|集团|委员会|中心|部|局|处|科|办公室|营业所)$")
_PAGE = re.compile(r"^(第\s*\d+\s*页|共\s*\d+\s*页|-\s*\d+\s*-)$")
_DATE_ONLY = re.compile(rf"^(?:{_DATE})(印发|发布|签发|制)?$")
_TOC = re.compile(r"^目\s*录$|[.…·]{3,}\s*\d+$")
_RULE = re.compile(r"^[─━—\-_=·•*～~]{4,}$")
_TITLE_END = re.compile(r"(办法|规定|细则|制度|规程|规范|规则|清单|指引|预案|通知|公告|通报|纪要|说明|须知|标准|方案)(（[^）]*）)?$")
_ADDR_HEAD = re.compile(r"^(各|有关|全国)")
_ADDR_TAIL = re.compile(r"(部|委|局|厅|院|办|办公厅|单位|部门|公司|集团|中心|营业所|分公司|省|市|区|县)$")
_EFFECTIVE = re.compile(rf"自\s*({_DATE})\s*起\s*(?:施行|执行|实施|生效)")
_SENT_END = re.compile(r"(?<=[。；！？])")
MIN_BODY = 50  # 上下文头很长时，每块正文至少留这么多字
MERGE_BELOW = 20  # 短于这个字数的零散段落（如"附表：××表"）才和相邻段落合并；一条规定通常远长于此


@dataclass
class Result:
    chunks: list[str] = field(default_factory=list)
    parents: list[dict] = field(default_factory=list)  # 父子模式：{"parent_content": 一条规定, "child_contents": [其中每一句]}
    removed: list[tuple[str, str]] = field(default_factory=list)  # (那一行, 去掉的理由)
    title: str = ""
    doc_no: str = ""
    effective: str = ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _addressees(line: str) -> bool:
    if "。" in line or not line.endswith(("：", ":")):
        return False
    items = [x.strip() for x in re.split(r"[，、,]", line[:-1]) if x.strip()]
    return bool(items) and all(_ADDR_HEAD.search(x) or _ADDR_TAIL.search(x) for x in items)


def _noise(line: str, title: str) -> str | None:
    """这一行是不是噪声；是就返回理由。含关键字段的行不算噪声。"""
    if _KEY.search(line):
        return None
    if _TOC.search(line):
        return "目录"
    if _RULE.match(line):
        return "分隔线"
    if _PAGE.match(line):
        return "页码"
    if _addressees(line):
        return "主送机关"
    if title and _norm(line) == _norm(title):
        return "标题行"
    tokens = [t for t in re.split(r"[\s　]+", line) if t]
    meta = lambda t: _META_LABEL.match(t) or _DOC_NO.fullmatch(t) or _ORG.match(t) or _DATE_ONLY.match(t)  # noqa: E731
    if tokens and all(meta(t) for t in tokens):
        return "封面与落款"
    return None


def _guess_title(lines: list[str]) -> str:
    """没给标题时，取前 8 行里第一个像公文标题的短行。"""
    for line in lines[:8]:
        t = line.strip()
        if 4 <= len(t) <= 40 and _TITLE_END.search(t) and not _CLAUSE.match(t):
            return t
    return ""


def _split_long(body: str, limit: int) -> list[str]:
    """超长的段按句号、分号切；单句仍超长就硬切。"""
    if len(body) <= limit:
        return [body]
    out, cur = [], ""
    for sent in (s for s in _SENT_END.split(body.replace("\n", "")) if s):
        while len(sent) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(sent[:limit])
            sent = sent[limit:]
        if len(cur) + len(sent) > limit and cur:
            out.append(cur)
            cur = ""
        cur += sent
    return out + ([cur] if cur else [])


def _split_table(rows: list[str], limit: int) -> list[str]:
    """表格按行切，每块都带上表头行，单独命中某几行也看得懂各列是什么。"""
    head, body = rows[0], rows[1:]
    out, cur = [], [head]
    for r in body:
        if len("\n".join(cur + [r])) > limit and len(cur) > 1:
            out.append("\n".join(cur))
            cur = [head]
        cur.append(r)
    out.append("\n".join(cur))
    return out


def clean_chunk(text: str, max_length: int = 500, title: str = "", header: bool = True) -> Result:
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    r = Result(title=title.strip() or _guess_title(lines))
    r.doc_no = next((m.group(0) for ln in lines[:10] if (m := _DOC_NO.search(ln))), "")
    r.effective = next((m.group(1) for ln in lines if (m := _EFFECTIVE.search(ln))), "")

    # 先归成段：(种类, 所属章节, 行)
    units: list[tuple[str, str, list[str]]] = []
    heading, table = "", []

    def flush_table():
        if table:
            units.append(("table", heading, list(table)))
            table.clear()

    for line in lines:
        if line.startswith("|"):
            if not _MD_TABLE_RULE.match(line):
                table.append(line)
            continue
        flush_table()
        if why := _noise(line, r.title):
            r.removed.append((line, why))
            continue
        if m := _MD_HEADING.match(line):
            heading = m.group(1)
        elif _CHAPTER.match(line):
            heading = line
        elif _CLAUSE.match(line):
            units.append(("clause", heading, [line]))
        elif units and units[-1][0] == "clause" and units[-1][1] == heading:
            units[-1][2].append(line)  # 条款后面的普通段落是这一条的续文
        else:
            units.append(("para", heading, [line]))
    flush_table()

    # 零散段落只把太短的并起来（同一章节内）：没有条款编号时（如 Dify 抽文字丢了 Word 自动编号），
    # 一整段往往就是一条规定，几条规定并成一块，命中一条就把无关的几条一起带出来
    # 太短的碎片（如表题"附表：××表"）并到下一块开头，最后一个没有下文就并回上一块
    merged: list[list] = []  # [种类, 章节, 表题, 正文]
    carry = ""
    for kind, head, ls in units:
        body = "\n".join(ls)
        if kind == "para" and len(body) < MERGE_BELOW:
            carry = f"{carry}\n{body}" if carry else body
            continue
        merged.append([kind, head, carry, body])
        carry = ""
    if carry:
        if merged:
            merged[-1][3] += "\n" + carry
        else:
            merged.append(["para", heading, "", carry])

    for kind, head, caption, body in merged:
        prefix = ""
        if header:
            parts = [f"《{r.title}》" if r.title else "", r.doc_no, f"自{r.effective}起施行" if r.effective else "", head]
            prefix = "｜".join(p for p in parts if p)
            prefix = f"【{prefix}】\n" if prefix else ""
        prefix += f"{caption}\n" if caption else ""  # 表题每块都带：只命中后半张表也知道是哪张
        # 上限按整块算：上下文头和表题也占字数（实测表格块曾到 541 字，超过 500）；正文至少留 MIN_BODY 字
        limit = max(MIN_BODY, max_length - len(prefix))
        pieces = _split_table(body.split("\n"), limit) if kind == "table" else _split_long(body, limit)
        r.chunks.extend(prefix + p for p in pieces)
        for p in pieces:
            r.parents.append({"parent_content": prefix + p, "child_contents": _children(kind, p)})
    return r


def _children(kind: str, piece: str) -> list[str]:
    """子块：表格是"表头行＋一行数据"（单独命中一行也看得懂各列），其余按句切。"""
    if kind == "table":
        rows = piece.split("\n")
        return [f"{rows[0]}\n{row}" for row in rows[1:]] or rows
    return [s.strip() for line in piece.split("\n") for s in _SENT_END.split(line) if s.strip()]


def parent_child(r: Result) -> dict:
    """Dify 父子分段结构（源码 api/core/schemas/builtin/schemas/v1/parent_child_structure.json）。"""
    return {"parent_mode": "paragraph", "parent_child_chunks": r.parents}
