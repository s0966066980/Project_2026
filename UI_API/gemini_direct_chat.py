#!/usr/bin/env python3
"""
Gemini API 直連互動聊天範例。

重點：
- 只使用 google-genai 直接連 Gemini API。
- 不 import 專案的 ai_services/config。
- 不連 Ollama。
- 不做 fallback。
- 沒有 GEMINI_API_KEY / GOOGLE_API_KEY 就直接結束。

執行：
    cd /home/oliver/Project_2026/UI_API
    conda activate emotion_ui
    python gemini_direct_chat.py

指定模型：
    python gemini_direct_chat.py --model gemini-3-flash-preview
    python gemini_direct_chat.py --model gemini-2.5-flash

如需測試額外 generation config：
    python gemini_direct_chat.py --use-config
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from dotenv import load_dotenv
from google import genai


def mask_key(value: str) -> str:
    if not value:
        return "未設定"
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def build_prompt(history: list[tuple[str, str]], question: str) -> str:
    turns = [
        "你是一個直接連線 Gemini API 的互動聊天助手。",
        "請使用繁體中文回答，除非使用者要求其他語言。",
        "",
    ]
    for user_text, model_text in history[-6:]:
        turns.append(f"使用者：{user_text}")
        turns.append(f"Gemini：{model_text}")
    turns.append(f"使用者：{question}")
    turns.append("Gemini：")
    return "\n".join(turns)


def ask_gemini(
    client,
    model: str,
    history: list[tuple[str, str]],
    question: str,
    use_config: bool,
    temperature: float,
    max_output_tokens: int,
) -> str:
    prompt = build_prompt(history, question)
    kwargs = {"model": model, "contents": prompt}
    if use_config:
        from google.genai import types

        kwargs["config"] = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    response = client.models.generate_content(**kwargs)
    return (response.text or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini API 直連互動聊天。")
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Gemini API model name")
    parser.add_argument(
        "--use-config",
        action="store_true",
        help="加上 GenerateContentConfig；預設不加，方便隔離模型端 500。",
    )
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("錯誤：找不到 GEMINI_API_KEY 或 GOOGLE_API_KEY。請先在 UI_API/.env 設定。")
        return 2

    client = genai.Client(api_key=api_key)
    history: list[tuple[str, str]] = []

    print("Gemini Direct Chat")
    print("model:", args.model)
    print("mode:", "generate_content + config" if args.use_config else "simple generate_content")
    print("api_key:", mask_key(api_key))
    print("輸入問題後按 Enter；輸入 exit / quit / q 離開。")

    while True:
        try:
            question = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n結束。")
            return 0

        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            print("結束。")
            return 0

        start = time.perf_counter()
        try:
            answer = ask_gemini(
                client,
                args.model,
                history,
                question,
                args.use_config,
                args.temperature,
                args.max_output_tokens,
            )
        except Exception as exc:
            print("\nGemini API 錯誤：", exc)
            print("沒有使用任何備援。")
            continue

        elapsed = time.perf_counter() - start
        history.append((question, answer))
        print("\nGemini：", answer)
        print(f"[耗時 {elapsed:.2f}s]")


if __name__ == "__main__":
    sys.exit(main())
