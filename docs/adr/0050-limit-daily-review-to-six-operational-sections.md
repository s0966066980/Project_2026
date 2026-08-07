# Limit daily review to six operational sections

Status: accepted

Every Daily Review Analyzer Profile receives the same Daily Operations Review Surface with six sections: current API connectivity; accepted voice, recommendation, and campaign clicks plus Confirmed Order Value; voice success and STT, LLM, TTS, retry, or correction outcomes; RAG hits, misses, suspected knowledge gaps, and issue clusters; aggregate emotion distribution and intensity plus de-identified voice-interaction analysis; and classified findings, reference guidance, offline tests, and risks.

The interface excludes database internals, complete system logs, member and order details, raw media, and individual emotion records. An analyzer cannot request or discover additional production data, so Codex, Claude, and Grok receive equivalent bounded evidence despite their different native models and effort controls.
