# Material Planning System — Documentation

This folder contains the project documentation.

| Document | Audience | Contents |
|----------|----------|----------|
| [**Functional Documentation**](FUNCTIONAL_DOCUMENTATION.md) | Business users, planners, stakeholders | What the system does, roles, concepts, the settings hierarchy, how indent quantities are calculated, every functional module, and end-to-end workflows. |
| [**Technical Documentation**](TECHNICAL_DOCUMENTATION.md) | Developers, integrators, operators | Architecture, tech stack, data model, settings-resolution engine, indent & forecasting algorithms, data-mining framework, scheduler, auth, full API reference, frontend architecture, configuration, and deployment. |

**Quick start (local):**
```bash
docker compose up -d --build
# Frontend: http://localhost:14030
# API:      http://localhost:14020   (docs at /docs)
# Default login: admin / Admin@123   (change in production)
```
