import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.chunker import clean_chunk  # noqa: E402

# 从 Dify 读出的样子：Word 自动编号"第X条"丢了，表格成了 Markdown
DIFY_TEXT = """江屿燃气集团有限公司
江燃〔2026〕12号
──────────────────────────────────
报装收费管理办法
各部门、各片区营业所：
为规范公司燃气报装与接驳业务管理，统一收费政策，制定本办法。
客服中心统一受理报装申请。受理后应当在2个工作日内安排现场勘察。
附表：报装收费项目汇总表
| 收费项目 | 计费单位 | 收费标准 |
| --- | --- | --- |
| 报装费（居民） | 元/户 | 2800 |
| 报装费（非居民） | 元/户 | 5000 |
本办法自2026年2月1日起施行，原2024年版《报装收费管理办法》（江燃〔2024〕5号）同时废止。
抄送：公司领导班子。
江屿燃气集团有限公司办公室　　　　2026年1月20日印发"""

# 带条款编号的写法
CLAUSE_TEXT = """报装收费管理办法
第一章 总则
第一条 为规范报装业务，制定本办法。
第二条 本办法适用于居民用户。
非居民用户参照执行。
第二章 收费
第三条 居民用户报装费按每户2800元收取。
本办法自2026年2月1日起施行。"""


def test_removes_cover_footer_and_keeps_body():
    r = clean_chunk(DIFY_TEXT)
    reasons = {line: why for line, why in r.removed}
    assert reasons["江屿燃气集团有限公司"] == "封面与落款"
    assert reasons["江燃〔2026〕12号"] == "封面与落款"
    assert reasons["各部门、各片区营业所："] == "主送机关"
    assert reasons["报装收费管理办法"] == "标题行"
    assert reasons["抄送：公司领导班子。"] == "封面与落款"
    assert reasons["江屿燃气集团有限公司办公室　　　　2026年1月20日印发"] == "封面与落款"
    assert any(why == "分隔线" for _, why in r.removed)
    body = "\n".join(r.chunks)
    for kept in ("统一收费政策", "2个工作日内安排现场勘察", "| 报装费（居民） | 元/户 | 2800 |", "同时废止"):
        assert kept in body  # 正文、表格、施行条款一个都不能丢


def test_context_header_carries_title_doc_no_and_effective_date():
    r = clean_chunk(DIFY_TEXT)
    assert (r.title, r.doc_no, r.effective) == ("报装收费管理办法", "江燃〔2026〕12号", "2026年2月1日")
    assert all(c.startswith("【《报装收费管理办法》｜江燃〔2026〕12号｜自2026年2月1日起施行】\n") for c in r.chunks)
    assert not clean_chunk(DIFY_TEXT, header=False).chunks[0].startswith("【")


def test_table_is_one_chunk_without_rule_row():
    tables = [c for c in clean_chunk(DIFY_TEXT, header=False).chunks if "| 收费项目" in c]
    assert tables == ["附表：报装收费项目汇总表\n| 收费项目 | 计费单位 | 收费标准 |\n| 报装费（居民） | 元/户 | 2800 |\n| 报装费（非居民） | 元/户 | 5000 |"]


def test_clauses_are_chunks_and_continuations_stay_with_their_clause():
    r = clean_chunk(CLAUSE_TEXT, header=True)
    bodies = [c.split("\n", 1)[1] for c in r.chunks]
    assert "第二条 本办法适用于居民用户。\n非居民用户参照执行。" in bodies  # 续行并入本条，不另成一段
    assert any(c.startswith("【《报装收费管理办法》｜自2026年2月1日起施行｜第二章 收费】\n第三条") for c in r.chunks)
    assert not any("第一章 总则" == b for b in bodies)  # 章标题进上下文头，不单独成段


def test_lines_with_key_fields_are_never_removed_as_noise():
    r = clean_chunk("江屿燃气集团有限公司\n本公司报装费 2800 元\n2026年1月20日")
    assert "本公司报装费 2800 元" in "\n".join(r.chunks)
    assert ("江屿燃气集团有限公司", "封面与落款") in r.removed


def test_long_paragraph_splits_on_sentences_and_tables_repeat_header():
    long = "。".join(f"第{i}句话说明报装流程的一个环节" for i in range(60)) + "。"
    chunks = clean_chunk(long, max_length=120, header=False).chunks
    assert len(chunks) > 1 and all(len(c) <= 120 for c in chunks)
    assert "".join(chunks) == long  # 切开后原文一字不差
    rows = "\n".join(["| 项目 | 金额 |"] + [f"| 材料{i} | {i}0 元 |" for i in range(40)])
    parts = clean_chunk(rows, max_length=100, header=False).chunks
    assert len(parts) > 1 and all(p.startswith("| 项目 | 金额 |") for p in parts)


def test_empty_input_gives_no_chunks():
    assert clean_chunk("").chunks == [] and clean_chunk("\n \n").chunks == []


def test_without_clause_numbers_each_rule_paragraph_is_its_own_chunk_and_captions_join_their_table():
    r = clean_chunk(DIFY_TEXT, header=False)
    assert "为规范公司燃气报装与接驳业务管理，统一收费政策，制定本办法。" in r.chunks
    assert "客服中心统一受理报装申请。受理后应当在2个工作日内安排现场勘察。" in r.chunks  # 两条规定不并成一块
    table = next(c for c in r.chunks if "| 收费项目" in c)
    assert table.startswith("附表：报装收费项目汇总表\n| 收费项目")  # 表题跟着表走，不粘到上一条规定上


def test_parent_child_structure_clause_parents_sentence_children_table_rows_with_header():
    from tools.chunker import parent_child
    pc = parent_child(clean_chunk(DIFY_TEXT))
    assert pc["parent_mode"] == "paragraph"
    items = pc["parent_child_chunks"]
    assert all(set(x) == {"parent_content", "child_contents"} and x["child_contents"] for x in items)
    rule = next(x for x in items if "客服中心统一受理报装申请" in x["parent_content"])
    assert rule["parent_content"].startswith("【《报装收费管理办法》")  # 父块带上下文头
    assert rule["child_contents"] == ["客服中心统一受理报装申请。", "受理后应当在2个工作日内安排现场勘察。"]  # 子块按句
    table = next(x for x in items if "| 收费项目" in x["parent_content"])
    assert table["child_contents"][0] == "| 收费项目 | 计费单位 | 收费标准 |\n| 报装费（居民） | 元/户 | 2800 |"
    assert len(pc["parent_child_chunks"]) == len(clean_chunk(DIFY_TEXT).chunks)  # 父块与通用模式的块一一对应


def test_max_length_counts_header_and_caption():
    """Dify 实测：表格块 541 字超过上限 500，因为上限只算了正文。现在整块（含上下文头、表题）不超上限。"""
    rows = "\n".join(["附表：材料价格表", "| 材料 | 单位 | 单价 | 备注 |"] + [f"| 镀锌钢管 DN{i} 规格说明较长 | 元/米 | {i} | 材料公示价 |" for i in range(15, 80)])
    text = "江燃〔2026〕12号\n报装收费管理办法\n本办法自2026年2月1日起施行。\n" + rows
    for c in clean_chunk(text, max_length=300).chunks:
        assert len(c) <= 300, len(c)
    assert clean_chunk("第一条 很长的规定" * 50, max_length=120).chunks  # 上限很小时也能切，不死循环
