# Backend Plan — Reps Management Platform (MVP)

Tracking doc for backend build progress. Check items off as they're completed. Update the **Decisions Log** whenever an open question gets resolved instead of deleting it — keep history.

---

## 0. Architecture Notes (read first)

- **Database: PostgreSQL** (confirmed).
- **This is a SaaS product** — plans, feature gating, and resource limits (reps/products/subusers/warehouses/etc.) must be designed in from the start, not retrofitted. See §4. Every "is this allowed" check must go through a shared entitlement layer — never hardcode limits/feature checks inside individual service methods.
- **Multi-tenant + global-customer hybrid model.** `Company` is the tenant. `SubUser`, `Rep`, `Product`, `Warehouse`, `Invoice` all belong to a company. `Customer` is a global entity — registers once, can browse/order from *any* company via the Store page — so `Order`, `Cart`, and `Notification` carry a `company_id` even though the customer isn't tenant-bound.
- Every tenant-scoped query should be filtered by `company_id` automatically (middleware/base repository), not manually per-endpoint.
- Stock levels (company warehouse, rep warehouse) are **derived from an append-only `StockMovement` ledger**, never a mutable quantity column. This gives an audit trail and avoids race conditions on concurrent confirmations.
- Order flows (both Rep→Company and Customer→Company) should be modeled as explicit **state machines** (enum + transition-validation function), not free-form status strings.

---

## 1. Core Entities (ERD checklist)

Live models: `apps/{companies,billing,reps,customers,products,orders,invoices,notifications}`. Sketch (historical): `docs/schema_phase0.py`.

- [x] `Company`
- [x] `SubUser`
- [x] `Role` / `ModulePermission` (`module`, `can_view`, `can_action`)
- [x] `Rep`
- [x] `Customer`
- [x] `Product` (required `unit` → `UnitOfMeasure`)
- [x] `UnitOfMeasure` (global predefined catalog: liter, kg, package, …)
- [x] `Warehouse` (see §2 — new)
- [x] `ProductWarehouseStock` (see §2 — new, join entity)
- [x] `Order` + `OrderItem`
- [x] `StockMovement` (ledger)
- [x] `Invoice` (Incoming / Return)
- [x] `Notification`
- [x] `Plan`, `PlanLimit`, `PlanFeature`, `Subscription` (see §7 — new, SaaS layer)

---

## 2. Warehouse Entity (new — from latest discussion)

- **`Warehouse`** belongs to a `Company`. Fields: name, address/location, active flag, (optionally) type/tag if a company wants to distinguish e.g. "main" vs "cold storage" later.
- A company can have **multiple warehouses**.
- **Product ↔ Warehouse is many-to-many**, not one-to-one. When an admin adds/edits a product, they select one or more warehouses it's stored in.
  - Model this as a join table `ProductWarehouseStock { product_id, warehouse_id, quantity }` rather than a simple `product.warehouse_id` FK.
  - This join table doubles as the natural home for warehouse-level stock quantities, and should be fed by `StockMovement` entries scoped to `warehouse_id`, consistent with the ledger approach in §0.
- Rep warehouses (from the original 9.1 flow) fit the same model: a **Rep also has a warehouse** (or is assigned one), and stock movements from "Company warehouse → Rep warehouse" on order confirmation are just ledger entries between two `Warehouse` records.
  - Open sub-question: is a Rep's warehouse a `Warehouse` row owned by the company but flagged `owner_type = rep`, or a separate lightweight entity? Recommend reusing `Warehouse` with an `owner_type` (`company` / `rep`) + optional `rep_id` — avoids duplicating stock-ledger logic for two different entity types.

**Action items:**
- [x] Design `Warehouse` schema
- [x] Design `ProductWarehouseStock` join schema
- [ ] Decide Rep-warehouse modeling approach (reuse `Warehouse` vs separate entity) — leaning toward reuse, confirm before building
- [ ] Update product create/edit endpoint to accept `warehouse_ids[]` (+ optional per-warehouse initial quantity)
- [x] Update `StockMovement` to always reference a `warehouse_id`, not just a company/rep

