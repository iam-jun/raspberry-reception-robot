from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


FALLBACK_MESSAGE = (
    "Hiện tại em chưa tìm thấy thông tin này trong tài liệu đã được nạp. "
    "Anh/chị vui lòng liên hệ bộ phận tuyển sinh UIT để được hỗ trợ chính xác hơn."
)

MAX_ANSWER_CHARS = 900

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bus_route": ("bus", "xe bus", "xe buýt", "tuyến xe", "di chuyển", "đhqg", "đại học quốc gia", "tuyến"),
    "tuition": ("học phí", "phí", "tiền học"),
    "dormitory": ("ký túc xá", "ktx", "chỗ ở", "ăn ở", "sinh hoạt"),
    "major_transfer": ("chuyển ngành", "đổi ngành"),
    "double_degree": ("song bằng", "bằng thứ hai", "hai bằng"),
    "campus_location": ("cơ sở", "học ở đâu", "địa chỉ", "vị trí"),
    "school_code": ("mã trường", "mã tuyển sinh"),
    "contact": ("liên hệ", "hotline", "email", "tư vấn"),
}

STOPWORDS = {
    "anh",
    "chị",
    "cho",
    "có",
    "của",
    "em",
    "gì",
    "hỏi",
    "không",
    "là",
    "mới",
    "muốn",
    "nào",
    "nhất",
    "ở",
    "thì",
    "thông",
    "tin",
    "tôi",
    "trong",
    "uit",
    "và",
    "về",
}


@dataclass
class Candidate:
    text: str
    score: float
    chunk: dict[str, Any]


