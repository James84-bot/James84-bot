# JMH Ops

Stock, purchasing and customer-balance control for Kenyan distributors,
wholesalers and hardware suppliers. By JMH Automation.

**Current stage: validating the idea.** Nothing is ready for use.

| Document | What it covers |
|---|---|
| [docs/VALIDATION.md](docs/VALIDATION.md) | Assumptions, interview plan, decision gate. Start here. |
| [docs/PLAN.md](docs/PLAN.md) | Target users, feature briefs, provisional phases, what is left out |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Proposed technical design, roles, data integrity rules |
| [docs/interviews/](docs/interviews/) | Interview template and (anonymised) notes |

`backend/` holds a parked Django + PostgreSQL scaffold (roles, organisation
isolation, stock ledger, transfers, audit log). It has no tests yet and is not
to be extended until the decision gate in VALIDATION.md is passed.
