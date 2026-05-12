# -*- coding: utf-8 -*-
"""
共享工具模块 — 日志、缓存、常量
"""

import logging
import time
from functools import wraps
from typing import Dict, Tuple, Optional

# ============ 日志配置 ============

def setup_logger(name: str = "sentiment_analysis", level: int = logging.INFO) -> logging.Logger:
    """创建统一的日志记录器"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger


log = setup_logger()


# ============ 中文停用词 & 情感词库 ============

STOPWORDS = frozenset({
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
    "吗", "还", "什么", "那", "就是", "可以", "吧", "呢",
    "被", "比", "从", "得", "等", "地", "对", "而", "个", "给",
    "跟", "过", "让", "些", "因为", "由于", "所以", "但是",
    "如果", "虽然", "而且", "或者", "以及", "还是", "已经",
    "但", "来", "这个", "那个", "时候", "其实", "可能",
    "大家", "不要", "一下", "比较", "真的", "觉得",
    "一些", "需要", "现在", "应该", "没有",
})

POSITIVE_WORDS = {
    "好": 1, "不错": 2, "喜欢": 2, "推荐": 3, "优秀": 3, "赞": 1,
    "厉害": 2, "方便": 2, "值得": 3, "看好": 3, "满意": 3, "实用": 2,
    "棒": 1, "支持": 2, "惊喜": 3, "进步": 2, "突破": 3, "成功": 2,
    "提升": 2, "效率": 2, "性价比": 2, "优势": 2, "领先": 3,
    "可靠": 2, "稳定": 2, "创新": 2, "友好": 1, "易用": 2,
    "清晰": 1, "完美": 3, "强大": 3, "出色": 3, "便捷": 2,
    "流畅": 2, "简洁": 1, "专业": 2,
}

NEGATIVE_WORDS = {
    "差": 2, "烂": 3, "失望": 3, "垃圾": 3, "坑": 2, "不好": 2,
    "问题": 1, "难用": 2, "后悔": 3, "骗": 3, "差劲": 3, "忽悠": 2,
    "泡沫": 2, "别买": 3, "过热": 1, "不行": 2, "差评": 3, "退款": 2,
    "bug": 2, "缺点": 2, "不足": 2, "缺陷": 3, "卡顿": 2, "崩溃": 3,
    "复杂": 1, "麻烦": 2, "不满意": 3, "误导": 2, "质量差": 3,
    "不推荐": 3, "不值": 3, "夸大": 2, "粗糙": 2, "繁琐": 2,
}

NEGATION_WORDS = frozenset({
    "不", "没", "无", "非", "别", "未", "否", "莫",
    "没有", "并不", "绝不", "毫无", "并非",
})

# 含有"不"的正面复合词（"不"不是真正的否定，而是词的一部分）
# "不错"=good, "不赖"=not bad, "不简单"=impressive 等
NOT_NEGATION_COMPOUNDS = frozenset({
    "不错", "不赖", "不简单", "不得了", "不一般", "不寻常",
    "不差", "不丢人", "不客气", "不客气地", "不含糊",
    "不用说", "不在话下", "不折不扣", "不慌不忙",
})

PRONOUNS = frozenset({"我", "你", "他", "她", "它", "我们", "你们", "他们", "她们",
                      "自己", "别人", "大家", "有人", "某人"})

PUNCTUATION = set('，。！？、；：""\'\'（）\n,.!?;:"() \t\r\u3000')


# ============ 简单内存缓存 ============

class SimpleCache:
    """简单的 TTL 内存缓存"""

    def __init__(self, ttl_seconds: int = 300):
        self._store: Dict[str, Tuple[float, object]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[object]:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: object) -> None:
        self._store[key] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)