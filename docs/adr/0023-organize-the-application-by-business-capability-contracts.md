# Organize the Application by Business Capability Contracts

Status: accepted

Project_2026 remains a modular monolith organized as ten vertical Business Capability Modules rather than horizontal route/service/repository layers or immediate microservices. Each module owns one Capability Interface, one versioned capability-centered HTTP API, its operation-level permissions, and the sole write authority for its business records in the shared PostgreSQL instance; in-process collaboration uses typed interfaces, durable consequences use events/outbox, and internal loopback HTTP or cross-module repository access is forbidden. FastAPI/Pydantic generates the reviewed OpenAPI artifact and sole TypeScript client, so Admin and Kiosk feature code does not hand-write transport calls. This preserves single-store transaction simplicity while allowing each capability to be tested, migrated, disabled, or degraded according to its declared criticality.
