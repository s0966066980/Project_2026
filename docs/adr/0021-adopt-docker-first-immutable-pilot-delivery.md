# Adopt Docker-First Immutable Pilot Delivery

Status: accepted

Project_2026 uses the Containerized Application Runtime as its sole supported development, verification, and deployment boundary; host-native Python and Conda launch paths are removed from the application contract. Development may build images from the working tree and use the repository `.env`, but a Pilot uses only CI-built GHCR images pinned by digest together with its host-external Pilot Configuration Authority. Short-lived branches and pull requests supply required CI evidence before merge, then are deleted so `main` remains the only long-lived branch. This trades some local immediacy for one reproducible artifact across verification, deployment, and rollback, and prevents an on-host rebuild or layered environment file from silently creating an untested release.
