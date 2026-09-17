from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


BOOK_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = BOOK_DIR / "source"
DERIVED_DIR = BOOK_DIR / "derived"

FILE_RANGE_RE = re.compile(r"\((\d+)-(\d+)章\)")
HEADING_RE = re.compile(r"^[ \t\u3000]*第(\d+)章(?:[ \t]+(.+?))?[ \t]*$", re.MULTILINE)
HAN_RE = re.compile(r"[\u4e00-\u9fff]")

NOISE_PATTERNS = [
    re.compile(r"^[（(]本章完[）)]$"),
    re.compile(r"^感谢(?:[~～]|.{0,40}(?:打赏|赠送|月票|推荐票|起点币|\d{3,}))"),
    re.compile(r"^(?:求|请投).{0,12}(?:票|订阅|收藏)"),
    re.compile(r"^章节错误.*(?:举报|修复)"),
    re.compile(r"^手机用户.*(?:访问|阅读)"),
    re.compile(r"^(?:最新网址|请记住本站|本书首发)"),
    re.compile(r"^https?://\S+$"),
    re.compile(r"^更多精彩小说，请访问：速读谷"),
    re.compile(r"^(?:ps|PS)[：:].*"),
]

INLINE_AUTHOR_NOTE_RE = re.compile(
    r"感谢(?:[~～]|[^。！？\n]{0,40}(?:打赏|赠送|月票|推荐票|起点币|\d{3,}))"
)

TYPE_KEYWORDS = {
    "探索": ("发现", "寻找", "探索", "观察", "调查", "抵达", "进入", "前往", "未知", "遗迹", "踪迹"),
    "战斗": ("攻击", "战斗", "战争", "追击", "逃离", "爆炸", "毁灭", "杀死", "敌人", "围攻", "防御"),
    "成长": ("进化", "成长", "制造", "改造", "能力", "结构", "学习", "获得", "变化", "诞生", "适应"),
    "过渡": ("准备", "计划", "等待", "离开", "返回", "继续", "之后", "旅途", "前往", "集合"),
    "世界展开": ("世界", "文明", "种族", "历史", "虚空", "星球", "空间", "生态", "大陆", "宇宙", "领域"),
    "交流关系": ("交流", "对话", "同伴", "联系", "合作", "信任", "沟通", "回应", "见面", "朋友"),
}

CONFLICT_KEYWORDS = {
    "环境生存": ("温度", "缺氧", "饥饿", "能量", "环境", "危险", "死亡", "逃离", "灾难", "风暴"),
    "外部对抗": ("攻击", "敌人", "战争", "战斗", "追击", "防御", "入侵", "围攻", "毁灭"),
    "认知谜题": ("未知", "疑问", "真相", "秘密", "异常", "发现", "调查", "为什么", "记忆"),
    "成长取舍": ("进化", "改造", "能力", "代价", "选择", "适应", "结构", "学习", "变化"),
    "关系沟通": ("交流", "联系", "合作", "信任", "回应", "同伴", "朋友", "谈话"),
}

LOCATION_KEYWORDS = (
    "海洋", "海底", "陆地", "地下", "洞穴", "岛屿", "大陆", "森林", "沙漠", "城市",
    "星球", "虚空", "空间", "宇宙", "遗迹", "舰船", "基地", "梦境", "世界", "领域",
    "地表", "深处", "空中", "水中", "废墟", "边缘", "内部", "外部",
)

HOOK_KEYWORDS = {
    "未知信息": ("什么", "为何", "为什么", "未知", "秘密", "真相", "疑问", "异常"),
    "新危险": ("危险", "攻击", "接近", "死亡", "毁灭", "爆炸", "袭击", "逃"),
    "目标改变": ("决定", "目标", "前往", "寻找", "准备", "开始", "必须"),
    "新生命出现": ("新生物", "陌生生物", "另一个生物", "全新生命", "孵化", "诞生", "第一次见到"),
    "世界扩大": ("世界", "星球", "虚空", "空间", "大陆", "领域", "宇宙"),
    "能力变化": ("能力", "进化", "改造", "结构", "获得", "变化", "制造"),
    "反常结果": ("却发现", "居然", "没想到", "并不是", "异常", "意外", "失败"),
}

