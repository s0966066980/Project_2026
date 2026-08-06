# Test daily optimization without production mutation

Status: accepted

Daily customer and voice evidence may currently be explored only through a manually triggered Daily Optimization Simulation. A simulation consumes an explicitly selected sanitized dataset and returns a report marked `reference_only` with possible Kiosk LLM or prompt adjustments, possible RAG Knowledge Items, offline evaluation results, risks, and evidence. The report has no apply or publish action. The simulation cannot update live settings, production knowledge, the Published index, recommendations, campaigns, or push state and cannot create an applicable project patch or schedule another run.

Automatic completion and publishing belong to a future Production Optimization Loop. That future capability receives no authority from the current simulation or Project Core Brain decisions and requires separate decisions for data governance, acceptance gates, rollback, release ownership, and whether aggregate emotion evidence may participate.
