"""被動語音比對服務。

流程：音訊 bytes → Whisper STT（含菜單 initial_prompt）→ 關鍵詞比對 → 品項比對
      品項比對支援：完整名稱、自動短形（去尾綴）、Admin 設定的口語別名
"""
import asyncio
import os
import re
import tempfile

import config
from repositories import menu_repository
from services.stt_service import get_stt

_SUFFIXES = ["套餐", "堡", "排", "雞", "翅", "餅", "捲", "球", "飯", "麵", "杯", "桶", "盒", "組", "包"]


def _normalize(s: str) -> str:
    return re.sub(r"[®™©\s]", "", s).replace("鷄", "雞")


def _short_forms(norm_name: str) -> list[str]:
    forms = []
    for sfx in _SUFFIXES:
        if norm_name.endswith(sfx) and len(norm_name) - len(sfx) >= 2:
            forms.append(norm_name[: -len(sfx)])
            break
    for form in forms[:]:
        for sfx in _SUFFIXES:
            if form.endswith(sfx) and len(form) - len(sfx) >= 2:
                forms.append(form[: -len(sfx)])
                break
    if len(norm_name) >= 4:
        forms.append(norm_name[:3])
    return list(dict.fromkeys(forms))


def _build_match_index(menu: list[dict], aliases: dict) -> list[tuple]:
    """回傳 [(item, form, label), ...] 所有可比對形式。"""
    index = []
    for item in menu:
        norm_name = _normalize(item.get("name", ""))
        if not norm_name:
            continue
        forms = [(norm_name, "完整名稱")]
        for sf in _short_forms(norm_name):
            forms.append((sf, f"短形「{sf}」"))
        for alias in aliases.get(item.get("id", ""), []):
            norm_alias = _normalize(alias)
            if norm_alias:
                forms.append((norm_alias, f"別名「{alias}」"))
        for form, label in forms:
            index.append((item, form, label))
    return index


def _build_whisper_prompt(menu: list[dict]) -> str:
    names = [i["name"] for i in menu if i.get("name")]
    return "麥當勞菜單：" + "、".join(names[:60])


def _get_resources() -> tuple[list[tuple], str, list[str]]:
    """回傳 (match_index, whisper_prompt, keywords)，每次呼叫都從 config + menu 重建。
    菜單與設定變動即時反映，不需額外快取失效機制。
    """
    menu = menu_repository.get_menu()
    aliases = config.get("PASSIVE_VOICE_ALIASES", {})
    if not isinstance(aliases, dict):
        aliases = {}
    keywords = config.get("PASSIVE_VOICE_KEYWORDS", [])
    if not isinstance(keywords, list):
        keywords = []

    index = _build_match_index(menu, aliases)
    prompt = _build_whisper_prompt(menu)
    return index, prompt, keywords


async def check_audio(audio_bytes: bytes) -> dict:
    """
    音訊 bytes → 比對結果 dict
    status: empty | no_keyword | no_item | hit
    """
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        index, whisper_prompt, keywords = await asyncio.to_thread(_get_resources)
        stt = get_stt()
        result = await stt.transcribe(tmp_path, initial_prompt=whisper_prompt)
        transcript = result.get("text", "").strip()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if not transcript:
        return {"status": "empty", "transcript": ""}

    matched_kw = next((kw for kw in keywords if kw and kw in transcript), None)
    if not matched_kw:
        return {"status": "no_keyword", "transcript": transcript}

    norm_t = _normalize(transcript)
    # 優先比對最長形式，避免短字觸發錯誤品項
    hit = next(
        ((item, form, label)
         for item, form, label in sorted(index, key=lambda x: len(x[1]), reverse=True)
         if form and form in norm_t),
        None,
    )
    if not hit:
        return {"status": "no_item", "transcript": transcript, "keyword": matched_kw}

    item, form, label = hit
    return {
        "status":        "hit",
        "transcript":    transcript,
        "keyword":       matched_kw,
        "matched_form":  form,
        "matched_label": label,
        "item": {
            "id":          item.get("id"),
            "name":        item.get("name"),
            "price":       item.get("price"),
            "image":       item.get("official_image_url") or item.get("image", ""),
            "description": item.get("description", ""),
            "category":    item.get("category", ""),
        },
    }