class LocalAnswerComposer:
    def compose_answer(
        self,
        question: str,
        retrieved_chunks: list[dict[str, Any]],
        min_score: float | None = None,
    ) -> dict[str, Any]:
        intent = detect_intent(question)
        candidates = self._rank_candidates(question, retrieved_chunks, intent)
        threshold = min_score if min_score is not None else _threshold_for_intent(intent)
        useful = [candidate for candidate in candidates if candidate.score >= threshold]

        if not useful or not _question_is_supported(question, useful, intent):
            return {"answer": FALLBACK_MESSAGE, "used_chunks": [], "confidence": "low"}

        answer, selected = self._compose_by_intent(intent, useful)
        if not answer:
            return {"answer": FALLBACK_MESSAGE, "used_chunks": [], "confidence": "low"}

        used_chunks = _used_chunks(selected)
        confidence = _confidence(useful[0].score, len(used_chunks))
        return {"answer": _limit_answer(answer), "used_chunks": used_chunks, "confidence": confidence}

    def _rank_candidates(self, question: str, chunks: list[dict[str, Any]], intent: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        question_terms = _tokens(question)
        for chunk in chunks:
            for sentence in _candidate_sentences(chunk.get("text", "")):
                score = _score_candidate(question, question_terms, sentence, intent)
                if score > 0:
                    candidates.append(Candidate(text=sentence, score=score, chunk=chunk))
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates

    def _compose_by_intent(self, intent: str, candidates: list[Candidate]) -> tuple[str, list[Candidate]]:
        if intent == "bus_route":
            return _compose_bus_answer(candidates)
        if intent == "tuition":
            return _compose_tuition_answer(candidates)
        if intent == "dormitory":
            return _compose_topic_answer(
                "Theo tài liệu tuyển sinh UIT, thông tin về ký túc xá/chỗ ở là:",
                candidates,
                intent,
            )
        if intent == "major_transfer":
            return _compose_topic_answer(
                "Theo tài liệu tuyển sinh UIT, sinh viên được xét chuyển ngành khi đáp ứng các điều kiện sau:",
                candidates,
                intent,
            )
        if intent == "double_degree":
            return _compose_topic_answer(
                "Theo tài liệu tuyển sinh UIT, thông tin về học song bằng là:",
                candidates,
                intent,
            )
        if intent == "campus_location":
            return _compose_topic_answer(
                "Theo tài liệu tuyển sinh UIT, thông tin về cơ sở học tập là:",
                candidates,
                intent,
            )
        if intent == "school_code":
            return _compose_topic_answer(
                "Theo tài liệu tuyển sinh UIT, thông tin mã trường là:",
                candidates,
                intent,
            )
        if intent == "contact":
            return _compose_topic_answer(
                "Theo tài liệu tuyển sinh UIT, thông tin liên hệ/tư vấn là:",
                candidates,
                intent,
            )
        return _compose_topic_answer("Theo tài liệu tuyển sinh UIT:", candidates, intent)


def detect_intent(question: str) -> str:
    normalized = _normalize(question)
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(_normalize(keyword) in normalized for keyword in keywords):
            return intent
    return "general"


def _candidate_sentences(text: str) -> list[str]:
    text = _remove_frontmatter(text)
    lines = []
    for raw_line in text.splitlines():
        line = _clean_markdown(raw_line)
        if not line:
            continue
        for part in _split_sentence_like(line):
            clean = _clean_markdown(part)
            if _has_enough_information(clean):
                lines.append(clean)
    return _dedupe(lines)


def _remove_frontmatter(text: str) -> str:
    return re.sub(r"^---\s.*?\s---", "", text, flags=re.DOTALL).strip()


def _clean_markdown(text: str) -> str:
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text.strip())
    text = re.sub(r"^\s*[-*]\s*", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -")


def _split_sentence_like(line: str) -> list[str]:
    if len(line) <= 260:
        return [line]
    parts = re.split(r"(?<=[.!?])\s+|\s+(?=(?:Các tuy[eế]n|Tuy[eế]n|Mã trường|Sinh viên|Điểm|Đạt)\b)", line)
    if len(parts) == 1:
        parts = re.split(r"\s{2,}|;\s+", line)
    return [part.strip() for part in parts if part.strip()]


def _has_enough_information(text: str) -> bool:
    tokens = _tokens(text)
    return len(tokens) >= 3 and len(text) >= 12


def _score_candidate(question: str, question_terms: set[str], sentence: str, intent: str) -> float:
    sentence_norm = _normalize(sentence)
    sentence_terms = _tokens(sentence)
    if not sentence_terms:
        return 0.0

    overlap = len(question_terms & sentence_terms)
    score = overlap / max(len(question_terms), 1)

    for keyword in INTENT_KEYWORDS.get(intent, ()):
        keyword_norm = _normalize(keyword)
        if keyword_norm in sentence_norm:
            score += 0.42

    question_norm = _normalize(question)
    for phrase in _important_phrases(question_norm):
        if phrase in sentence_norm:
            score += 0.35

    if len(sentence) > 420:
        score -= 0.28
    elif len(sentence) > 260:
        score -= 0.12
    if len(sentence_terms) > 70:
        score -= 0.18

    if intent != "general" and not _contains_intent_keyword(sentence, intent):
        score -= 0.35

    return max(score, 0.0)


def _compose_bus_answer(candidates: list[Candidate]) -> tuple[str, list[Candidate]]:
    bus_candidates = [
        candidate
        for candidate in candidates
        if _contains_intent_keyword(candidate.text, "bus_route") and re.search(r"\d+", candidate.text)
    ]
    if not bus_candidates:
        return "", []

    daily_numbers: list[str] = []
    nearby_numbers: list[str] = []
    supporting_lines: list[str] = []
    selected: list[Candidate] = []
    for candidate in bus_candidates[:5]:
        text = _trim_after_unrelated(candidate.text)
        numbers = _route_numbers(text)
        if not numbers:
            continue
        selected.append(candidate)
        normalized = _normalize(text)
        if "hang ngay" in normalized or "trung tam" in normalized or "dhqg" in normalized:
            daily_numbers.extend(numbers)
        elif "lan can" in normalized or "suoi tien" in normalized or "nong lam" in normalized:
            nearby_numbers.extend(numbers)
        else:
            supporting_lines.append(text)

    parts = []
    if daily_numbers:
        parts.append(
            "Theo tài liệu tuyển sinh UIT, các tuyến xe buýt hằng ngày từ trung tâm thành phố đến ĐHQG-HCM gồm: "
            + ", ".join(_dedupe(daily_numbers))
            + "."
        )
    if nearby_numbers:
        parts.append("Ngoài ra, một số tuyến lân cận gồm: " + ", ".join(_dedupe(nearby_numbers)) + ".")
    if not parts and supporting_lines:
        parts.append("Theo tài liệu tuyển sinh UIT, các tuyến xe buýt liên quan gồm: " + _join_lines(supporting_lines[:3]))
    return " ".join(parts), selected


def _compose_tuition_answer(candidates: list[Candidate]) -> tuple[str, list[Candidate]]:
    selected = [candidate for candidate in candidates if _is_topic_candidate(candidate.text, "tuition")]
    if not selected:
        return "", []

    for candidate in selected:
        normalized = _normalize(candidate.text)
        amounts = re.findall(r"\b\d{1,3}(?:\.\d{3}){2,}\b", candidate.text)
        if "2025 2026" in normalized and "chinh quy" in normalized and amounts:
            amount = amounts[3] if len(amounts) >= 4 else amounts[-1]
            return (
                f"Theo tài liệu tuyển sinh UIT, học phí dự kiến năm học 2025-2026 đối với chương trình chính quy là {amount} đồng/năm học.",
                [candidate],
            )

    return (
        "Theo tài liệu tuyển sinh UIT, thông tin học phí liên quan là: "
        + _join_lines([candidate.text for candidate in selected[:3]]),
        selected[:3],
    )


def _compose_topic_answer(prefix: str, candidates: list[Candidate], intent: str) -> tuple[str, list[Candidate]]:
    selected = []
    for candidate in candidates:
        if _is_topic_candidate(candidate.text, intent):
            selected.append(candidate.text)
        if len(selected) >= 5:
            break
    if not selected:
        return "", []
    selected_candidates = []
    selected_texts = set(selected)
    for candidate in candidates:
        if candidate.text in selected_texts:
            selected_candidates.append(candidate)
    return f"{prefix} {_join_lines(selected)}", selected_candidates


def _join_lines(lines: list[str]) -> str:
    cleaned = [_clean_markdown(line).rstrip(".") for line in _dedupe(lines)]
    text = "; ".join(cleaned)
    return text + ("." if text and not text.endswith(".") else "")


def _route_numbers(text: str) -> list[str]:
    numbers = []
    for number in re.findall(r"\b\d{1,3}\b", text):
        if number.startswith("0") and len(number) > 1:
            continue
        numbers.append(number)
    return numbers


def _trim_after_unrelated(text: str) -> str:
    return re.split(r"\bThông tin khác\b|\[\d{4}\]|Tuyển sinh chung", text, maxsplit=1)[0].strip()


def _is_topic_candidate(text: str, intent: str) -> bool:
    normalized = _normalize(text)
    if intent == "general":
        return True
    if intent == "tuition":
        if any(term in normalized for term in ("ky tuc xa", "xe bus", "xe buyt", "giay bao nhap hoc")):
            return False
        if "mon hoc tu chon" in normalized:
            return False
        return "hoc phi" in normalized or "tien hoc" in normalized or (
            "chinh quy" in normalized and bool(re.search(r"\d{1,3}(?:\.\d{3}){2,}", text))
        )
    if intent == "bus_route":
        return _contains_intent_keyword(text, intent) and bool(_route_numbers(text))
    if intent == "dormitory":
        return any(term in normalized for term in ("ky tuc xa", "ktx", "cho o", "an o", "sinh hoat")) and not any(
            term in normalized for term in ("xe bus", "xe buyt", "tuyen")
        )
    return _contains_intent_keyword(text, intent)


def _contains_intent_keyword(text: str, intent: str) -> bool:
    normalized = _normalize(text)
    return any(_normalize(keyword) in normalized for keyword in INTENT_KEYWORDS.get(intent, ()))


def _question_is_supported(question: str, candidates: list[Candidate], intent: str) -> bool:
    question_norm = _normalize(question)
    combined = " ".join(_normalize(candidate.text) for candidate in candidates[:5])
    if "nganh y" in question_norm:
        return "nganh y" in combined or "y khoa" in combined
    if intent != "general":
        return any(_contains_intent_keyword(candidate.text, intent) for candidate in candidates[:5])
    return candidates[0].score >= 0.42


def _threshold_for_intent(intent: str) -> float:
    return 0.35 if intent == "general" else 0.28


def _confidence(score: float, used_chunk_count: int) -> str:
    if score >= 0.78 or (score >= 0.62 and used_chunk_count >= 1):
        return "high"
    if score >= 0.42:
        return "medium"
    return "low"


def _used_chunks(candidates: list[Candidate]) -> list[dict[str, Any]]:
    used: dict[str, dict[str, Any]] = {}
    for candidate in candidates[:6]:
        chunk = candidate.chunk
        chunk_id = chunk.get("chunk_id", "")
        if not chunk_id:
            continue
        item = used.setdefault(
            chunk_id,
            {
                **chunk,
                "relevant_preview": candidate.text,
                "relevant_score": round(candidate.score, 6),
            },
        )
        if candidate.score > item.get("relevant_score", 0):
            item["relevant_preview"] = candidate.text
            item["relevant_score"] = round(candidate.score, 6)
    return list(used.values())


def _limit_answer(answer: str) -> str:
    answer = re.sub(r"\s+", " ", answer).strip()
    if len(answer) <= MAX_ANSWER_CHARS:
        return answer
    return answer[:MAX_ANSWER_CHARS].rsplit(" ", 1)[0].rstrip(".,;") + "."


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        key = _normalize(item)
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _important_phrases(normalized_question: str) -> list[str]:
    phrases = []
    for intent_keywords in INTENT_KEYWORDS.values():
        for keyword in intent_keywords:
            normalized_keyword = _normalize(keyword)
            if normalized_keyword in normalized_question and " " in normalized_keyword:
                phrases.append(normalized_keyword)
    return phrases


def _tokens(text: str) -> set[str]:
    normalized = _normalize(text)
    words = re.findall(r"\b[\w]+\b", normalized, flags=re.UNICODE)
    return {word for word in words if len(word) > 1 and word not in STOPWORDS}


def _normalize(text: str) -> str:
    text = text.lower().replace("đ", "d")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()
