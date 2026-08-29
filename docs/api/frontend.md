# Invoicing API — Frontend Integration Guide

Reference for the invoicing subsystem: incoming invoices, stock transfers, customer
requests, sales invoices, returns/credit notes, payment collections, customer
credits and the admin reports.

Every example in this document is real output captured from the running API, not
hand-written. Field names, types and status codes match the implementation.

> Scope: this covers the invoicing module only. Auth, products, customers, reps
> and company setup are documented separately.

---

## 1. The domain model, in one page

Read this before wiring screens. Three distinctions drive the whole API, and
getting them wrong is the most likely source of frontend bugs.

**A stock transfer is not an invoice.** When a rep asks the company for goods, no
money changes hands — it is an internal movement of stock from the company
warehouse to the rep's van. `TRF-00001` has no totals, no prices and no tax
fields. Do not render it as an invoice.

**A customer request is not an order.** When a customer adds products in the
customer app, that is a *wishlist signal* telling their rep what they want on the
next visit. Nothing is reserved, no stock moves, no money is owed, and the
customer has not committed to anything. Copy in the UI should say so — "we've let
your rep know", not "your order is confirmed". The real sale happens face-to-face.

**The sale is the rep's document.** The rep issues `INV-SALE-00001` at the moment
of delivery. That is the only document that creates a debt and the only one that
deducts the rep's van. It may include products the customer never requested, and
it may fulfil zero, one or several requests.

**Payment is not a boolean.** A customer can pay in full, pay part, or defer
entirely. There is **no credit limit** — a rep may extend credit freely. So a
sales invoice carries a running balance, not a paid/unpaid flag:

```
balance_due = max(0, total_amount - paid_amount - returned_amount)

status = fully_paid       when balance_due == 0
         partially_paid   when balance_due > 0 and (paid + returned) > 0
         deferred         otherwise
```

`total_amount`, `paid_amount`, `returned_amount`, `balance_due` and `status` are
**computed server-side** and recalculated after every payment and every issued
return. They are read-only everywhere. Never try to PATCH a balance, and never
compute a new balance client-side and send it — post a payment and re-read.

**A return is a credit note against a specific sale.** It always references the
original sales invoice, copies the price from the original line, and cannot
exceed what was actually sold. One sale can accumulate several returns over
successive visits.

### Document types

| Document | Number | Financial | Tax fields | Created by | Warehouse effect |
|---|---|---|---|---|---|
| Incoming invoice | `INV-IN-00001` | yes | yes | Admin | **+** company warehouse, on issue |
| Stock transfer | `TRF-00001` | no | no | Rep, approved by admin | **−** company / **+** rep, on receipt |
| Customer request | *(no number)* | no | no | Customer | none |
| Sales invoice | `INV-SALE-00001` | yes | yes | Rep | **−** rep warehouse, on create |
| Return invoice | `INV-RET-00001` | yes | yes | Rep or admin | **+** rep or company, on issue |
| Payment collection | *(no number)* | yes | no | Rep or admin | none |

Each type has its own counter — they never share one sequence.

---

## 2. Base URL, authentication, actors

```
Base URL:  https://<host>/api
```

All endpoints require a JWT access token:

```http
Authorization: Bearer <access_token>
```

Tokens come from the auth endpoints (`POST /api/auth/company/signin`,
`/api/auth/rep/signin`, `/api/auth/customer/signin`). The token encodes which
actor you are, and that determines which URL prefix you may use:

| Actor | `actor_type` | Prefix | Notes |
|---|---|---|---|
| Company staff / owner | `subuser` | `/api/companies/...` | Gated by module permissions (§6) |
| Sales rep | `rep` | `/api/reps/...` | Auto-scoped to that rep's own documents |
| Customer | `customer` | `/api/customers/...` | Auto-scoped to that customer |

Using the wrong prefix for your token returns **403**, not 404 — a rep hitting
`/api/companies/...` is rejected by actor type.

> **Access tokens expire after 2 minutes.** Refresh via
> `POST /api/auth/token/refresh` (refresh tokens last 7 days). Build the refresh
> loop into your HTTP client before integrating these endpoints, otherwise you
> will see spurious 401s mid-flow.

### Trailing slashes are required

Every invoicing endpoint ends in `/`. Omitting it causes Django to issue a
redirect, and **a redirected POST loses its body**. Always include the slash.

---

## 3. Response envelope

Every response — success or failure — uses the same envelope.

**Success**

```json
{
  "success": true,
  "message": "تم إنشاء فاتورة المبيعات بنجاح",
  "data": { "invoice": { "...": "..." } }
}
```

`message` is a user-displayable Arabic string on writes, and `""` on plain reads.
`data` always contains a single named key (`invoice`, `transfer`, `request`,
`settings`, `report`, `history`, …) rather than a bare object — read
`response.data.invoice`, not `response.data`.

**Failure**

```json
{
  "success": false,
  "message": "الكمية غير متوفرة في المستودع للمنتج: Rice 1kg",
  "errors": {
    "product_id": ["1"],
    "warehouse_id": ["2"],
    "available": ["115.000"],
    "requested": ["9999.000"]
  }
}
```

