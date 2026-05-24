import re


_TRAD_PHRASE_MAP = {
    "菜单": "菜單",
    "推荐": "推薦",
    "输出": "輸出",
    "简体": "簡體",
    "繁体": "繁體",
    "价格": "價格",
    "顾客": "顧客",
    "记录": "紀錄",
    "审查": "審查",
    "文本": "文本",
    "项目": "項目",
    "语音": "語音",
    "回复": "回覆",
    "后台": "後台",
}

_TRAD_CHAR_MAP = str.maketrans({
    "说": "說", "车": "車", "为": "為", "体": "體", "荐": "薦", "单": "單",
    "输": "輸", "简": "簡", "语": "語", "顾": "顧", "录": "錄", "审": "審",
    "查": "查", "项": "項", "后": "後", "台": "台", "应": "應", "请": "請",
    "这": "這", "个": "個", "买": "買", "卖": "賣", "鸡": "雞", "饭": "飯",
    "汤": "湯", "面": "麵", "饮": "飲", "号": "號", "无": "無", "发": "發",
    "会": "會", "将": "將", "与": "與", "对": "對", "错": "錯", "删": "刪",
})


def to_traditional_lite(text: str) -> str:
    out = str(text or "")
    for src, dst in _TRAD_PHRASE_MAP.items():
        out = out.replace(src, dst)
    return out.translate(_TRAD_CHAR_MAP)


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def latin_noise_count(text: str) -> int:
    cleaned = "".join(ch for ch in text or "" if ch.isalpha() or ch.isspace())
    return sum(1 for ch in cleaned if "A" <= ch.upper() <= "Z")


_EMOTION_LABEL_SYNONYMS = {
    "生氣": ["生氣", "憤怒", "怒氣", "不悅", "不爽", "氣憤", "angry", "anger", "mad", "furious"],
    "焦躁": ["焦躁", "焦慮", "急躁", "不耐", "不耐煩", "煩躁", "anxious", "irritated", "impatient", "frustrated"],
    "猶豫": ["猶豫", "遲疑", "困惑", "迷惘", "不確定", "hesitant", "confused", "uncertain", "unsure"],
    "疲憊": ["疲憊", "疲倦", "勞累", "倦怠", "tired", "exhausted", "weary"],
    "難過": ["難過", "傷心", "悲傷", "失落", "沮喪", "sad", "unhappy", "depressed", "down"],
    "開心": ["開心", "高興", "愉快", "快樂", "歡喜", "happy", "joyful", "pleased", "cheerful"],
    "平靜": ["平靜", "中性", "冷靜", "平穩", "neutral", "calm", "relaxed"],
}


def normalize_emotion_label(label: str) -> str:
    """Map free-form emotion descriptions (zh / en / mixed) onto the canonical zh label."""
    raw = str(label or "").strip().lower()
    if not raw:
        return ""
    for canonical, aliases in _EMOTION_LABEL_SYNONYMS.items():
        for alias in aliases:
            if alias.lower() in raw:
                return canonical
    return label


def remove_latin_noise(text: str) -> str:
    clean = str(text or "")
    replacements = {
        "Emotion-LLaMA": "情緒模型",
        "neutral": "平靜",
        "calm": "平靜",
        "happy": "開心",
        "tired": "疲憊",
        "confused": "困惑",
        "angry": "生氣",
        "sad": "難過",
        "customer": "顧客",
        "person": "顧客",
        "video": "影像",
    }
    for source in sorted(replacements, key=len, reverse=True):
        clean = re.sub(re.escape(source), replacements[source], clean, flags=re.IGNORECASE)
    clean = re.sub(r"[A-Za-z][A-Za-z0-9_/'’.-]*", "", clean)
    clean = re.sub(r"\s+", "", clean)
    clean = re.sub(r"[，,。；;：:]{2,}", "，", clean)
    return clean.strip(" ，,。；;：:")

