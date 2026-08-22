"""父子文档分块：子文档做检索索引，父文档做回答上下文。

当前参数：
- 子文档 150 字，重叠 30 字
- 父文档 800 字
"""

SEPARATORS = ("\n", "!", "！", ".", "。")

PARENT_CHARS = 800
CHILD_CHARS = 150
CHILD_OVERLAP = 30
CHILD_TOP_K = 10
MAX_PARENTS = 3


def _cut_at_separator(text: str, max_chars: int) -> int:
    """在不超过 max_chars 的位置找切点；找不到则硬切。"""
    window = text[:max_chars]
    cut = -1
    for separator in SEPARATORS:
        position = window.rfind(separator)
        if position >= max_chars // 2:
            cut = position
            break
    return max_chars if cut == -1 else cut + 1


def split_parents(text: str, max_chars: int = PARENT_CHARS) -> list:
    """把长文本切成父文档块（按句子/换行优先，最后才硬切）。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    cut = _cut_at_separator(text, max_chars)
    return [text[:cut].strip()] + split_parents(text[cut:], max_chars)


def split_children(
    parent_text: str,
    max_chars: int = CHILD_CHARS,
    overlap: int = CHILD_OVERLAP,
) -> list:
    """把单个父文档切成带重叠的子文档。"""
    text = parent_text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    if overlap >= max_chars:
        raise ValueError("overlap 必须小于 max_chars")

    cut = _cut_at_separator(text, max_chars)
    tail = text[cut:].strip()
    if len(tail) <= overlap:
        return [text]  # 尾部太小，并入当前块，允许轻微超长

    next_start = max(cut - overlap, 1)
    head = text[:cut].strip()
    return [head] + split_children(text[next_start:], max_chars, overlap)


def split_parent_children(
    text: str,
    parent_chars: int = PARENT_CHARS,
    child_chars: int = CHILD_CHARS,
    overlap: int = CHILD_OVERLAP,
) -> list:
    """生成父子结构：每个元素含 parent_index / parent / children。"""
    result = []
    for index, parent in enumerate(split_parents(text, parent_chars)):
        result.append(
            {
                "parent_index": index,
                "parent": parent,
                "children": split_children(parent, child_chars, overlap),
            }
        )
    return result
