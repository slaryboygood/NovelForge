"""确定性文本相似度（V4-05 §52）。

三层里的前两层，**只用确定性算法**（不使用 embedding，§18）：

```text
1. normalized 精确比较（去掉空白与标点后是否完全相同）
2. 结构化相似度：token Jaccard（词级）+ char n-gram Jaccard（措辞级）
```

词级 Jaccard 抓不到「同一句加后缀」这种模板化重复
（V3 NF-003：`试探：查清核心记录` vs `试探：查清核心记录（第 2 次）`），
所以额外提供字符 n-gram 相似度；两者取较大值。
"""

from __future__ import annotations

_PUNCTUATION = " \t\r\n　，。；：、（）()[]{}《》〈〉“”‘’\"'!！?？…·|/\\-—~@#$%^&*+=<>"


def normalize_text(text: str) -> str:
    """去掉全部空白与标点（用于第 1 层精确比较）。"""

    return "".join(ch for ch in str(text or "") if ch not in _PUNCTUATION).strip()


def token_set(text: str) -> set[str]:
    """词级 token（复用 memory 的确定性 tokenizer，避免第二套实现）。"""

    from novelforge.memory.scoring import tokenize

    return {token for token in tokenize(text) if token}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return round(len(left & right) / len(left | right), 4)


def char_ngram_jaccard(left: str, right: str, *, n: int = 2) -> float:
    """字符 n-gram Jaccard（抓「同一措辞 + 后缀 / 修饰」）。"""

    def grams(text: str) -> set[str]:
        served = normalize_text(text)
        if len(served) < n:
            return {served} if served else set()
        return {served[index:index + n] for index in range(len(served) - n + 1)}

    return jaccard(grams(left), grams(right))


def similarity(left: str, right: str) -> float:
    """两个文本的综合确定性相似度（0..1）。"""

    if not str(left or "").strip() or not str(right or "").strip():
        return 0.0
    if normalize_text(left) == normalize_text(right):
        return 1.0
    return max(jaccard(token_set(left), token_set(right)),
               char_ngram_jaccard(left, right))


__all__ = ["char_ngram_jaccard", "jaccard", "normalize_text", "similarity",
           "token_set"]
