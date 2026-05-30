---
name: senior-prompt-engineer
description: Optimize prompts, design templates, evaluate RAG, and architect agentic systems. Use when designing LLM workflows, improving response quality, or implementing complex retrieval systems.
---

# Senior Prompt Engineer

Expertise in prompt engineering patterns, LLM evaluation frameworks, and agentic system design.

## Core Workflows

### 1. Prompt Optimization
Use to improve performance or reduce costs.
- **Analyze**: Check for token waste, ambiguity, and missing constraints.
- **Apply Patterns**:
  - **Ambiguity**: Add explicit format specs (e.g., "Respond in JSON").
  - **Inconsistency**: Add Role/Persona framing.
  - **Edge Cases**: Add boundary constraints.
- **Iterate**: Compare optimized versions against a baseline.

### 2. Few-Shot Example Design
- **Select Diverse Cases**: Include simple, complex, edge, and negative (what NOT to do) cases.
- **Format Consistently**: Use a clear `Input:` / `Output:` structure.
- **Validate**: Ensure examples cover the task space and follow the desired schema.

### 3. Structured Output Design
- **Define Schema**: Use JSON Schema or clear markdown bullet points.
- **Enforce Format**: Use instructions like "Respond ONLY with valid JSON. No markdown."
- **Handle Truncation**: Use stop sequences and predictable structures.

### 4. RAG Evaluation
- **Retrieval Metrics**: Measure Context Relevance and Precision@K.
- **Generation Metrics**: Measure Faithfulness (no hallucinations) and Groundedness.
- **Troubleshoot**: If retrieval is poor, check chunking and embedding strategies.

### 5. Agent Architecture
- **Pattern Selection**: Choose ReAct, Plan-Execute, or Tool-Use based on complexity.
- **Safety**: Implement tool validation and recursion limits.
- **Observability**: Log "thought" process, tool calls, and final answers.

## Common Patterns
| Pattern | Use Case |
|---------|----------|
| **Zero-shot** | Simple classification/extraction. |
| **Few-shot** | Complex formatting or specific styles. |
| **Chain-of-Thought** | Reasoning, math, multi-step logic. |
| **Role Prompting** | Setting expertise context. |
| **Structured Output** | Machine-readable interfaces. |