---

## 3. Customer → Company Order Fulfillment (new — from latest discussion)

Resolves the previously-open fulfillment gap in section 9.2 of the spec.

- When a customer places an order with a company:
  - If the customer has an **assigned Rep** (via referral code link or manual admin assignment — see §5 of original doc) → that Rep is responsible for fulfilling the order.
  - If the customer has **no assigned Rep** → the order lands with the **Admin dashboard**, and the admin must assign a Rep to fulfill it before it proceeds.
- Implications for the state machine:
  - [x] Add a `fulfilling_rep_id` (nullable) field on `Order`, distinct from any "created by" field.
  - [ ] New/entry state: `pending_rep_assignment` — order sits here if no rep is linked at creation time. Only Admin (or a role with Orders `can_action`) can transition out of this state by assigning a rep.
  - [ ] Once a rep is attached (auto or manual), order proceeds through the normal fulfillment states (needs to be defined: is it identical to the Rep→Company flow's `ready_for_pickup → received_confirmed`, or does the rep deliver to the customer directly? — **this is now the one remaining open question on this flow**, see §7).
  - [ ] Notification triggers: customer's assigned rep gets "new order" notification immediately; if unassigned, Admin/delivery-role sub-users get "order needs rep assignment" notification instead.

**Action items:**
- [x] Add `assigned_rep_id` (nullable) to `Customer` if not already planned (this is the referral/assignment link from §5/§6 of the original doc — confirm it's the same field or if fulfillment assignment is separate from the referral relationship)
- [ ] Build "assign rep to order" endpoint (Admin only, requires Orders `can_action`)
- [ ] Build state machine transitions above
- [ ] Wire notifications for both branches

---

## 4. SaaS Plans, Features & Limits (new — from latest discussion)

**Principle:** business rules like "max N reps" or "excel import enabled" must live in **data (plan config)**, never hardcoded in service logic. Code asks "is this company entitled to do X" through one shared layer; it never asks "what plan are they on."

### Entities
- **`Plan`** — the catalog. `id, name, price, billing_interval, is_active`. Just metadata — no business logic attached.
- **`PlanLimit`** — generic numeric caps, one row per resource: `{ plan_id, resource_key, max_value }`. `resource_key` examples: `reps`, `products`, `subusers`, `warehouses`, `customers` (if ever needed). Generic key/value shape means adding a newly-limited resource later is a data insert, not a migration.
- **`PlanFeature`** — generic boolean/tier feature gates: `{ plan_id, feature_key, enabled }`. Examples: `excel_import`, `advanced_reports`, `multi_warehouse` (if that itself becomes a paid tier feature). Same generic shape as `PlanLimit` — one pattern for both.
- **`Subscription`** — the company's actual subscription instance, decoupled from the `Plan` catalog itself: `{ company_id, plan_id, status [trialing/active/past_due/cancelled], current_period_start, current_period_end, cancelled_at }`. Decoupling matters because plans evolve/change price over time, but a company's historical subscription record shouldn't retroactively change — reference `plan_id` as of subscription time, don't just inline plan fields onto `Company`.

### Enforcement layer
- Build a single **entitlement service**, not per-endpoint checks:
  - `canCreate(company_id, resource_key)` → counts current usage (e.g. `COUNT(reps) WHERE company_id = ...`) vs. that company's active plan's `PlanLimit`. Return allowed/denied (+ current/max for a friendly error message).
  - `hasFeature(company_id, feature_key)` → looks up `PlanFeature` for the company's active plan.
- Call these at the **top of the relevant service method** (e.g. `RepService.create()` calls `canCreate(company_id, 'reps')` before insert), not in controllers/routes — keeps it enforced regardless of entry point.
- At MVP scale, computing usage via live `COUNT()` queries is fine — no need for cached/denormalized usage counters yet. Flag as a future optimization if resource counts get large (§ note below).
- Middleware wrapper for feature-gated routes (e.g. `requireFeature('excel_import')`) so gated endpoints fail fast with a clear "upgrade your plan" response rather than partially executing.

### Design guardrails
- [ ] No plan/tier name (`'pro'`, `'enterprise'`) should ever appear in an `if` statement in business logic — always resolve through `PlanLimit`/`PlanFeature` lookups.
- [ ] `Company.subscription` (or a helper) should resolve "current active plan" in one place — reused everywhere, not re-queried differently per feature.
- [ ] Decide seed/default plan for new company signups (e.g. auto-start on a "Free"/"Trial" plan with sane default limits) so `Company` never exists without a `Subscription`.
- [ ] Downgrade/over-limit handling: if a company exceeds a resource's new lower limit after downgrading (e.g. has 20 reps, downgrades to a 10-rep plan) — block new creation but don't auto-delete existing records. (Full policy is a product decision — see §7.)

**Action items:**
- [x] Design `Plan`, `PlanLimit`, `PlanFeature`, `Subscription` schemas
- [ ] Build entitlement service (`canCreate`, `hasFeature`)
- [ ] Wire `canCreate` checks into Rep/Product/SubUser/Warehouse creation endpoints
- [ ] Wire `hasFeature` checks into gated endpoints (e.g. Excel import once it's confirmed as a gated feature)
- [ ] Seed a default/free plan + auto-subscribe new companies on signup
- [ ] Decide and document downgrade/over-limit policy (§7)

---

## 5. Build Phases (from initial roadmap — unchanged, for tracking)

### Phase 0 — Foundations
- [x] DB choice: PostgreSQL
- [x] Full ERD sketched and reviewed (incl. Warehouse §2 and SaaS §7 additions)
- [x] Migration tooling decided
- [ ] Open questions in §7 reviewed with product owner (or explicitly deferred)

### Phase 1 — Identity & Access
- [x] Admin/SubUser auth
- [x] Rep auth (no self-service profile edit, enforced server-side)
- [ ] Customer auth
- [x] JWT with `actor_type` + `company_id` claims
- [x] Tenant-scoping middleware/base repository
- [x] Role/ModulePermission matrix + authorization middleware
- [x] `Plan` / `PlanLimit` / `PlanFeature` / `Subscription` schemas (§4)
- [x] Entitlement service (`canCreate`, `hasFeature`) + feature-gate middleware (§4)
- [x] Seed default/free plan, auto-subscribe new companies on Company signup

### Phase 2 — Core Resource Management
> Reminder: creation endpoints for the limited resources below (SubUser, Rep, Product, Warehouse — see §4) must call the entitlement service's `canCreate()` before inserting. Excel import should call `hasFeature('excel_import')` if/when that's confirmed as a plan-gated feature.

- [ ] SubUser CRUD (admin-created, role-assigned) — gated by `canCreate(company_id, 'subusers')`
- [ ] Rep CRUD (credential generation, copy-to-clipboard payload, customer assignment, password reset) — gated by `canCreate(company_id, 'reps')`
- [ ] Customer CRUD — manual entry
- [ ] Customer CRUD — Excel import (async job + per-row validation/error reporting)
- [ ] First-visit GPS pin endpoint (store lat/lng on customer location)
- [ ] Product CRUD + image upload (object storage abstraction) — gated by `canCreate(company_id, 'products')`
- [ ] Warehouse CRUD (new, §2) — gated by `canCreate(company_id, 'warehouses')`
- [ ] Product↔Warehouse assignment (new, §2)

### Phase 3 — Order Engine
- [x] Rep → Company state machine — now `orders.StockTransfer` (invoicing spec §3.2), not an Order
- [x] Customer → Company — now `orders.CustomerRequest`, an informational signal, not a sale (invoicing spec §3.3)
- [x] `StockMovement` ledger (warehouse-aware, §2) — moved to `apps.products`, written only via `products.services.stock`
- [x] Derived balance calculation (company warehouse / rep warehouse)
- [x] Transaction-safe, row-locked balance-affecting transitions

### Phase 4 — Invoicing
- [x] Incoming Invoice (tied to stock receipt + tax settings)
- [x] Return Invoice — now a credit note against a required Sales Invoice (invoicing spec §3.5)
- [x] Invoice immutability (payments/returns appended, derived fields recomputed; audit trail in `common.AuditLog`)

### Phase 5 — Notifications
- [ ] Domain events defined (`OrderApproved`, `OrderAdjusted`, `NewOrderReceived`, `RepAssignmentNeeded`, etc.)
- [ ] Queue-based dispatcher (Redis/BullMQ, SQS, Celery, etc.)
- [ ] Push (FCM) integration
- [x] In-app notification records (`notifications.services`)
- [x] Role-based targeting (derived from permission model)

### Phase 6 — Hardening (ongoing, not a final step)
- [ ] Unit tests: state machine, permission middleware (highest priority)
- [ ] Integration tests: full order flow end-to-end
- [ ] OpenAPI/Swagger docs published early
- [ ] Structured logging + error tracking (Sentry or similar)
- [ ] Indexes: `company_id`, `phone`, `referral_code`, `rep_id`, order `status`, `warehouse_id`
- [ ] Pagination enforced on all list endpoints

---

## 6. Suggested Build Order

Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5, with Phase 6 running in parallel throughout.

---

## 7. Open Questions (deferred — revisit later)

From the original spec:
- [ ] Does Customer registration require trade-license image upload for verification?
- [ ] Incoming stock from "parent company": paid immediately on receipt, or another mechanism (deferred/installments)?
- [ ] Predefined Roles and their detailed permissions — needs discussion with merchants before implementation.

New, surfaced during backend planning:
- [ ] For Customer→Company orders once a rep is assigned: does the rep deliver directly to the customer, or does fulfillment mirror the Rep→Company pickup/confirm flow (`ready_for_pickup → received_confirmed`)? Needed to finish designing the Customer-order state machine in §3.
- [ ] Is "assigned rep" for fulfillment purposes (§3) the same relationship as the referral-code link (§5/§6 of original doc), or can a customer have a different rep for referral credit vs. order fulfillment?
- [ ] Rep-warehouse modeling: reuse `Warehouse` entity with `owner_type` flag, or separate entity? (see §2 — leaning toward reuse, needs confirmation)
- [ ] Full list of plan tiers and what limits/features differ per tier — not needed to build the *mechanism* (§4), but needed before launch to seed real `Plan`/`PlanLimit`/`PlanFeature` data.
- [ ] Downgrade/over-limit policy: block-only vs. grace period vs. forced deactivation of excess records (§4).
- [ ] Billing/payment provider integration (Stripe, Paddle, local provider?) — out of scope for MVP mechanism but affects `Subscription.status` transitions.

---

## Decisions Log

_Add an entry here each time an open question above gets resolved, with date and decision._

- 2026-08-13: Phase 0 schema sketch lives in `docs/schema_phase0.py` (Django models, not an installed app). §1/§2/§4 design checkboxes refer to that file. No §7 item was resolved.
- 2026-08-13: Migration tooling is Django's built-in migrations (already the repo stack).
- 2026-08-13: Every tenant-scoped table (including child rows like `OrderItem`, `InvoiceItem`, `ModulePermission`) denormalizes `company_id` so the §0 auto-filter can apply without joins.
- 2026-08-13: `ProductWarehouseStock.quantity` is a projection of `StockMovement` for `(product, warehouse)`, not a second source of truth — reconciles §0 (ledger-only) with §2 (join table holds quantity).
- 2026-08-13: `StockMovement` is one row per warehouse with a signed `quantity`. A company→rep transfer is two ledger rows, so every movement stays scoped to a single `warehouse_id` (§2).
- 2026-08-13: `PlanLimit.max_value` NULL means unlimited (avoids a magic `-1`; not specified in §4).
- 2026-08-13: `Cart` / `CartItem` are named in §0 but are not §1 entities — omitted from this schema until an order-engine task adds them.
- 2026-08-13: Identity is three credential tables (`SubUser`, `Rep`, `Customer`) matching the §1 entities, not a single Django `User`. Company is not a login actor; the company owner is a `SubUser` with `is_owner=True`. (Login identifier and owner-role rules are still FLAG'd in the sketch.)
- 2026-08-14: Material unit is a global predefined catalog (`UnitOfMeasure`), not free text and not per-company. `Product.unit` is required. Companies pick from the list; they cannot create units. Confirmed seed: liter, kg, package — full list still open. No unit-conversion table (one unit per product).
- 2026-08-14: Quantities are `Decimal(14,3)` (not integers) because liter/kg need fractions. `OrderItem` and `InvoiceItem` snapshot `unit_id` so historical lines stay stable if a product's unit is later changed.
- 2026-08-14: Domain apps (Phase-aligned): `companies` (Company/Role/ModulePermission/SubUser), `billing` (Plan/PlanLimit/PlanFeature/Subscription), `reps`, `customers`, `products` (UnitOfMeasure/Product/Warehouse/ProductWarehouseStock), `orders` (Order/OrderItem/StockMovement), `invoices` (Incoming/Return — separate from SaaS billing), `notifications`.
- 2026-08-14: `Product.image` is `FileField`, not `ImageField`, so the stack does not require Pillow until image validation exists. Object-storage swap stays a storage-backend change.
- 2026-08-14: Confirmed units (`liter`, `kg`, `package`) are seeded in `products.0002_seed_units`. Full unit catalog still open. No default SaaS plan seed yet (§7 / Phase 1 entitlement).
- 2026-08-14: `docs/schema_phase0.py` is historical; live schema is the app models + migrations. No §7 item was resolved.
- 2026-08-16: Phase 1 (Identity & Access) completed. Implemented Admin/SubUser and Rep authentication with JWT tokens containing `actor_type` and `company_id` claims. Created tenant-scoping middleware, permission system with Role/ModulePermission, and entitlement service for SaaS limits. Seeded Free plan with resource limits (reps:5, products:50, subusers:3, warehouses:2). Auto-subscribe new companies on signup. Customer auth deferred to later phase. Comprehensive test coverage added for all auth flows.
- 2026-08-29: Invoicing module built to `invoicing-module-spec.md`, which supersedes the original doc's sections 8 and 9. Notes on what changed structurally:
  - **`Order`/`OrderItem` are gone.** They are replaced by `orders.StockTransfer` (company→rep goods movement, no money, no tax) and `orders.CustomerRequest` (a wishlist signal, explicitly *not* a sale). Neither model had an API, a serializer or a writer, so no data could exist; the migration drops them.
  - **`invoices.Invoice`/`InvoiceItem` are gone**, replaced by `IncomingInvoice`, `SalesInvoice`, `ReturnInvoice`, `PaymentCollection`, `PendingCustomerCredit` and `InvoiceSettings`. Same reasoning — the old pair was an unused stub.
  - **`StockMovement` moved from `apps.orders` to `apps.products`** (same `stock_movement` table). Inventory owns the ledger because both `invoices` and `orders` write to it; this keeps `products` a leaf app that imports neither. Source documents are referenced by `(source_type, source_id)` rather than one nullable FK per document type, so a new document type is a data concern, not a migration. `products.0004` depends on `orders.0003` so the old table is dropped before the new one is created.
  - **The sale is the rep's document, not the customer's order.** A customer request creates no financial record and moves no stock; the rep issues the Sales Invoice face-to-face on delivery and may optionally link the requests it fulfils.
  - **Payment is not binary.** `paid_amount`/`returned_amount`/`balance_due`/`status` on `SalesInvoice` are derived from `PaymentCollection` and issued `ReturnInvoice` rows and recomputed on every mutation (`invoices.services.balances`). No credit limit, per the spec's explicit decision.
  - **Over-return overage is measured per return, not cumulatively.** The spec's formula `(returned + paid) - total` is the invoice-level figure; applying it verbatim to a *second* return would re-refund what the first already paid back, so each return records the increment it creates. Both resolution paths are built: `cash_refunded_by_rep` writes a negative `RepCashAdjustment` (deducted from the rep's expected cash-in), `deferred_customer_credit` writes a `PendingCustomerCredit`.
  - **`RepCashAdjustment` is new**, not in the spec's entity list. The `cash_refunded_by_rep` path requires the overage to come off the rep's next reconciliation, and there is no settlement entity; this append-only row plus collected payments is enough to state that figure (`invoices.services.reports.rep_cash_reconciliation`) without building a settlement module.
  - **Cash overpayment is refused.** The spec defines an overage only via returns, which carry a `refund_method`; a bare payment exceeding the balance has no defined resolution, so `add_payment` rejects it rather than leaving unaccounted money.
  - **Module permissions split per document type** (§6.7): `incoming_invoices`, `stock_transfers`, `customer_requests`, `sales_invoices`, `return_invoices`, `payment_collections`, `customer_credits`. `apps/common/modules.py` is now the single source for the catalog used by the owner short-circuit, `GET /api/modules`, and every view's `required_module`. The legacy `invoices`/`orders` keys still grant the granular ones *and* stay in the resolved permission payload, so existing roles and dashboards keep working with no data migration.
  - Idempotency (§6.6) is opt-in per request via an `Idempotency-Key` header on the rep app's create/receive/payment endpoints, backed by `common.IdempotencyKey`.
  - Still open, unchanged: incoming-invoice payment terms (§7 of the original doc, §8 of the invoicing spec) — `IncomingInvoice` has no payment-status fields yet.
- 2026-08-30: Added **company-direct sales**, extending the invoicing spec, which modelled the sale purely as the rep's field document ("Created by: Rep (in field, on delivery)", "− Rep warehouse"). A customer can also buy straight from the company, so:
  - `SalesInvoice.rep` and `ReturnInvoice.rep` are now **nullable**. Null means a company-direct sale — goods leave a company warehouse, and the money is company cash. Non-null keeps the spec's behaviour exactly.
  - New `POST /api/companies/sales-invoices/` (module `sales_invoices`, `can_action`). `rep` is optional: omit for a direct sale, supply one to record a sale on that rep's behalf from their van. Both go through the same `create_sales_invoice` service, so stock, credits, payments, atomicity and the audit trail are identical to the rep app.
  - A direct sale's payment is recorded with `collected_by = null`, so it is excluded from `rep_cash_reconciliation` (which already filtered `collected_by__isnull=False`). A `cash_refunded_by_rep` overage on a direct sale writes **no** `RepCashAdjustment` — the refund came from the company till, not a rep's float.
  - Returns against a direct sale inherit the null rep and default the destination to a company warehouse instead of a van.
  - Overdue report `by_rep` now has a `rep_id: null` bucket for direct-sale debt; the docs tell the client to label rather than drop it.
  - `rep_name` on the sales/return serializers needed `allow_null=True`: DRF raises `SkipField` when traversing a null FK, which would have **removed the key entirely** from the payload instead of returning null.
  - Warehouse selection/validation was consolidated into `apps/products/services/warehouses.py` (`require_warehouse`, `default_company_warehouse`, `default_rep_warehouse`). `orders.services.transfers` had privately duplicated the rep-warehouse lookup; both apps now share one copy, which also stopped this change from duplicating it a third time.
- 2026-08-30: Money is rendered as a decimal **string** everywhere in responses, via `core.responses.decimal_string`. Serializer-backed fields already were (DRF `COERCE_DECIMAL_TO_STRING`), but report aggregates and list `total_amount` extras bypass serializers and were being encoded as JSON floats — precision loss on money, and two parsing paths for the client. A test walks those responses and fails on any float.
- 2026-08-30: `docs/api/frontend.md` is now the invoicing API reference for the frontend (it previously held a Products API doc, still in git history at `3ccd19a`). Examples in it were generated from real API responses rather than written by hand.
