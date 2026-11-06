"""文本清洗与分词。

中文没有空格，BM25 与哈希嵌入都需要自己切词：
这里用「汉字 unigram + bigram + ASCII 词 + 数字」，既覆盖术语（H100、MFU、KV Cache），
也保证「显存」「利用率」这类双字术语能整词命中。
"""

from __future__ import annotations

import re
import zlib

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_ASCII = re.compile(r"[a-z0-9][a-z0-9._+/#-]*")
_WS = re.compile(r"\s+")
_HEADER_NOISE = re.compile(r"^AI Infra 全栈实战.*$")
_PAGE_NO = re.compile(r"^\d{1,4}$")

_STOP_UNIGRAM = set("的了是在和与及或这那其为个有不也就都而中对上下等被我你他")

_SENTENCE_END = "。！？；"


def clean_line(line: str) -> str:
    """去掉页眉、页码和多余空白。"""

    text = line.replace("\u3000", " ").strip()
    if not text or _PAGE_NO.match(text) or _HEADER_NOISE.match(text):
        return ""
    return _WS.sub(" ", text)


def normalize(text: str) -> str:
    return _WS.sub(" ", text.replace("\u3000", " ")).strip()


def join_lines(prev: str, nxt: str) -> str:
    """PDF 硬换行拼接：中英文之间补空格，其余直接相连。"""

    if not prev:
        return nxt
    if prev[-1].isascii() and prev[-1].isalnum() and nxt[0].isascii() and nxt[0].isalnum():
        return f"{prev} {nxt}"
    return prev + nxt


def split_sentences(text: str) -> list[str]:
    """按中文句末标点切句，保留标点。"""

    parts = re.split(f"(?<=[{_SENTENCE_END}])", text)
    return [p.strip() for p in parts if p.strip()]


def tokens(text: str) -> list[str]:
    """分词：ASCII 词 + 数字 + 汉字 bigram + 汉字 unigram。"""

    lowered = text.lower()
    out: list[str] = []
    out.extend(_ASCII.findall(lowered))
    for run in _CJK_RUN.findall(lowered):
        if len(run) == 1:
            out.append(run)
            continue
        out.extend(run[i : i + 2] for i in range(len(run) - 1))
        out.extend(ch for ch in run if ch not in _STOP_UNIGRAM)
    return out


def fts_text(text: str) -> str:
    """FTS5 入库文本：预先切好词，查询侧用同一分词器，避免 unicode61 对中文整段切分。"""

    return " ".join(tokens(text))


def fts_query(text: str) -> str:
    """查询侧用 OR 连接：FTS5 默认是 AND，会让长查询几乎无法命中。"""

    return " OR ".join(f'"{t}"' for t in dict.fromkeys(tokens(text)))


def normalize_query(text: str) -> str:
    """统一厂商简称，避免「字节跳动」把只写「字节」的正确表格行挤出前列。"""

    aliases = {
        "字节跳动": "字节",
        "阿里巴巴": "阿里",
        "腾讯云": "腾讯",
        "阿里云": "阿里",
        "英伟达": "NVIDIA",
        "算力集群": "集群",
    }
    out = text
    for src, dst in aliases.items():
        out = out.replace(src, dst)
    return out


def hash_token(token: str) -> tuple[int, float]:
    """稳定哈希（crc32 不受进程随机化影响），返回 (桶号, 符号)。"""

    h = zlib.crc32(token.encode("utf-8"))
    return h, 1.0 if (h >> 20) & 1 else -1.0


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