`message` is safe to show the user directly. `errors` is a map of
`field → [strings]`, intended for inline field highlighting and for debugging;
its values are English and not user-facing. Nested serializer errors nest one
level (see §3.2).

### 3.1 Lists and pagination

Every list endpoint is paginated:

```json
{
  "success": true,
  "message": "",
  "data": {
    "invoices": [ { "...": "..." } ],
    "pagination": { "count": 1, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

- Page through with `?page=N`.
- **`page_size` is fixed at 50** and cannot be changed by query parameter. It is
  reported in the response so you can compute offsets, not so you can set it.
- The rows key differs per resource — see each endpoint below.

Some lists carry an extra aggregate alongside the rows (e.g. `total_amount` on
payment and credit lists). That aggregate covers the **whole filtered set**, not
just the current page.

### 3.2 Status codes

| Code | Meaning | When |
|---|---|---|
| 200 | OK | Reads, and state transitions (`issue`, `approve`, `receive`, `cancel`) |
| 201 | Created | New document created, and idempotent replays of a create |
| 400 | Bad request | Validation failure, or a business rule violation |
| 401 | Unauthenticated | Missing/expired token — refresh and retry |
| 403 | Forbidden | Wrong actor type, or missing module permission |
| 404 | Not found | Unknown id, **or an id belonging to another company/rep** |
| 409 | Conflict | Illegal state transition, or an idempotency-key conflict |

Two things to handle deliberately:

**404 hides cross-tenant access.** Querysets are scoped before lookup, so another
company's invoice — or another rep's — reads as "not found". Treat 404 as "does
not exist for you".

**409 means the document already moved on.** Issuing an already-issued invoice,
or receiving an already-received transfer, returns 409 with the current status in
`errors.status`. The correct client response is to re-fetch the document and
re-render, not to retry.

```json
{
  "success": false,
  "message": "لا يمكن ترحيل هذه الفاتورة إلا وهي مسودة",
  "errors": { "status": ["Cannot issue an invoice in status 'issued'."] }
}
```

A validation failure nests per field:

```json
{
  "success": false,
  "message": "فشل التحقق من البيانات",
  "errors": {
    "customer_id": ["This field is required."],
    "lines": { "non_field_errors": ["This list may not be empty."] }
  }
}
```

> **Known quirk:** a 404 currently carries the generic message
> `"حدث خطأ في الخادم"` ("a server error occurred"), which is inherited from the
> project-wide exception handler and predates this module. The **status code** is
> the reliable signal; don't show that message for a 404.

### 3.3 Numbers, money and dates

- **All monetary values are strings**, never JSON numbers: `"120.00"`, `"-30.00"`.
  This is deliberate — floats lose precision on money. Parse with a decimal
  library, not `parseFloat`, and never do arithmetic on these client-side to
  derive a balance the server already computed.
- **Quantities are strings with 3 decimal places**: `"10.000"`. Products are sold
  by weight and volume, so quantities are genuinely fractional.
- Counts (`invoice_count`, `payment_count`, `days_overdue`, `total_pages`) are
  plain integers.
- All timestamps are ISO-8601 UTC: `"2026-08-29T20:50:47.640895Z"`. Send
  timestamps in the same format; omit optional ones to let the server use "now".
- `returned_quantity` on a sales invoice line is `null` when nothing has been
  returned against that line. Treat `null` as `0`.

---

## 4. Idempotency (rep app — important)

Reps work in poor connectivity. A request can succeed on the server and still time
out on the handset, and a naive retry would invoice a customer twice or
double-deduct the van.

Send an `Idempotency-Key` header on every write from the rep app:

```http
POST /api/reps/sales-invoices/
Idempotency-Key: 8f2c1e90-visit-2026-08-29-001
```

- **Generate the key on the device** when the user taps the button — a UUID, or
  something stable like `<rep-id>-<visit-id>-<seq>` — and reuse the *same* key for
  every retry of that action. Generating a new key per retry defeats the purpose.
- A retry with the same key and the same body replays the original response
  verbatim, including its `201` and the original document number. Nothing is
  created twice.
- A retry with the same key but a **different body** returns **409**. That is a
  client bug (a key was reused for a new operation), not something to retry:

  ```json
  {
    "success": false,
    "message": "تم استخدام مفتاح الطلب هذا مع بيانات مختلفة",
    "errors": { "Idempotency-Key": ["Key already used with a different request body."] }
  }
  ```
- A 409 saying `"الطلب قيد المعالجة"` means an identical request is still in
  flight. Back off and retry the same key.
- If the operation failed, the key is released, so you may retry with corrected
  data under the same key.

Supported on:

| Endpoint | Scope |
|---|---|
| `POST /api/reps/sales-invoices/` | `sales_invoice.create` |
| `POST /api/reps/return-invoices/` | `return_invoice.create` |
| `POST /api/reps/return-invoices/{id}/issue/` | `return_invoice.issue` |
| `POST /api/reps/payments/` | `payment_collection.create` |
| `POST /api/reps/stock-transfers/` | `stock_transfer.create` |
| `POST /api/reps/stock-transfers/{id}/receive/` | `stock_transfer.receive` |

The header is optional; without it, two POSTs create two documents.

---

## 5. Enumerations

Send and compare these exact string values.

```
IncomingInvoice.status     draft | issued | cancelled
StockTransfer.status       pending | modified_by_admin | pending_rep_confirmation
                           | confirmed | received | cancelled
