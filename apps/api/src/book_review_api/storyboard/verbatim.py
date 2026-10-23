"""Chia bài review có sẵn thành cảnh, giữ nguyên văn (tab "Từ bài review có sẵn", ngày 3).

Code chia cảnh, không có LLM: Hook là 1 cảnh `hook`, Ý chính thành các cảnh `body`, Nhận xét
thành các cảnh `review_cta`. Mỗi cảnh gom 2–3 câu (~7 giây đọc), không vượt ranh giới đoạn văn.
Lời đọc chỉ khác văn bản gốc ở chỗ số, ký hiệu và vài chữ viết tắt được đọc thành chữ cho TTS;
`verbatim_problems` kiểm lại điều đó.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from book_review_api.storyboard.duration import count_syllables, syllables_for
from book_review_api.storyboard.schema import Section

# Một cảnh nhắm ~7 giây đọc, tối đa ~10 giây trước khi phải tách sang cảnh mới.
TARGET_SCENE_SECONDS = 7.0
MAX_SCENE_SECONDS = 10.0
TARGET_SYLLABLES = syllables_for(TARGET_SCENE_SECONDS)
MAX_SYLLABLES = syllables_for(MAX_SCENE_SECONDS)
# Đuôi đoạn văn ngắn hơn mức này thì gộp vào cảnh trước của cùng đoạn (nếu không quá dài).
MIN_TAIL_SYLLABLES = TARGET_SYLLABLES // 3

# --- Markdown -----------------------------------------------------------------

_LINE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$"), ""),  # đường kẻ ngang
    (re.compile(r"^\s*#{1,6}\s+(.*?)\s*#*\s*$"), r"\1"),  # tiêu đề
    (re.compile(r"^\s*(?:>\s?)+"), ""),  # trích dẫn
    (re.compile(r"^\s*[-*+]\s+"), ""),  # gạch đầu dòng
    (re.compile(r"^\s*\d+[.)]\s+"), ""),  # danh sách đánh số
)
_INLINE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),  # ảnh
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),  # liên kết
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"(\*\*|__)(.+?)\1"), r"\2"),
    (re.compile(r"~~(.+?)~~"), r"\1"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"\1"),
    (re.compile(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)"), r"\1"),
)


def strip_markdown(text: str) -> str:
    """Bỏ cú pháp markdown, giữ chữ và ranh giới dòng. Văn bản thường đi qua không đổi."""
    lines: list[str] = []
    for line in text.split("\n"):
        for pattern, repl in _LINE_RULES:
            line = pattern.sub(repl, line)
        for pattern, repl in _INLINE_RULES:
            line = pattern.sub(repl, line)
        lines.append(line.strip())
    return "\n".join(lines).strip()


def paragraphs(text: str) -> list[str]:
    """Mỗi dòng không trống là một đoạn (markdown đã bỏ, khoảng trắng đã gom)."""
    return [" ".join(p.split()) for p in strip_markdown(text).split("\n") if p.strip()]


# --- Tách câu -----------------------------------------------------------------

# Chữ viết tắt hay gặp có dấu chấm, không coi là hết câu.
ABBREVIATIONS: frozenset[str] = frozenset(
    {"tp", "ts", "ths", "pgs", "gs", "bs", "ks", "nxb", "st", "mr", "mrs", "ms", "dr", "vs"}
    | {"v.v", "tr", "no", "p", "q"}
)
_SENTENCE_END_RE = re.compile(r"[.!?…]+[\"'”’»)\]]*(?=\s)")
_CLAUSE_END_RE = re.compile(r"[,;:]+(?=\s)")


def _is_abbreviation(text: str, end: int) -> bool:
    """Dấu chấm tại `end` thuộc chữ viết tắt (vd "TS.", "v.v.") hoặc chữ cái đầu tên ("J.")."""
    word = re.search(r"([\w.]+)\.$", text[: end + 1])
    if word is None:
        return False
    token = word.group(1)
    return token.lower() in ABBREVIATIONS or (len(token) == 1 and token.isupper())


def split_sentences(paragraph: str) -> list[str]:
    """Tách câu ở `. ! ? …` (kể cả ngoặc kép đóng sau dấu), trừ chữ viết tắt và câu sau bắt đầu
    bằng chữ thường. Ghép các câu lại bằng một khoảng trắng ra đúng đoạn văn."""
    out: list[str] = []
    start = 0
    for m in _SENTENCE_END_RE.finditer(paragraph):
        punct_end = m.start() + len(m.group(0).rstrip("\"'”’»)]")) - 1
        if paragraph[punct_end] == "." and _is_abbreviation(paragraph, punct_end):
            continue
        rest = paragraph[m.end() :].lstrip()
        if rest and rest[0].islower():
            continue
        out.append(paragraph[start : m.end()].strip())
        start = m.end()
    tail = paragraph[start:].strip()
    if tail:
        out.append(tail)
    return out


def _split_long(sentence: str) -> list[str]:
    """Câu quá dài cho một cảnh thì tách ở dấu phẩy, chấm phẩy, hai chấm."""
    if count_syllables(sentence) <= MAX_SYLLABLES:
        return [sentence]
    parts: list[str] = []
    start = 0
    for m in _CLAUSE_END_RE.finditer(sentence):
        parts.append(sentence[start : m.end()].strip())
        start = m.end()
    parts.append(sentence[start:].strip())
    return [p for p in parts if p]


# --- Gom câu thành cảnh -------------------------------------------------------


def _group(pieces: list[str]) -> list[str]:
    groups: list[list[str]] = []
    current: list[str] = []
    size = 0
    for piece in pieces:
        n = count_syllables(piece)
        if current and size + n > MAX_SYLLABLES:
            groups.append(current)
            current, size = [], 0
        current.append(piece)
        size += n
        if size >= TARGET_SYLLABLES:
            groups.append(current)
            current, size = [], 0
    if current:
        last = groups[-1] if groups else None
        merged = count_syllables(" ".join(last)) + size if last else 0
        if last and size < MIN_TAIL_SYLLABLES and merged <= MAX_SYLLABLES * 1.3:
            last.extend(current)
        else:
            groups.append(current)
    return [" ".join(g) for g in groups]


def chunk_paragraph(paragraph: str) -> list[str]:
    pieces = [p for s in split_sentences(paragraph) for p in _split_long(s)]
    return _group(pieces)


@dataclass(frozen=True)
class SceneText:
    section: Section
    # Văn bản gốc của cảnh (đã bỏ markdown) và lời đọc đã chuẩn hoá cho TTS.
    text: str
    narration: str
    changes: list[dict[str, str]] = field(default_factory=list)


def split_review_into_scenes(hook: str | None, main: str, comment: str | None) -> list[SceneText]:
    """Ô trống thì không có cảnh của phần đó. Hook luôn là đúng 1 cảnh."""
    parts: list[tuple[Section, list[str]]] = []
    if hook and (hook_paragraphs := paragraphs(hook)):
        parts.append(("hook", [" ".join(hook_paragraphs)]))
    parts.append(("body", [c for p in paragraphs(main) for c in chunk_paragraph(p)]))
    if comment:
        parts.append(("review_cta", [c for p in paragraphs(comment) for c in chunk_paragraph(p)]))
    scenes: list[SceneText] = []
    for section, texts in parts:
        for text in texts:
            spoken = normalize_for_tts(text)
            scenes.append(SceneText(section, text, spoken.text, spoken.changes))
    return scenes


# --- Chuẩn hoá cho TTS --------------------------------------------------------

_DIGITS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")
_SCALES = ("", "nghìn", "triệu", "tỷ")


def _read_tens(n: int, full: bool) -> list[str]:
    """Đọc 0..99 trong một nhóm ba chữ số; `full` khi đã có hàng trăm phía trước."""
    tens, units = divmod(n, 10)
    if tens == 0:
        if units == 0:
            return []
        return (["linh"] if full else []) + [_DIGITS[units]]
    words = ["mười"] if tens == 1 else [_DIGITS[tens], "mươi"]
    if units == 1 and tens > 1:
        words.append("mốt")
    elif units == 5:
        words.append("lăm")
    elif units:
        words.append(_DIGITS[units])
    return words


def _read_triple(n: int, full: bool) -> list[str]:
    hundreds, rest = divmod(n, 100)
    if not full and hundreds == 0:
        return _read_tens(rest, False)
    return [_DIGITS[hundreds], "trăm", *_read_tens(rest, True)]


def read_number(n: int) -> str:
    """Số nguyên không âm thành chữ: 1988 → "một nghìn chín trăm tám mươi tám"."""
    if n == 0:
        return "không"
    if n >= 1000 ** len(_SCALES):
        return " ".join(_DIGITS[int(d)] for d in str(n))
    groups: list[int] = []
    while n:
        n, g = divmod(n, 1000)
        groups.append(g)
    words: list[str] = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        words += _read_triple(g, full=bool(words))
        if _SCALES[i]:
            words.append(_SCALES[i])
    return " ".join(words)


def _read_digits(digits: str) -> str:
    """Chuỗi chữ số: có số 0 đứng đầu thì đọc từng chữ số, không thì đọc như số."""
    if len(digits) > 1 and digits.startswith("0"):
        return " ".join(_DIGITS[int(d)] for d in digits)
    return read_number(int(digits))


# "1.200" (dấu chấm ngăn nghìn), "1,5" hoặc "3.5" (thập phân), số thường; kèm "%" phía sau.
_NUMBER_RE = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+[.,]\d{1,2}(?!\d)|\d+,\d+|\d+)(?!\w)(\s?%)?"
)
_ORDINAL_RE = re.compile(r"\bthứ\s+$", re.IGNORECASE)

# Chữ viết tắt đọc thành chữ (so khớp phân biệt hoa thường, theo ranh giới từ).
_ABBREVIATION_WORDS: tuple[tuple[str, str], ...] = (
    (r"TP\.\s?HCM\b", "thành phố Hồ Chí Minh"),
    (r"TP\.\s?", "thành phố "),
    (r"v\.v\.?", "vân vân"),
    (r"NXB\b\.?", "nhà xuất bản"),
    (r"PGS\.\s?", "phó giáo sư "),
    (r"GS\.\s?", "giáo sư "),
    (r"ThS\.\s?", "thạc sĩ "),
    (r"TS\.\s?", "tiến sĩ "),
)
_ABBREVIATION_RE = re.compile("|".join(f"(?<!\\w)(?:{p})" for p, _ in _ABBREVIATION_WORDS))
_SYMBOLS: dict[str, str] = {"&": "và", "%": "phần trăm"}


@dataclass(frozen=True)
class SpokenText:
    text: str
    # Các chỗ đã đổi để màn duyệt đánh dấu: {"from": "1.200", "to": "một nghìn hai trăm"}.
    changes: list[dict[str, str]] = field(default_factory=list)


def _number_words(raw: str, before: str) -> str:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", raw):
        whole, _, frac = raw.partition(",")
        words = read_number(int(whole.replace(".", "")))
        return f"{words} phẩy {_read_digits(frac)}" if frac else words
    if m := re.fullmatch(r"(\d+)[.,](\d+)", raw):
        return f"{_read_digits(m.group(1))} phẩy {_read_digits(m.group(2))}"
    if _ORDINAL_RE.search(before) and raw in ("1", "4"):
        return "nhất" if raw == "1" else "tư"
    return _read_digits(raw)


def normalize_for_tts(text: str) -> SpokenText:
    """Đọc số, "%", "&" và vài chữ viết tắt thành chữ; phần còn lại giữ nguyên."""
    changes: list[dict[str, str]] = []

    def abbreviation(m: re.Match[str]) -> str:
        raw = m.group(0)
        for pattern, words in _ABBREVIATION_WORDS:
            if re.fullmatch(pattern, raw):
                changes.append({"from": raw.strip(), "to": words.strip()})
                return words
        return raw  # pragma: no cover - mọi nhánh của regex gộp đều có trong bảng

    def number(m: re.Match[str]) -> str:
        raw, percent = m.group(1), m.group(2)
        words = _number_words(raw, m.string[: m.start()])
        if percent:
            words += " phần trăm"
        changes.append({"from": m.group(0).strip(), "to": words})
        return words

    def symbol(m: re.Match[str]) -> str:
        words = _SYMBOLS[m.group(0)]
        changes.append({"from": m.group(0), "to": words})
        return words

    text = _ABBREVIATION_RE.sub(abbreviation, text)
    text = _NUMBER_RE.sub(number, text)
    text = re.sub(r"[&%]", symbol, text)
    return SpokenText(" ".join(text.split()), changes)


# --- Kiểm tra nguyên văn ------------------------------------------------------


def fold_spaces(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def verbatim_problems(
    hook: str | None, main: str, comment: str | None, scenes: list[SceneText]
) -> list[str]:
    """Ghép lại văn bản và lời đọc của từng phần, so với văn bản gốc đã chuẩn hoá. Rỗng là khớp:
    không mất, không thêm, không đảo câu."""
    problems: list[str] = []
    fields: tuple[tuple[Section, str | None], ...] = (
        ("hook", hook),
        ("body", main),
        ("review_cta", comment),
    )
    for section, source in fields:
        mine = [s for s in scenes if s.section == section]
        expected = fold_spaces(" ".join(paragraphs(source or "")))
        if fold_spaces(" ".join(s.text for s in mine)) != expected:
            problems.append(f"Phần {section}: văn bản các cảnh khác văn bản gốc.")
        spoken = fold_spaces(normalize_for_tts(expected).text) if expected else ""
        if fold_spaces(" ".join(s.narration for s in mine)) != spoken:
            problems.append(f"Phần {section}: lời đọc khác văn bản gốc đã chuẩn hoá.")
        if section == "hook" and len(mine) > 1:
            problems.append("Hook phải là đúng 1 cảnh.")
    return problems
