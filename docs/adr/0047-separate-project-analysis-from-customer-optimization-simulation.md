# Separate project analysis from customer optimization simulation

Status: accepted

Project analysis and customer-interaction optimization are separate modules and Docker services. The Project Analyst Sidecar receives only sanitized project evidence and never customer or business data. The Optimization Lab Module receives only explicitly selected de-identified Voice Interaction Evidence, synthetic fixtures, or sanitized administrator imports and never project files, Git state, Docker access, home-directory content, raw media, or production database volumes.

The Optimization Lab exposes one structured simulation interface and returns only a Daily Optimization Reference Report. Shell, file, Web, MCP, and production-write tools are unavailable, and the service cannot call settings, RAG publication, campaign, recommendation, or push mutation endpoints. Provider adapter implementation may be reused as code, but the services do not share containers, credentials, data volumes, or input snapshots.