CHANGE_MARKERS = ("突然", "但是", "不过", "却", "于是", "因此", "发现", "决定", "开始", "失败", "成功", "死亡", "消失", "出现", "改变")
EXPLANATION_MARKERS = ("也就是说", "实际上", "简单来说", "简单地说", "这是因为", "原因是", "总而言之", "据说", "这意味着")


@dataclass
class SourceChapter:
    chapter_id: int
    title: str
    source_file: str
    source_start: int
    source_end: int
    raw: str


def source_files() -> list[Path]:
    def start_number(path: Path) -> int:
        match = FILE_RANGE_RE.search(path.name)
        if not match:
            raise ValueError(f"无法识别文件范围: {path.name}")
        return int(match.group(1))

    return sorted(SOURCE_DIR.glob("*.txt"), key=start_number)


def read_source_chapters() -> tuple[list[SourceChapter], list[dict[str, object]]]:
    chapters: list[SourceChapter] = []
    source_report: list[dict[str, object]] = []
    for path in source_files():
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        raw_matches = list(HEADING_RE.finditer(text))
        matches = []
        for match in raw_matches:
            if matches and int(matches[-1].group(1)) == int(match.group(1)):
                continue
            matches.append(match)
        source_report.append(
            {
                "file": path.name,
                "encoding": "utf-8",
                "byte_count": path.stat().st_size,
                "character_count": len(text),
                "replacement_character_count": text.count("\ufffd"),
                "raw_chapter_heading_count": len(raw_matches),
                "chapter_heading_count": len(matches),
                "first_chapter": int(matches[0].group(1)) if matches else None,
                "last_chapter": int(matches[-1].group(1)) if matches else None,
            }
        )
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            chapters.append(
                SourceChapter(
                    chapter_id=int(match.group(1)),
                    title=(match.group(2) or "（原标题缺失）").strip(),
                    source_file=path.name,
                    source_start=match.start(),
                    source_end=end,
                    raw=text[match.start():end],
                )
            )
    chapters.sort(key=lambda item: item.chapter_id)
    return chapters, source_report


def is_noise(line: str) -> bool:
    return any(pattern.search(line) for pattern in NOISE_PATTERNS)


def trim_inline_author_note(line: str) -> tuple[str, bool]:
    match = INLINE_AUTHOR_NOTE_RE.search(line)
    if not match:
        return line, False
    prefix = line[: match.start()].rstrip("…。. 　")
    return prefix, True


def clean_chapter(chapter: SourceChapter) -> tuple[str, dict[str, int]]:
    lines = chapter.raw.splitlines()
    heading = f"第{chapter.chapter_id}章 {chapter.title}"
    output = [heading]
    removed_duplicate = 0
    removed_noise = 0
    seen_body = False
    blank_pending = False
    for raw_line in lines[1:]:
        line = raw_line.strip().replace("\u3000", "")
        if not line:
            blank_pending = True
            continue
        if not seen_body and line == heading:
            removed_duplicate += 1
            continue
        line, trimmed_note = trim_inline_author_note(line)
        if trimmed_note:
            removed_noise += 1
        if not line:
            continue
        if is_noise(line):
            removed_noise += 1
            continue
        if blank_pending and output[-1] != "":
            output.append("")
        output.append(line)
        seen_body = True
        blank_pending = False
    while output and output[-1] == "":
        output.pop()
    return "\n".join(output).strip() + "\n", {
        "duplicate_heading_lines_removed": removed_duplicate,
        "noise_lines_removed": removed_noise,
    }


def keyword_scores(text: str, groups: dict[str, tuple[str, ...]]) -> dict[str, int]:
    return {name: sum(text.count(word) for word in words) for name, words in groups.items()}


