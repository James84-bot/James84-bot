# JMH Ops — Delivery plan

This document records what we are building, for whom, and in what order. Each
module has a short brief answering the five questions agreed before any
feature is built. A feature that cannot answer them, or cannot be built
reliably, is listed under "Left out" with the reason.

## Target users

Small and medium Kenyan distributors, wholesalers and hardware suppliers with
one to ten branches, 200 to 20,000 stock items, a handful of office staff and
store clerks, and customers who buy on credit. Typical example: a hardware
wholesaler in Industrial Area, Nairobi with a second branch in Thika, buying
cement, steel and paint from local manufacturers and importers, and selling on
30-day terms to contractors and retail hardware shops.

## Phases

Phase V comes first. Phases 1–5 below are provisional and will be re-ordered or cut based on its result; the sales module in particular is on hold pending the eTIMS question in VALIDATION.md §3.1.

| Phase | Scope | Exit criteria |
|---|---|---|
| V | Validate the idea with 10 businesses — see [VALIDATION.md](VALIDATION.md) | Decision gate recorded |
| 0 | Plan, architecture, schema, tooling, Docker Compose | Docs reviewed, empty app boots, CI command runs |
| 1 | Accounts, organisations, branches, roles; products, suppliers; stock ledger (opening stock, receipts, issues, adjustments); audit log; sign-in and stock screens | Tests for auth, roles, org isolation, stock ledger, concurrency pass |
| 2 | Inter-branch transfers; purchase requisitions, purchase orders, approval, receiving | Partial and over-receipt tests pass; PO cannot be approved twice |
| 3 | Customers, invoices, receipts with allocation, credit notes and returns, customer ledger | Partial payment and balance tests pass |
| 4 | Reports (valuation, low stock, movements, purchasing, sales, balances and ageing), CSV export, dashboard from live queries | Export permission tests pass; figures match ledger |
| 5 | Full frontend workflow, demo organisation, README, ERD, API docs, backup/restore, deployment notes | Portfolio workflow runs end to end from documented commands |

Each phase ends with migrations applied, tests and linters green, and a short
report of files changed, tests run and remaining risks.

## Feature briefs

### Sign-in, organisations, branches and roles

1. **Who:** Business owners who need to control who can see and change what; staff who need their own login.
2. **Problem:** Shared logins mean nobody can tell who changed a price or adjusted stock. Clerks can see margins and customer balances they should not.
3. **Today:** One shared password on a desktop accounting package, or an Excel file on a shared drive.
4. **Improvement:** Personal accounts, five fixed roles with server-enforced permissions, optional branch restriction, and invitations so the owner never handles anyone else's password.
5. **Test:** Each role is exercised against each protected endpoint; a user from one organisation cannot read or change another organisation's records by guessing IDs.

### Products and stock ledger

1. **Who:** Store clerks receiving and issuing goods; managers checking what is on hand.
2. **Problem:** Stock counts drift because nobody records why a quantity changed. Two clerks can sell the last ten bags of cement at the same time.
3. **Today:** Bin cards, a stock book or a spreadsheet updated at the end of the day, reconciled at the monthly count.
4. **Improvement:** Every change is a movement with a reason, person, time and source document. Quantity on hand is maintained from those movements inside a database transaction with a row lock, so overselling is impossible unless the business has switched on a negative-stock policy.
5. **Test:** Receipts, issues, adjustments and transfers update balances and cost correctly; an issue larger than stock fails; two parallel issues for the last units cannot both succeed; a reconciliation command proves balances equal the sum of movements.

### Purchasing

1. **Who:** Branch managers who request stock; the owner or administrator who approves spending; clerks who receive deliveries.
2. **Problem:** Orders are placed by phone without approval; suppliers deliver short or deliver twice and get paid for the full order.
3. **Today:** Handwritten LPOs, WhatsApp messages to suppliers, delivery notes filed in a box.
4. **Improvement:** Requisitions become purchase orders with a clear approval step. Receiving records what actually arrived against each line and blocks receiving more than was ordered beyond a configured tolerance.
5. **Test:** Draft → submitted → approved → partially received → completed; double approval and over-receipt are rejected; cancelling an order with received goods is rejected.

### Sales and customer balances

1. **Who:** Sales and accounts staff who invoice customers and record payments; managers chasing overdue accounts.
2. **Problem:** Partial payments by M-Pesa, cheque or bank transfer are hard to match to invoices, so balances are disputed and overdue accounts are noticed late.
3. **Today:** A receipt book, an M-Pesa statement and a ledger card per customer.
4. **Improvement:** Invoices post stock issues and a customer ledger entry. Receipts are recorded with their reference (for example the M-Pesa transaction code) and allocated to specific invoices. An invoice is paid only when allocations cover it. Credit notes return goods to stock and reduce the balance.
5. **Test:** A KSh 100,000 invoice with a KSh 40,000 receipt shows KSh 60,000 outstanding and status "Partly paid"; ageing buckets are correct by due date; returns put stock back at the original cost.

### Reports, export and audit

1. **Who:** Owners and auditors.
2. **Problem:** Owners cannot see stock value, slow movers or overdue balances without asking someone to prepare a spreadsheet; nobody can prove who changed what.
3. **Today:** Month-end spreadsheets compiled by hand.
4. **Improvement:** Reports run directly on stored records, filterable by date and branch, exportable as CSV for people with export permission. Important actions write audit events that cannot be edited or deleted, enforced in the database.
5. **Test:** Report totals match the ledger; users without export permission get 403; the audit table rejects UPDATE and DELETE at the database level.

## Left out, and why

- **M-Pesa / payment gateway integration.** No tested provider connection exists. Receipts record the M-Pesa transaction code manually. A Daraja integration can be added later behind the same receipt model.
- **eTIMS (KRA) invoice transmission.** Not built yet, and not claimed. Because eTIMS is mandatory for all Kenyan invoices, issuing invoices without it would force double entry. Whether we integrate, stay out of invoicing, or drop the sales module is decided by the validation in [VALIDATION.md](VALIDATION.md) §3.1.
- **Supplier bills and accounts payable.** Out of scope for the first release; purchasing stops at receiving. Listed as a known limitation.
- **Celery and Redis.** No workload needs background jobs yet. CSV exports are streamed synchronously. Email in development goes to the console.
- **Charts on the dashboard.** The dashboard shows figures and lists people act on (low stock, overdue invoices, orders awaiting approval). A chart is added only where a trend matters to a decision.