CustomerRequest.status     pending | fulfilled | cancelled
SalesInvoice.status        fully_paid | partially_paid | deferred      (computed)
ReturnInvoice.status       draft | issued
ReturnInvoice.refund_method  ""  | cash_refunded_by_rep | deferred_customer_credit
PaymentCollection.source   cash | customer_credit
PendingCustomerCredit.status  pending | applied | cancelled
```

---

## 6. Permissions (admin endpoints)

Company staff are gated per document type. The owner has everything. For staff,
each role holds `can_view` / `can_action` per module — reads need `can_view`,
writes need `can_action`.

| Module key | Covers |
|---|---|
| `incoming_invoices` | `/companies/incoming-invoices/` |
| `stock_transfers` | `/companies/stock-transfers/` |
| `customer_requests` | `/companies/customer-requests/` |
| `sales_invoices` | `/companies/sales-invoices/` **and recording a payment from an invoice** |
| `return_invoices` | `/companies/return-invoices/` |
| `payment_collections` | `/companies/payment-collections/` (the ledger list) |
| `customer_credits` | `/companies/customer-credits/` |
| `reports` | `/companies/reports/...` |
| `settings` | `/companies/invoice-settings/` |

Sales and returns are deliberately **separate** modules: a delivery-only role can
create sales invoices without being able to issue credit notes. Hide UI you know
the user cannot use — the current permission set is returned in the signin
response under `data.user.permissions`.

> Note the one crossover: `POST /companies/sales-invoices/{id}/payments/` is an
> action on the sales invoice, so it needs `sales_invoices.can_action`, while
> reading the payment ledger needs `payment_collections.can_view`.

Rep and customer endpoints are not module-gated; they are scoped by identity.

---

# Endpoint reference

---

## 7. Invoice settings — `settings`

One settings object per company, shared by every invoice type. Company name and
tax number are **snapshotted onto each document** when it is created/issued, so
editing settings never rewrites documents already given to a customer.

### `GET /api/companies/invoice-settings/`

Created on first read; never 404s.

```json
{
  "success": true,
  "message": "",
  "data": {
    "settings": {
      "company_name": "",
      "display_company_name": "Tredro Foods",
      "tax_registration_no": "",
      "address": "",
      "phone": "",
      "overdue_threshold_days": 7,
      "updated_at": "2026-08-29T20:50:47.596221Z"
    }
  }
}
```

`display_company_name` is what to print on documents: `company_name` if set,
otherwise the company's own name. Show `display_company_name`, edit `company_name`.

### `PATCH /api/companies/invoice-settings/`

```json
{
  "company_name": "Tredro Foods LLC",
  "tax_registration_no": "TAX-9915",
  "address": "Damascus, Mezzeh",
  "phone": "+963111234567",
  "overdue_threshold_days": 14
}
```

All fields optional. `overdue_threshold_days` drives the overdue report (§14).
Returns the updated `settings` object.

---

## 8. Incoming invoices — `incoming_invoices` (admin)

Stock arriving from a supplier or the parent company. **Created as a draft; stock
only lands when you issue it.**

### `GET /api/companies/incoming-invoices/`

Query: `status`, `warehouse`, `search` (invoice number), `page`.
Rows key: `invoices`. List rows omit `lines`.

```json
{
  "success": true,
  "message": "",
  "data": {
    "invoices": [
      {
        "id": 1,
        "number": "INV-IN-00001",
        "date": "2026-08-29T20:50:47.640895Z",
        "supplier_ref": "Parent company",
        "company_name": "Tredro Foods LLC",
        "tax_registration_no": "TAX-9915",
        "warehouse": 1,
        "warehouse_name": "Main store",
        "status": "draft",
        "total_amount": "1690.00",
        "notes": "August shipment",
        "issued_at": null,
        "cancelled_at": null,
        "created_at": "2026-08-29T20:50:47.641210Z",
        "updated_at": "2026-08-29T20:50:47.647888Z"
      }
    ],
    "pagination": { "count": 1, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

### `POST /api/companies/incoming-invoices/` → 201

```json
{
  "warehouse": 1,
  "supplier_ref": "Parent company",
  "notes": "August shipment",
  "date": "2026-08-29T10:00:00Z",
  "lines": [
    { "product_id": 1, "quantity": "200", "unit_price": "6.50" },
    { "product_id": 2, "quantity": "120", "unit_price": "3.25" }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `warehouse` | yes | Must be a **company** warehouse. A rep's van is rejected with 400. |
| `lines[].product_id` | yes | Must belong to your company and be active |
| `lines[].quantity` | yes | > 0 |
| `lines[].unit_price` | no | Falls back to the product's catalog price; 400 if neither exists |
| `lines[].tax_rate` | no | Defaults to the product's tax rate |
| `date`, `supplier_ref`, `notes` | no | `date` defaults to now |

Returns the full invoice **including `lines`**:

```json
"lines": [
  {
    "id": 1,
    "product": 1,
    "product_name": "Rice 1kg",
    "product_sku": "",
    "unit": 1,
    "unit_name": "Package",
    "quantity": "200.000",
    "unit_price": "6.50",
    "subtotal": "1300.00",
    "tax_rate": "0.00"
  }
]
```

`subtotal` and `total_amount` are computed — do not send them.

### `GET /api/companies/incoming-invoices/{id}/`

Full detail with `lines`.

### `POST /api/companies/incoming-invoices/{id}/issue/` → 200

Draft → issued, **incrementing the company warehouse for every line**, atomically.
Returns the updated invoice with `status: "issued"` and `issued_at` set.

- 409 if not currently `draft`.
- 400 if it has no lines.

### `POST /api/companies/incoming-invoices/{id}/cancel/` → 200

Only a **draft** can be cancelled. An issued invoice returns 409: its stock is
already in the warehouse and may have been sold on, so unwinding it is not
something the client can do. Handle this by disabling Cancel once issued.

### `GET /api/companies/incoming-invoices/{id}/history/`

Immutable audit trail, newest first. Also available on stock transfers, sales
invoices and return invoices.

```json
{
  "success": true,
  "message": "",
  "data": {
    "history": [
      {
        "id": 2,
        "actor_type": "subuser",
        "actor_id": 1,
        "entity_type": "incoming_invoice",
        "entity_id": 1,
        "entity_number": "INV-IN-00001",
        "action": "issued",
        "from_status": "draft",
        "to_status": "issued",
        "changes": { "lines": 2, "warehouse_id": 1 },
        "created_at": "2026-08-29T20:50:47.720264Z"
      }
    ]
  }
}
```

---

## 9. Stock transfers — `stock_transfers`

Company warehouse → rep's van. No money, no tax. **Stock moves only on receipt.**

```
pending ──approve────────────────────────────────► confirmed ──receive──► received
   │                                                   ▲
   └──modify──► pending_rep_confirmation ──confirm─────┘
                          │
                          └──reject──► cancelled
```

Approving does **not** move stock — it only means the quantities are agreed. The
rep tapping "received" is what physically transfers the goods.

### Rep endpoints

#### `GET /api/reps/stock-transfers/`
Query: `status`, `page`. Rows key: `transfers`. Only this rep's transfers.

#### `POST /api/reps/stock-transfers/` → 201  *(idempotent)*

```json
{
  "lines": [{ "product_id": 1, "quantity": "40" }],
  "notes": "Weekly load"
}
```

`source_warehouse` and `destination_warehouse` are optional — they default to the
company's main warehouse and the rep's own van, so the app normally omits both.

```json
{
  "success": true,
  "message": "تم إرسال طلب البضاعة",
  "data": {
    "transfer": {
      "id": 1,
      "number": "TRF-00001",
      "rep": 1,
      "rep_name": "Sami",
      "source_warehouse": 1,
      "source_warehouse_name": "Main store",
      "destination_warehouse": 2,
      "destination_warehouse_name": "Sami's van",
      "status": "pending",
      "requested_at": "2026-08-29T20:50:47.787417Z",
      "approved_at": null,
      "received_at": null,
      "cancelled_at": null,
      "notes": "Weekly load",
      "created_at": "2026-08-29T20:50:47.787885Z",
      "updated_at": "2026-08-29T20:50:47.787895Z",
      "lines": [
        {
          "id": 1,
          "product": 1,
          "product_name": "Rice 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "requested_qty": "40.000",
          "approved_qty": null,
          "effective_qty": "40.000"
        }
      ]
    }
  }
}
```

`approved_qty` is `null` until an admin acts. **Render `effective_qty`** — it is
the approved quantity when there is one, and the requested quantity otherwise.

#### `POST /api/reps/stock-transfers/{id}/confirm/` → 200
Rep accepts the admin's modified quantities → `confirmed`.

#### `POST /api/reps/stock-transfers/{id}/reject/` → 200
Rep refuses them → `cancelled`. Terminal.

#### `POST /api/reps/stock-transfers/{id}/receive/` → 200  *(idempotent)*
Physical receipt. **The only call in this flow that moves stock**: company
warehouse down, rep warehouse up, in one transaction.

- 409 if not `confirmed` (e.g. tapped before approval, or already received).
- 400 if the company warehouse no longer has the stock — the transfer stays
  `confirmed` and nothing moves.

#### `GET /api/reps/stock-transfers/{id}/`

### Admin endpoints

#### `GET /api/companies/stock-transfers/`
Query: `status`, `rep`, `search`, `page`. Rows key: `transfers`.

#### `POST /api/companies/stock-transfers/{id}/approve/` → 200
Accept the requested quantities unchanged → `confirmed`. Sets every line's
`approved_qty` to its `requested_qty`.

#### `POST /api/companies/stock-transfers/{id}/modify/` → 200

```json
{ "lines": [{ "line_id": 1, "approved_qty": "25" }] }
```

Lines you omit keep their requested quantity. Constraints:

- `approved_qty` must be ≥ 0 and **may not exceed** `requested_qty` → 400.
- If nothing actually changed → 400 telling you to use `approve` instead.

The transfer lands in `pending_rep_confirmation` (it passes through
`modified_by_admin` in the audit trail) and the rep is notified.

#### `POST /api/companies/stock-transfers/{id}/cancel/` → 200
#### `GET /api/companies/stock-transfers/{id}/` and `/history/`

---

## 10. Customer requests — `customer_requests`

A wishlist signal. **Creating one moves no stock and creates no financial
record.** It notifies the customer's assigned rep.

### Customer app

#### `POST /api/customers/requests/` → 201

```json
{
  "company_id": 1,
  "notes": "Before Friday please",
  "lines": [{ "product_id": 1, "quantity": "12" }]
}
```

`company_id` is required and names the company being browsed — customers are
global and not bound to one company. Products must belong to that company and be
sellable.

```json
{
  "success": true,
  "message": "تم إرسال طلبك إلى المندوب",
  "data": {
    "request": {
      "id": 1,
      "company": 1,
      "customer": 1,
      "customer_name": "Abu Ahmad Market",
      "customer_phone": "+963955555555",
      "rep": 1,
      "rep_name": "Sami",
      "status": "pending",
      "fulfilled_by_invoice": null,
      "fulfilled_by_invoice_number": null,
      "fulfilled_at": null,
      "cancelled_at": null,
      "notes": "Before Friday please",
      "created_at": "2026-08-29T20:50:48.025149Z",
      "updated_at": "2026-08-29T20:50:48.025159Z",
      "lines": [
        {
          "id": 1,
          "product": 1,
          "product_name": "Rice 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "desired_quantity": "12.000"
        }
      ]
    }
  }
}
```

`rep` is `null` if the customer has no rep assigned at that company — the request
is still recorded, just not routed.

> **UI copy matters here.** This is interest, not a confirmed order. Avoid
> "order placed" / "confirmed" wording; there is no price, no reservation and no
> commitment. Lines carry `desired_quantity` and deliberately have **no price**.

#### `GET /api/customers/requests/`
Query: `status`, `company`, `page`. Rows key: `requests`. Only this customer's.

#### `GET /api/customers/requests/{id}/`
#### `POST /api/customers/requests/{id}/cancel/` → 200
Only while `pending`; 400 once fulfilled or already cancelled.

### Rep

#### `GET /api/reps/customer-requests/` — query `status`, `customer`, `page`
#### `GET /api/reps/customer-requests/{id}/`

Read-only. A rep resolves a request by passing its id as `fulfils_request_ids`
when creating the sales invoice (§11) — there is no separate "fulfil" action.

### Admin

#### `GET /api/companies/customer-requests/` — query `status`, `customer`, `rep`, `page`
#### `GET /api/companies/customer-requests/{id}/`

Read-only: there is nothing for an admin to approve.

---

## 11. Sales invoices — `sales_invoices`

The real transaction. Created by the rep at delivery; deducts the van
immediately.

### `POST /api/reps/sales-invoices/` → 201  *(idempotent — use a key)*

The whole visit in one call: the sale, any credits applied, and any cash
collected on the spot. It all commits together or not at all.

```json
{
  "customer_id": 1,
  "notes": "Visit 29/08",
  "lines": [
    { "product_id": 1, "quantity": "10", "unit_price": "10.00" },
    { "product_id": 2, "quantity": "4" }
  ],
  "payment_amount": "50.00",
  "fulfils_request_ids": [1]
}
```

| Field | Required | Notes |
|---|---|---|
| `customer_id` | yes | Must be an active customer |
| `lines[].product_id` | yes | Must be active **and sellable** |
| `lines[].quantity` | yes | > 0 |
| `lines[].unit_price` | no | Omit to use the catalog price (customer-category price first, then general). 400 listing the products if neither resolves |
| `lines[].tax_rate` | no | Defaults to the product's tax rate |
| `warehouse` | no | Defaults to the rep's own van; must be that rep's warehouse |
| `date` | no | Defaults to now |
| `credit_ids` | no | Pending credits to apply (§13) |
| `payment_amount` | no | Cash collected on the spot |
| `payment_collected_at` | no | Defaults to the invoice date |
| `fulfils_request_ids` | no | Customer requests this delivery resolves |
| `notes` | no | |

Response (`data.invoice`, full detail):

```json
{
  "id": 1,
  "number": "INV-SALE-00001",
  "date": "2026-08-29T20:50:48.107984Z",
  "rep": 1,
  "rep_name": "Sami",
  "customer": 1,
  "customer_name": "Abu Ahmad Market",
  "customer_phone": "+963955555555",
  "warehouse": 2,
  "company_name": "Tredro Foods LLC",
  "tax_registration_no": "TAX-9915",
  "total_amount": "120.00",
  "paid_amount": "50.00",
  "returned_amount": "0.00",
  "balance_due": "70.00",
  "overage_amount": "0.00",
  "status": "partially_paid",
  "notes": "Visit 29/08",
  "created_at": "2026-08-29T20:50:48.108285Z",
  "updated_at": "2026-08-29T20:50:48.136110Z",
  "lines": [
    {
      "id": 1,
      "product": 1,
      "product_name": "Rice 1kg",
      "product_sku": "",
      "unit": 1,
      "unit_name": "Package",
      "quantity": "10.000",
      "unit_price": "10.00",
      "subtotal": "100.00",
      "tax_rate": "0.00",
      "returned_quantity": null
    }
  ],
  "payments": [
    {
      "id": 1,
      "sales_invoice": 1,
      "sales_invoice_number": "INV-SALE-00001",
      "amount": "50.00",
      "collected_by": 1,
      "collected_by_name": "Sami",
      "collected_at": "2026-08-29T20:50:48.107984Z",
      "source": "cash",
      "applied_credit": null,
      "note": "",
      "created_at": "2026-08-29T20:50:48.124651Z"
    }
  ],
  "returns": [],
  "fulfilled_request_ids": [1]
}
```

Notes:

- A sale with no payment is `deferred` with `balance_due == total_amount`. That is
  a **normal outcome**, not an error — there is no credit limit.
- `lines[].returned_quantity` is `null` until something is returned against that
  line; treat as 0. Use it to cap the return form.
- `payments`, `returns` and `fulfilled_request_ids` appear on detail responses
  only, not in lists.

**Errors worth handling:**

- Not enough stock in the van → **400**, and **nothing is written** — no invoice,
  no stock movement. The payload names the product and the available quantity:

  ```json
  {
    "success": false,
    "message": "الكمية غير متوفرة في المستودع للمنتج: Rice 1kg",
    "errors": {
      "product_id": ["1"], "warehouse_id": ["2"],
      "available": ["115.000"], "requested": ["9999.000"]
    }
  }
  ```
- A request already fulfilled or cancelled in `fulfils_request_ids` → 400.
- A credit already spent in `credit_ids` → 400.

### `GET /api/reps/sales-invoices/` and `GET /api/companies/sales-invoices/`

Rows key: `invoices`. The rep list is scoped to their own invoices; the admin list
covers the company.

| Query | Both | Notes |
|---|---|---|
| `status` | ✓ | `fully_paid` / `partially_paid` / `deferred` |
| `customer` | ✓ | customer id |
| `outstanding=true` | ✓ | only invoices with `balance_due > 0` |
| `date_from`, `date_to` | ✓ | on `date` |
| `search` | ✓ | invoice number |
| `rep` | admin only | rep id |
| `page` | ✓ | |

### `GET /api/reps/sales-invoices/{id}/` · `GET /api/companies/sales-invoices/{id}/`

Full detail. Admin also has `GET /api/companies/sales-invoices/{id}/history/`.

> There is no admin **create** for sales invoices, and no update or delete
> anywhere. Sales are written in the field; corrections are made by appending a
> payment or issuing a credit note, never by editing.

---

## 12. Payments — `payment_collections`

Append-only. One invoice can be collected across many visits. Every insert
recalculates the invoice's derived fields.

**Never send a "new balance".** Post what was collected and read the recomputed
invoice back.

### `POST /api/reps/payments/` → 201  *(idempotent)*

```json
{ "sales_invoice": 1, "amount": "30.00", "note": "Cash" }
```

`collected_at` is optional (defaults to now; a future date is rejected).
`collected_by` is forced to the authenticated rep.

Both the payment and the refreshed invoice come back, so you can re-render
without a second request:

```json
{
  "success": true,
  "message": "تم تسجيل الدفعة بنجاح",
  "data": {
    "payment": { "...": "..." },
    "invoice": { "balance_due": "40.00", "status": "partially_paid", "...": "..." }
  }
}
```

**Overpayment is rejected** — 400, with the current balance:

```json
{
  "success": false,
  "message": "قيمة الدفعة تتجاوز الرصيد المتبقي على الفاتورة",
  "errors": {
    "amount": ["Payment exceeds the invoice balance."],
    "balance_due": ["35.00"]
  }
}
```

Cap the input at `balance_due` in the UI. (The only path where money legitimately
exceeds the total is an over-return, which carries a refund method — §13.)

### `POST /api/companies/sales-invoices/{id}/payments/` → 201

Admin equivalent, for a customer settling at the office. The invoice comes from
the URL, so **omit `sales_invoice`** from the body. `collected_by` (a rep id) is
optional here.

```json
{ "amount": "5.00", "note": "Settled at the office", "collected_by": 1 }
```

Requires `sales_invoices.can_action`.

### `GET /api/reps/payments/` · `GET /api/companies/payment-collections/`

Rows key: `payments`, plus a `total_amount` for the whole filtered set.

Query: `sales_invoice`, `source`, `date_from`, `date_to`, `page`; admin adds `rep`.

```json
{
  "payments": [ { "...": "..." } ],
  "total_amount": "4.00",
  "pagination": { "count": 1, "page": 1, "page_size": 50, "total_pages": 1 }
}
```

Payments cannot be edited or deleted.

---

## 13. Returns and customer credits — `return_invoices`, `customer_credits`

A return is a credit note against one sales invoice. Created as a **draft**;
nothing moves until issued.

### `POST /api/reps/return-invoices/` → 201  *(idempotent)*
### `POST /api/companies/return-invoices/` → 201

```json
{
  "sales_invoice": 1,
  "notes": "Damaged packs",
  "lines": [{ "sales_invoice_line_id": 1, "quantity": "2" }]
}
```

Lines reference **`sales_invoice_line_id`, not `product_id`** — that is what
carries the original price and caps what is still returnable. Price is copied
from the original line and cannot be re-entered.

| Field | Required | Notes |
|---|---|---|
| `sales_invoice` | yes | A return is never standalone |
| `lines[].sales_invoice_line_id` | yes | Must be a line on that invoice |
| `lines[].quantity` | yes | > 0, and ≤ what remains returnable |
| `warehouse` | no | Defaults to the rep's van. Admins can route defective goods to a company warehouse instead |
| `refund_method` | no | May also be supplied at issue time |
| `date`, `notes` | no | |

Returning more than remains → 400 naming the product and the remaining quantity.

A draft response includes **`projected_overage_amount`** — what would be refunded
if issued right now. Use it to decide whether to ask for a refund method:

```json
{
  "id": 2,
  "number": "INV-RET-00002",
  "sales_invoice": 1,
  "sales_invoice_number": "INV-SALE-00001",
  "rep": 1, "rep_name": "Sami",
  "warehouse": 2, "warehouse_name": "Sami's van",
  "status": "draft",
  "amount": "30.00",
  "overage_amount": "0.00",
  "refund_method": "",
  "issued_at": null,
  "lines": [
    {
      "id": 2, "product": 1, "product_name": "Rice 1kg",
      "unit": 1, "unit_name": "Package",
      "quantity": "3.000", "unit_price": "10.00", "subtotal": "30.00",
      "tax_rate": "0.00", "sales_invoice_line": 1
    }
  ],
  "projected_overage_amount": "30.00"
}
```

### `POST /api/reps/return-invoices/{id}/issue/` → 200  *(idempotent)*
### `POST /api/companies/return-invoices/{id}/issue/` → 200

Optional body — supply the refund method here if you did not at creation:

```json
{ "refund_method": "deferred_customer_credit" }
```

Issuing restocks the goods and recalculates the parent invoice. The response
carries both documents:

```json
{
  "success": true,
  "message": "تم ترحيل فاتورة الإرجاع",
  "data": {
    "return_invoice": { "status": "issued", "overage_amount": "30.00", "...": "..." },
    "invoice": {
      "total_amount": "120.00",
      "paid_amount": "100.00",
      "returned_amount": "50.00",
      "balance_due": "0.00",
      "overage_amount": "30.00",
      "status": "fully_paid",
      "...": "..."
    }
  }
}
```

### The overage rule — build both paths

When payments plus returns exceed the invoice total, the customer is owed money.
`balance_due` **floors at zero and never goes negative**; the excess becomes an
overage that must be resolved.

If `projected_overage_amount > 0`, the client **must** collect a `refund_method`
before issuing. Without one the API refuses:

```json
{
  "success": false,
  "message": "يجب تحديد طريقة رد المبلغ الزائد قبل ترحيل الإرجاع",
  "errors": {
    "refund_method": ["Required when the return creates an overage."],
    "overage_amount": ["30.00"]
  }
}
```

Two options, both required in the UI:

| `refund_method` | Meaning | Effect |
|---|---|---|
| `cash_refunded_by_rep` | Rep handed cash back on the spot | Deducted from that rep's expected cash-in (§14). No new document. |
| `deferred_customer_credit` | Nothing changed hands; the customer is owed credit | Creates a pending credit against a future purchase |

Either way the sale closes at `balance_due: "0.00"`. Each return records only the
overage **it** created, so stacked returns never double-refund.

### `GET /api/reps/return-invoices/` · `GET /api/companies/return-invoices/`

Rows key: `return_invoices`. Query: `status`, `sales_invoice`, `page`; admin adds
`rep` and `search`.

### Customer credits

Credits are a **tracked list applied manually**, never an auto-applying balance.
Do not silently deduct one — ask.

#### `GET /api/reps/customer-credits/?customer={id}&status=pending`

Call this when starting a new invoice for a customer, and prompt: *"this customer
has a pending credit of X — apply it?"* Rows key: `credits`, plus `total_amount`.

```json
{
  "credits": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "Abu Ahmad Market",
      "source_return_invoice": 2,
      "source_return_invoice_number": "INV-RET-00002",
      "amount": "30.00",
      "status": "pending",
      "applied_to_invoice": null,
      "applied_at": null,
      "created_at": "2026-08-29T20:50:48.583362Z",
      "updated_at": "2026-08-29T20:50:48.583370Z"
    }
  ],
  "total_amount": "30.00",
  "pagination": { "count": 1, "page": 1, "page_size": 50, "total_pages": 1 }
}
```

Apply by passing `credit_ids: [1]` when creating the sales invoice. Several may
be applied at once, as long as their sum does not exceed the new invoice's total
(400 otherwise). Each applied credit is recorded as a payment with
`source: "customer_credit"`, so it appears in `paid_amount` and stays traceable —
it is **not** a discount on the line prices.

#### `GET /api/companies/customer-credits/` — query `status`, `customer`, `page`
#### `POST /api/companies/customer-credits/{id}/cancel/` → 200
Write off a credit. Only while `pending`.

---

## 14. Reports — `reports` (admin)

### `GET /api/companies/reports/overdue-debts/`

Computed on read — not a cached table and not a push alert. An invoice is overdue
when it still owes money (`deferred` or `partially_paid`) **and** is older than
the threshold.

Query: `threshold_days` (defaults to Invoice Settings), `rep`, `customer`.

```json
{
  "success": true,
  "message": "",
  "data": {
    "report": {
      "overdue_threshold_days": 7,
      "generated_at": "2026-08-29T20:53:08.345669Z",
      "totals": { "invoice_count": 1, "total_balance_due": "16.00" },
      "by_rep": [
        { "rep_id": 1, "rep_name": "Sami", "invoice_count": 1, "total_balance_due": "16.00" }
      ],
      "by_customer": [
        {
          "customer_id": 1,
          "customer_name": "Abu Ahmad Market",
          "invoice_count": 1,
          "total_balance_due": "16.00",
          "invoices": [
            {
              "id": 1,
              "number": "INV-SALE-00001",
              "date": "2026-08-29T20:53:08.250334Z",
              "balance_due": "16.00",
              "status": "partially_paid",
              "days_overdue": 0
            }
          ]
        }
      ]
    }
  }
}
```

Both groupings come from the same filtered set — `by_rep` totals and `by_customer`
totals both sum to `totals.total_balance_due`. Only `by_customer` carries the
individual invoice rows. Intended to hang off the existing rep-activity
monitoring screen rather than a new module.

### `GET /api/companies/reports/rep-cash/`

What each rep is expected to hand in: cash collected, minus cash they refunded to
customers on the spot.

Query: `rep`, `date_from`, `date_to`.

```json
{
  "report": {
    "generated_at": "2026-08-29T20:55:20.525994Z",
    "date_from": null,
    "date_to": null,
    "totals": {
      "cash_collected": "100.00",
      "adjustments": "0.00",
      "expected_cash_in": "100.00"
    },
    "by_rep": [
      {
        "rep_id": 1,
        "rep_name": "Sami",
        "cash_collected": "100.00",
        "payment_count": 4,
        "adjustments": "0.00",
        "expected_cash_in": "100.00"
      }
    ]
  }
}
```

`adjustments` is negative when a rep refunded cash via `cash_refunded_by_rep`;
`expected_cash_in = cash_collected + adjustments`. Credits applied are **excluded**
— no money changed hands for those.

---

## 15. Client flows

### Rep: a customer visit

```
1. GET  /api/reps/customer-requests/?customer={id}&status=pending
        → what they asked for. Prefill, don't restrict: anything can be sold.

2. GET  /api/reps/customer-credits/?customer={id}&status=pending
        → if any, prompt "apply credit of X?"

3. GET  /api/reps/sales-invoices/?customer={id}&outstanding=true
        → old debt to collect on this visit

4. POST /api/reps/sales-invoices/          [Idempotency-Key]
        lines + credit_ids? + payment_amount? + fulfils_request_ids?
        → the sale, stock deduction, credits and cash in one commit

5. POST /api/reps/payments/                [Idempotency-Key]
        → collections against older invoices from step 3

6. Returns, if the customer is sending goods back:
   POST /api/reps/return-invoices/         [Idempotency-Key]
        → read projected_overage_amount
   if > 0: ask the rep to choose a refund method
   POST /api/reps/return-invoices/{id}/issue/   [Idempotency-Key]
```

### Rep: restocking the van

```
POST /api/reps/stock-transfers/          [Idempotency-Key]   → pending
   ... admin approves (→ confirmed) or modifies (→ pending_rep_confirmation)
POST /api/reps/stock-transfers/{id}/confirm/   (only if modified)  → confirmed
POST /api/reps/stock-transfers/{id}/receive/   [Idempotency-Key]   → received
                                                        ↑ stock actually moves here
```

Poll `GET /api/reps/stock-transfers/?status=confirmed` (or react to the
notification) to know when it is collectable.

### Admin: receiving supplier stock

```
POST /api/companies/incoming-invoices/            → draft (nothing in the warehouse yet)
     ... review
POST /api/companies/incoming-invoices/{id}/issue/ → issued, stock lands
```

### Customer app

```
POST /api/customers/requests/     { company_id, lines }
GET  /api/customers/requests/     → track status: pending → fulfilled
POST /api/customers/requests/{id}/cancel/
```

The request becomes `fulfilled` when the rep delivers and links it;
`fulfilled_by_invoice_number` then names the invoice.

---

## 16. Integration checklist

- [ ] Token refresh on 401 (access tokens live **2 minutes**)
- [ ] Trailing slash on every URL
- [ ] Read `response.data.<key>`, not `response.data`
- [ ] Parse money as decimal strings; never `parseFloat`, never recompute balances
- [ ] `Idempotency-Key` on all six rep write endpoints, stable across retries
- [ ] 409 → re-fetch and re-render, don't retry
- [ ] 404 → "not found for you" (may be another tenant's record)
- [ ] `?page=N` on lists; page size is fixed at 50
- [ ] Treat `returned_quantity: null` as 0
- [ ] Render `effective_qty` on transfer lines, not `requested_qty`
- [ ] Force a refund-method choice whenever `projected_overage_amount > 0`
- [ ] Surface pending credits before a sale; never auto-apply
- [ ] Customer-request copy says "signal", not "confirmed order"
- [ ] Hide admin actions the user's module permissions don't allow