def top_labels(scores: dict[str, int], *, limit: int = 2) -> list[str]:
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    positive = [name for name, score in ranked if score > 0]
    return positive[:limit] or ["未分类"]


def classify(chapter_text: str) -> dict[str, object]:
    body = chapter_text[-700:]
    type_scores = keyword_scores(chapter_text, TYPE_KEYWORDS)
    conflict_scores = keyword_scores(chapter_text, CONFLICT_KEYWORDS)
    hook_scores = keyword_scores(body, HOOK_KEYWORDS)
    locations = [word for word in LOCATION_KEYWORDS if word in chapter_text]
    return {
        "chapter_types": top_labels(type_scores),
        "primary_conflict": top_labels(conflict_scores, limit=1)[0],
        "location_tags": locations[:4],
        "ending_hook_types": top_labels(hook_scores),
        "classification_method": "keyword_heuristic_reference_only",
    }


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def build() -> None:
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    source_chapters, source_report = read_source_chapters()
    seen: set[int] = set()
    duplicate_ids: list[int] = []
    clean_parts: list[str] = []
    index: list[dict[str, object]] = []
    removal_totals = Counter()
    offset = 0

    for chapter in source_chapters:
        if chapter.chapter_id in seen:
            duplicate_ids.append(chapter.chapter_id)
            continue
        seen.add(chapter.chapter_id)
        clean, removals = clean_chapter(chapter)
        removal_totals.update(removals)
        start = offset
        end = start + len(clean)
        compact_chars = len("".join(clean.split()))
        paragraphs = [line for line in clean.splitlines()[1:] if line.strip()]
        dialogue_paragraphs = sum(1 for line in paragraphs if line.startswith(("“", '"')))
        question_paragraphs = sum(1 for line in paragraphs if "？" in line or "?" in line)
        change_marker_count = sum(clean.count(marker) for marker in CHANGE_MARKERS)
        explanation_marker_count = sum(clean.count(marker) for marker in EXPLANATION_MARKERS)
        classification = classify(clean)
        index.append(
            {
                "chapter_id": f"{chapter.chapter_id:04d}",
                "title": chapter.title,
                "start_offset": start,
                "end_offset": end,
                "character_count": len(clean),
                "compact_character_count": compact_chars,
                "paragraph_count": len(paragraphs),
                "dialogue_paragraph_count": dialogue_paragraphs,
                "question_paragraph_count": question_paragraphs,
                "change_marker_count": change_marker_count,
                "explanation_marker_count": explanation_marker_count,
                "stage_id": f"S{((chapter.chapter_id - 1) // 100) + 1:02d}",
                "stage_chapter_range": [
                    ((chapter.chapter_id - 1) // 100) * 100 + 1,
                    min((((chapter.chapter_id - 1) // 100) + 1) * 100, 4884),
                ],
                "source_file": chapter.source_file,
                "source_start_offset": chapter.source_start,
                "source_end_offset": chapter.source_end,
                **classification,
            }
        )
        clean_parts.append(clean + "\n")
        offset = end + 1

    clean_text = "".join(clean_parts).rstrip() + "\n"
    (DERIVED_DIR / "clean_text.txt").write_text(clean_text, encoding="utf-8")
    (DERIVED_DIR / "chapter_index.json").write_text(
        json.dumps(
            {
                "book_id": "book_001",
                "title": "进化的四十六亿重奏",
                "source_role": "REFERENCE_ONLY",
                "offset_unit": "Unicode code point in derived/clean_text.txt",
                "classification_warning": "章节类型、地点、冲突与Hook均为启发式研究标签，不是原作事实，也不得进入《硅基升维》Canon。",
                "chapters": index,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    lengths = [int(item["compact_character_count"]) for item in index]
    paragraph_counts = [int(item["paragraph_count"]) for item in index]
    type_counts = Counter(label for item in index for label in item["chapter_types"])
    hook_counts = Counter(label for item in index for label in item["ending_hook_types"])
    blocks: list[dict[str, object]] = []
    for start in range(1, 4885, 20):
        members = [item for item in index if start <= int(item["chapter_id"]) <= min(start + 19, 4884)]
        if not members:
            continue
        blocks.append(
            {
                "range": [start, min(start + 19, 4884)],
                "chapter_count": len(members),
                "average_compact_characters": round(statistics.mean(int(item["compact_character_count"]) for item in members), 1),
                "type_counts": dict(Counter(label for item in members for label in item["chapter_types"])),
                "hook_counts": dict(Counter(label for item in members for label in item["ending_hook_types"])),
            }
        )

    segment_ranges = [
        (1, 100),
        (101, 500),
        (501, 1000),
        (1001, 2000),
        (2001, 3000),
        (3001, 4000),
        (4001, 4884),
    ]
    segments: list[dict[str, object]] = []
    for start, end in segment_ranges:
        members = [item for item in index if start <= int(item["chapter_id"]) <= end]
        total_paragraphs = sum(int(item["paragraph_count"]) for item in members)
        total_dialogue = sum(int(item["dialogue_paragraph_count"]) for item in members)
        total_chars = sum(int(item["compact_character_count"]) for item in members)
        segments.append(
            {
                "range": [start, end],
                "chapter_count": len(members),
                "average_compact_characters": round(statistics.mean(int(item["compact_character_count"]) for item in members), 1),
                "average_paragraphs": round(statistics.mean(int(item["paragraph_count"]) for item in members), 1),
                "dialogue_paragraph_ratio": round(total_dialogue / total_paragraphs, 4) if total_paragraphs else 0,
                "change_markers_per_1000_compact_chars": round(
                    1000 * sum(int(item["change_marker_count"]) for item in members) / total_chars,
                    2,
                ) if total_chars else 0,
                "explanation_markers_per_1000_compact_chars": round(
                    1000 * sum(int(item["explanation_marker_count"]) for item in members) / total_chars,
                    2,
                ) if total_chars else 0,
                "type_counts": dict(Counter(label for item in members for label in item["chapter_types"])),
                "hook_counts": dict(Counter(label for item in members for label in item["ending_hook_types"])),
            }
        )

    missing = [number for number in range(1, 4885) if number not in seen]
    metrics = {
        "book_id": "book_001",
        "source_role": "REFERENCE_ONLY",
        "source_report": source_report,
        "integrity": {
            "expected_chapters_from_filename_claim": 4884,
            "indexed_unique_chapters": len(index),
            "missing_chapter_ids": missing,
            "duplicate_top_level_chapter_ids": duplicate_ids,
            "replacement_character_count": sum(int(item["replacement_character_count"]) for item in source_report),
            **dict(removal_totals),
        },
        "clean_text": {
            "character_count": len(clean_text),
            "byte_count_utf8": len(clean_text.encode("utf-8")),
        },
        "chapter_statistics": {
            "compact_character_mean": round(statistics.mean(lengths), 1),
            "compact_character_median": statistics.median(lengths),
            "compact_character_p10": percentile(lengths, 0.10),
            "compact_character_p90": percentile(lengths, 0.90),
            "paragraph_mean": round(statistics.mean(paragraph_counts), 1),
            "dialogue_paragraph_ratio": round(
                sum(int(item["dialogue_paragraph_count"]) for item in index)
                / sum(int(item["paragraph_count"]) for item in index),
                4,
            ),
            "chapter_type_counts": dict(type_counts),
            "ending_hook_type_counts": dict(hook_counts),
        },
        "segments": segments,
        "twenty_chapter_blocks": blocks,
    }
    (DERIVED_DIR / "study_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metrics["integrity"], ensure_ascii=False))
    print(json.dumps(metrics["chapter_statistics"], ensure_ascii=False))


if __name__ == "__main__":
    build()
