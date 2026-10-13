# Architecture

## Overview

```
 Browser (React + TypeScript, Vite build)
        │  JSON over HTTPS, session cookie + CSRF token
        │  X-Organization header selects the active organisation
        ▼
 Django + Django REST Framework  (/api/v1/...)
   ├─ accounts    users, organisations, branches, memberships, invitations
   ├─ catalog     categories, units, products, suppliers
   ├─ inventory   stock ledger, balances, adjustments, transfers
   ├─ purchasing  requisitions, purchase orders, goods receipts
   ├─ sales       customers, invoices, receipts, credit notes, customer ledger
   ├─ reports     read-only queries and CSV export
   ├─ audit       append-only audit events
   └─ core        org scoping, permissions, document numbering, money helpers, health
        │
        ▼
 PostgreSQL 16
```

The frontend and backend are separate projects. In development, Vite proxies
`/api` to Django so the browser sees one origin and the session cookie and CSRF
protection work without CORS. In production, a reverse proxy (or WhiteNoise for
the static build) serves both under one domain.

### Why session authentication instead of JWT

The only client is our own browser app on the same domain. Django sessions give
server-side logout, password-change invalidation and CSRF protection with no
token storage in JavaScript. If a mobile app or third-party API client is
added, token authentication can be enabled for those clients alongside.

## Organisation scoping

Every business record carries `organization_id`. Views inherit from
`OrgScopedViewSet`, which:

1. Resolves the active organisation from the `X-Organization` header (or the
   user's only membership if they have one).
2. Rejects the request with 403 if the user has no active membership there.
3. Filters every queryset by that organisation and sets it on every create.
4. Checks the role's permission for the action (`apps/core/permissions.py`).

Lookups by ID go through the filtered queryset, so a valid ID from another
organisation returns 404, never the record.

## Roles

| Permission | Owner | Admin | Manager | Clerk | Auditor |
|---|:-:|:-:|:-:|:-:|:-:|
| Manage organisation settings | ✓ | | | | |
| Manage users and branches | ✓ | ✓ | | | |
| Manage products, suppliers, customers | ✓ | ✓ | ✓ | | |
| View cost prices and stock value | ✓ | ✓ | ✓ | | ✓ |
| Record receipts, issues, transfers | ✓ | ✓ | ✓ | ✓ | |
| Stock adjustments | ✓ | ✓ | ✓ | | |
| Create requisitions | ✓ | ✓ | ✓ | ✓ | |
| Create and submit purchase orders | ✓ | ✓ | ✓ | | |
| Approve purchase orders | ✓ | ✓ | ✓* | | |
| Receive goods | ✓ | ✓ | ✓ | ✓ | |
| Invoices, receipts, credit notes | ✓ | ✓ | ✓ | | |
| View reports | ✓ | ✓ | ✓ | | ✓ |
| Export CSV | ✓ | ✓ | | | ✓ |
| View audit log | ✓ | ✓ | | | ✓ |

\* Managers can approve orders up to the organisation's configured approval
limit. Above it, an owner or administrator must approve.

A membership can be restricted to one branch; clerks restricted this way can
only record movements at that branch.

## Data integrity rules

- **Money** is `Decimal(18,2)` with an explicit ISO currency code on every
  document. Unit costs are `Decimal(18,4)`. Quantities are `Decimal(14,3)` so
  that metres of cable and kilograms of nails work; units that cannot be
  split (bags, pieces) reject fractional quantities.
- **Timestamps** are timezone-aware (UTC in the database, Africa/Nairobi by
  default for display and for business dates, configurable per organisation).
- **Stock** is held in `StockBalance` (one row per branch and product) and
  changed only by `inventory.services.post_movement`, which locks the balance
  row with `SELECT ... FOR UPDATE`, validates, writes an immutable
  `StockMovement`, and updates the balance in one transaction. The
  `reconcile_stock` management command recomputes balances from movements and
  reports any difference.
- **Costing** uses the weighted average cost per branch. A receipt changes the
  average: `(old_qty × old_avg + qty × cost) / (old_qty + qty)`. Issues,
  outgoing transfers and negative adjustments go out at the current average.
  Incoming transfers arrive at the source branch's cost. Customer returns come
  back at the cost recorded on the original issue.
- **Negative stock** is rejected unless the organisation enables it. When
  enabled, every movement that takes a balance below zero writes a flagged
  audit event, and the average cost is left unchanged while the balance is
  negative.
- **Corrections** never edit history. A wrong receipt is reversed with a
  compensating movement; a wrong invoice is voided (which writes reversing
  stock and ledger entries) or corrected with a credit note.
- **Status changes** (approve, receive, issue, void) lock the document row and
  check the current status inside the transaction, so two people clicking
  "Approve" at the same time produce one approval and one clear error.
- **Document numbers** (PO-000001, INV-000001, ...) come from a per-organisation
  sequence row locked during allocation, so numbers are unique and gap-free
  within a committed transaction.
- **Audit events** are inserted by the services that perform the action. A
  PostgreSQL trigger rejects UPDATE and DELETE on the audit table.

## Schema

See [ERD.md](ERD.md) for the entity relationship diagram and field list.
