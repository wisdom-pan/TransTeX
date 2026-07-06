"""术语表:保证全文术语翻译一致。

逐段独立翻译会导致同一术语("session"/"stateful")在不同段落译法不一。
解决:先扫描全文高频术语,让 LLM 一次性给出统一译法,再把术语表注入每段的
system prompt,使所有段落遵循同一套译名。
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

# 常见英文停用词/功能词,不作为术语候选
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "can", "will", "our", "その", "these", "those", "which", "when", "where",
    "then", "than", "into", "over", "each", "such", "also", "but", "not", "all",
    "one", "two", "may", "use", "used", "using", "based", "via", "per", "its",
    "their", "they", "them", "have", "has", "been", "more", "most", "some",
    "any", "both", "other", "only", "same", "very", "how", "why", "what",
    "figure", "table", "section", "equation", "appendix", "eq", "fig",
}

# 候选术语:2-3 个单词的名词短语(含大小写混合/驼峰/连字符的技术词)
_TERM_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9\-]*(?:\s+[A-Za-z][A-Za-z0-9\-]*){0,2})\b"
)


# 常见句首词/功能词/动词,多词短语若以此开头则不是术语
_PHRASE_STOP_STARTERS = {
    "as", "at", "we", "it", "in", "on", "of", "to", "by", "if", "is", "an",
    "a", "the", "this", "that", "these", "those", "our", "their", "its",
    "when", "where", "while", "for", "with", "from", "and", "or", "but",
    "each", "all", "both", "such", "using", "based", "given", "let", "here",
    "there", "then", "thus", "however", "moreover", "since", "because",
    "shown", "show", "note", "figure", "table", "section",
}


def extract_candidate_terms(segments: List[str], top_k: int = 40,
                            min_count: int = 4) -> List[str]:
    """从待翻译段里提取高频术语候选。

    偏好:出现次数多、含大写/连字符(技术术语特征)、非停用词/句首词。
    """
    counter: Counter[str] = Counter()
    for seg in segments:
        for m in _TERM_RE.finditer(seg):
            phrase = m.group(1).strip()
            words = phrase.split()
            if not words:
                continue
            low = phrase.lower()
            # 单词术语:必须像技术词(含大写非首字母、或含连字符、或全大写缩写)
            if len(words) == 1:
                w = words[0]
                is_techy = (
                    any(c.isupper() for c in w[1:])  # 驼峰/内部大写
                    or "-" in w
                    or (w.isupper() and len(w) >= 2)  # 缩写
                )
                if not is_techy or low in _STOPWORDS:
                    continue
            else:
                # 多词短语:开头/结尾不能是停用词或句首词(排除 "As shown in"/"We evaluate")
                if words[0].lower() in _PHRASE_STOP_STARTERS:
                    continue
                if words[0].lower() in _STOPWORDS or words[-1].lower() in _STOPWORDS:
                    continue
                # 至少一个词首字母大写(专有/术语特征),避免普通短语刷屏
                if not any(w[0].isupper() for w in words):
                    continue
            counter[phrase] += 1

    # 归并大小写不同但相同的词(取出现最多的写法)
    candidates = [(t, c) for t, c in counter.items() if c >= min_count]
    candidates.sort(key=lambda x: (-x[1], -len(x[0])))
    return [t for t, _ in candidates[:top_k]]


def format_glossary(glossary: Dict[str, str]) -> str:
    """把术语表格式化成注入 system prompt 的文本。"""
    if not glossary:
        return ""
    lines = [f"- {en} → {zh}" for en, zh in glossary.items()]
    return (
        "\n\n术语表(遇到下列术语时必须使用统一译法,保持全文一致):\n"
        + "\n".join(lines)
    )


# 让 LLM 生成术语表译法的 prompt
GLOSSARY_SYSTEM_PROMPT = """你是学术论文翻译术语专家。我会给你一批从一篇论文里提取的英文术语,
请为每个术语给出统一、专业的中文译法(或保留英文,如广泛通用的缩写)。

规则:
1. 每行输出一个:英文术语 => 中文译法
2. 人名、产品名、广泛通用的缩写(如 GPU、API、LLM)可保留英文
3. 译法要符合该领域学术习惯,简洁准确
4. 只输出术语对照,不要解释、不要编号、不要多余文字"""


def parse_glossary_response(text: str, candidates: List[str]) -> Dict[str, str]:
    """解析 LLM 返回的术语表('英文 => 中文' 每行一条)。"""
    glossary: Dict[str, str] = {}
    cand_lower = {c.lower(): c for c in candidates}
    for line in text.splitlines():
        line = line.strip().lstrip("-•* ").strip()
        if "=>" in line:
            en, _, zh = line.partition("=>")
        elif "→" in line:
            en, _, zh = line.partition("→")
        else:
            continue
        en, zh = en.strip(), zh.strip()
        if not en or not zh:
            continue
        # 只接受确实是候选里的术语(防跑偏)
        key = cand_lower.get(en.lower())
        if key:
            glossary[key] = zh
    return glossary
