
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



