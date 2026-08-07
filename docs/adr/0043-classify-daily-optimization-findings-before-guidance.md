# Classify daily optimization findings before guidance

Status: accepted

Every Daily Optimization Simulation finding is classified before the reference-only report suggests a response. The fixed categories are RAG Knowledge Gap, Prompt Behavior, Model Capability, Product Pipeline, and Insufficient Evidence. RAG guidance may follow only a knowledge gap; prompt guidance only a response-style, format, or policy mismatch; model guidance only a supported quality, latency, or stability issue; and product guidance covers Kiosk, STT, TTS, transport, and workflow faults.

The simulation cannot rewrite multiple layers merely because one interaction failed. Insufficient Evidence produces an observation and evidence request rather than a change recommendation. The classification and cited evidence remain visible in the report so an administrator can challenge the attribution.
