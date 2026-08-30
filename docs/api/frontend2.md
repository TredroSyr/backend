# Warehouses, Stock Movement & Company-Direct Invoicing

Companion to [frontend.md](frontend.md). That document covers the invoicing
module as the spec originally modelled it. This one covers three things it does
not:

1. **Company-direct sales** — an admin creating a sales invoice from the
   dashboard, either for a walk-in customer buying from the company itself, or on
   a rep's behalf.
2. **`currency` on every financial document** — the denomination is now pinned
   onto the document instead of being read off the company at display time.
3. **Warehouses and the stock pipeline** — what a warehouse is, and the complete
   path goods travel from the supplier's truck to the customer's hands, which is
   how a rep ends up with something to sell.

Every JSON body below is real output captured from the API, not hand-written.

> Conventions — base URL, JWT auth, the `{success, message, data}` envelope,
> pagination, idempotency, error shapes and permission modules — are unchanged.
> See frontend.md §2–§6. The only things repeated here are the ones that changed.

---

## 0. What changed

| Change | Impact on the client |
|---|---|
| `POST /api/companies/sales-invoices/` now exists | The admin dashboard can create sales invoices. It was read-only before. |
| `SalesInvoice.rep` and `ReturnInvoice.rep` are **nullable** | `rep` and `rep_name` can be `null` on any sales or return invoice. Every screen that renders a rep must handle it. |
| `currency` added to incoming, sales and return invoices | Render money with the document's own currency, not the company's. |
| Payments from a direct sale carry `collected_by: null` | They are company cash and never appear in a rep's settlement. |
| Overdue report `by_rep` gained a `rep_id: null` bucket | Label it ("Company direct"), do not drop it — its balance is part of `totals`. |
| Warehouse selection and validation consolidated server-side | Error payloads for a bad warehouse are now identical across sales, returns, incoming invoices and transfers. |

Nothing was removed and no field changed type. A client built against
frontend.md keeps working; the two `null`s are the only new shapes it can meet.

---

# Part A — Currency on documents

## 1. What it is

Money columns previously carried no denomination. A client rendered them using
`Company.currency`, read at display time — so changing that field silently
re-denominated documents that had already been priced and issued.

Every financial document now snapshots the code it was priced in:

```json
"total_amount": "4390.00",
"currency": "SYP"
```

`currency` is an **ISO 4217 code** (3 characters), read-only, and present on:

| Document | Endpoint family |
|---|---|
| Incoming invoice | `/api/companies/incoming-invoices/` |
| Sales invoice | `/api/companies/sales-invoices/`, `/api/reps/sales-invoices/` |
| Return invoice | `/api/companies/return-invoices/`, `/api/reps/return-invoices/` |

It appears on both the list and the detail serializer of each, so a list screen
never has to fetch a document to know how to format its total.

Stock transfers and customer requests do **not** have it — they carry no money.
Payment collections do not either; a payment is denominated by the invoice it
belongs to.

## 2. The rules

**Pinned once, at creation.** The code is copied from `Company.currency` when the
document row is created, alongside the existing `company_name` and
`tax_registration_no` header snapshot.

**Not refreshed on issue.** The other two snapshot fields are re-read when a
draft is issued — they are only header text. `currency` is not, because the lines
were already priced under it.

**Returns inherit from the sale, not from the company.** A credit note copies
`currency` from the sales invoice it credits. Its `amount` is subtracted from
that invoice's total, so the two must agree even if the company switched currency
in between.

**Existing rows were backfilled** with the currency their company trades in
today — exactly what the client inferred for them before the column existed. No
displayed value changed; it was only pinned.

## 3. What the client should do

- Format each document with **its own** `currency`. Do not reach for the company
  setting any more.
- Never sum totals across documents without checking they share a currency. In
  practice a company trades in one, but that is no longer an assumption the data
  guarantees.
- Report aggregates (`/reports/overdue-debts/`, `/reports/rep-cash/`) sum across
  documents and therefore carry **no** currency field. Label them with the
  company's current currency.
- Treat the field as read-only. There is no request field for it, and sending one
  is ignored.

---

# Part B — Warehouses

## 4. The model

A warehouse is a place stock sits. There are exactly two kinds, and the
difference drives every stock rule in the system.

| `owner_type` | `rep` | What it is |
|---|---|---|
| `company` | always `null` | A company store or depot. Where supplier deliveries land, and where a direct sale ships from. |
| `rep` | always set | One rep's van. Where their transfers arrive, and the only place their field sales can deduct from. |

That pairing is enforced by a database constraint, not only by the serializer: a
company warehouse with a rep, or a rep warehouse without one, cannot exist.

A rep may have more than one warehouse row, but the flows below always pick their
**oldest active** one as the default.

### Warehouse object

```json
{
  "id": 2,
  "name": "Sami's van",
  "address": "",
  "kind": "",
  "owner_type": "rep",
  "rep": 1,
  "rep_name": "Sami",
  "is_active": true,
  "created_at": "2026-08-30T09:17:24.160427Z",
  "updated_at": "2026-08-30T09:17:24.160460Z"
}
```

`kind` is a free-text label for your own grouping (`"depot"`, `"cold store"`, …).
It has no behaviour attached.

## 5. Which warehouse gets used when you omit one

Every document that moves stock names a warehouse, but clients rarely need to
send one — the server picks the only sensible default. This is the whole table:

| Document | Field | Default when omitted | Must be |
|---|---|---|---|
| Incoming invoice | `warehouse` | *(none — required)* | `owner_type=company` |
| Stock transfer | `source_warehouse` | company's oldest active company warehouse | `owner_type=company` |
| Stock transfer | `destination_warehouse` | the rep's oldest active van | `owner_type=rep`, belonging to that rep |
| Sales invoice (rep) | `warehouse` | that rep's oldest active van | `owner_type=rep`, belonging to that rep |
| Sales invoice (direct) | `warehouse` | company's oldest active company warehouse | `owner_type=company` |
| Return invoice | `warehouse` | the van of the sale's rep — or a company warehouse when the sale had no rep | any active warehouse of the company |

Send an explicit id only when the company has more than one warehouse of the
right kind and the goods really moved through a specific one.

## 6. Endpoints

All warehouse endpoints are tenant-scoped: you only ever see your own company's
rows. Unlike the invoicing endpoints they are **not** behind a permission module
— any authenticated actor of the company, a rep token included, can read and
write them. Treat the write endpoints as an admin-dashboard screen by convention;
the server does not enforce that today.

### `GET /api/companies/warehouses/`

Query params: `is_active` (`true`/`false`), `owner_type` (`company`/`rep`).
Ordered by name. **Not paginated** — the response is the complete list.

```json
{
  "success": true,
  "message": "",
  "data": {
    "warehouses": [
      {
        "id": 1,
        "name": "Main store",
        "address": "",
        "kind": "",
        "owner_type": "company",
        "rep": null,
        "rep_name": null,
        "is_active": true,
        "created_at": "2026-08-30T09:17:24.159072Z",
        "updated_at": "2026-08-30T09:17:24.159080Z"
      },
      {
        "id": 2,
        "name": "Sami's van",
        "address": "",
        "kind": "",
        "owner_type": "rep",
        "rep": 1,
        "rep_name": "Sami",
        "is_active": true,
        "created_at": "2026-08-30T09:17:24.160427Z",
        "updated_at": "2026-08-30T09:17:24.160460Z"
      }
    ]
  }
}
```

Note `rep_name` is `null`, not absent, on a company warehouse — the key is always
present.

### `POST /api/companies/warehouses/` → 201

```json
{
  "name": "North depot",
  "owner_type": "company",
  "address": "Aleppo road",
  "kind": "depot"
}
```

```json
{
  "success": true,
  "message": "تم إنشاء المستودع بنجاح",
  "data": {
    "warehouse": {
      "id": 3,
      "name": "North depot",
      "address": "Aleppo road",
      "kind": "depot",
      "owner_type": "company",
      "rep": null,
      "rep_name": null,
      "is_active": true,
      "created_at": "2026-08-30T09:17:24.771213Z",
      "updated_at": "2026-08-30T09:17:24.771224Z"
    }
  }
}
```

For a rep's van send `"owner_type": "rep"` and `"rep": <rep_id>`. Omitting the
rep is a 400:

```json
{
  "success": false,
  "message": "بيانات غير صالحة",
  "errors": { "rep": ["مستودع المندوب يجب أن يرتبط بمندوب"] }
}
```

The mirror case — `owner_type: "company"` with a `rep` — fails the same way with
`"مستودع الشركة لا يجب أن يرتبط بمندوب"`. A rep id from another company, or an
inactive rep, is rejected with `"المندوب غير موجود أو لا ينتمي لهذه الشركة"`.

### `GET /api/companies/warehouses/{id}/` → 200

Returns `data.warehouse`, the same object shape.

### `PATCH /api/companies/warehouses/{id}/` → 200

Partial update. `id`, `created_at` and `updated_at` are read-only; everything
else is writable, and the `owner_type`/`rep` consistency check runs again.

### `DELETE /api/companies/warehouses/{id}/` → 200

**Soft delete** — sets `is_active = false`. Returns 200 with a message, not 204,
and no `data`. The row survives because documents point at it. An inactive
warehouse is refused by every document service (`"المستودع غير نشط"`) and stops
being a default candidate.

### `GET /api/companies/warehouses/{id}/product-stock/`

What is currently in this warehouse, per product. Read-only, not paginated.

```json
{
  "success": true,
  "message": "",
  "data": {
    "stock": [
      {
        "id": 1,
        "warehouse": 1,
        "warehouse_name": "Main store",
        "product": 1,
        "product_name": "Rice 1kg",
        "product_sku": "",
        "quantity": "500.000",
        "created_at": "2026-08-30T09:17:24.825801Z",
        "updated_at": "2026-08-30T09:17:24.825813Z"
      },
      {
        "id": 2,
        "warehouse": 1,
        "warehouse_name": "Main store",
        "product": 2,
        "product_name": "Sugar 1kg",
        "product_sku": "",
        "quantity": "200.000",
        "created_at": "2026-08-30T09:17:24.825829Z",
        "updated_at": "2026-08-30T09:17:24.825833Z"
      }
    ]
  }
}
```

`quantity` is a decimal **string** with 3 decimal places, in the product's unit of
measure. A product with no row has never moved through that warehouse; treat a
missing row as `0`, not as an error.

### `GET /api/companies/products/{id}/warehouse-stock/`

The same rows sliced the other way: one product across every warehouse. Identical
object shape, same `data.stock` key. Use this for a product screen's "where is
it?" panel, and the warehouse-nested one for a van-contents screen.

## 7. Warehouse errors, everywhere

These come from the document services (sales, returns, incoming, transfers), not
from the warehouse endpoints, and read identically whichever document raised
them. All are **400**.

| `message` | `errors` value | Cause |
|---|---|---|
| `المستودع لا ينتمي لهذه الشركة` | `["Wrong company."]` | Warehouse id belongs to another tenant |
| `المستودع غير نشط` | `["Inactive warehouse."]` | Soft-deleted warehouse |
| `المستودع المحدد يجب أن يكون مستودع الشركة` | `["Expected owner_type=company."]` | A company-warehouse slot was given a van |
| `المستودع المحدد يجب أن يكون مستودع المندوب` | `["Expected owner_type=rep."]` | A van slot was given a company warehouse |
| `المستودع لا يخص هذا المندوب` | `["Warehouse belongs to another rep."]` | Another rep's van |
| `لا يوجد مستودع نشط للشركة` | `["The company has no active warehouse."]` | No default company warehouse to fall back to |
| `لا يوجد مستودع مرتبط بهذا المندوب` | `["The rep has no active warehouse."]` | The rep has no van to fall back to |

The `errors` **key** names the request field that was wrong, so you can highlight
the right input: `warehouse` on invoices, `source_warehouse` /
`destination_warehouse` on a stock transfer.

---

# Part C — Stock movement: how the rep gets goods to sell

## 8. The pipeline

Goods travel through exactly three hops, and each hop is a different document
written by a different actor:

```
   SUPPLIER
      │
      │  ①  Incoming invoice   INV-IN-00001      admin creates, admin issues
      ▼
┌──────────────────────┐
│  COMPANY WAREHOUSE   │   "Main store"   owner_type = company
└──────────────────────┘
      │
      │  ②  Stock transfer     TRF-00001         rep requests, admin approves,
      │                                          rep receives  ← stock moves here
      ▼
┌──────────────────────┐
│  REP WAREHOUSE (van) │   "Sami's van"   owner_type = rep, rep = Sami
└──────────────────────┘
      │
      │  ③  Sales invoice      INV-SALE-00001    rep issues on delivery
      ▼
   CUSTOMER
```

Two shortcuts exist around hop ③, both covered in Part D: an admin can write the
sales invoice on the rep's behalf (still leaving the van), or write a
**company-direct sale** that skips the van entirely and ships straight from the
company warehouse.

The key thing to internalise: **a stock transfer is not an invoice.** No money
changes hands, there are no prices, no tax fields and no totals on it. It is an
internal movement. Do not render it as an invoice.

## 9. The stock ledger

Behind all three hops is one append-only ledger. You do not write to it directly
— every document service does, atomically with its own row.

- **One ledger row per warehouse per product per movement.** A company → rep
  transfer is therefore *two* rows: a negative one on the source and a positive
  one on the destination.
- **`product-stock` is a projection**, not a second source of truth. It is the
  fast read of the ledger's running sum.
- **Stock can never go negative.** An outbound move that would overdraw a
  warehouse is rejected before anything is written.
- **Everything is atomic.** The stock rows and the financial record commit
  together, or neither does. A failed sale leaves no invoice *and* no deduction.

Movement types you will see referenced (`movement_type` in the ledger):

| Value | Written by |
|---|---|
| `initial` | Opening stock / seed |
| `incoming` | Incoming invoice, on issue |
| `transfer_out` | Stock transfer, on receipt — company side |
| `transfer_in` | Stock transfer, on receipt — rep side |
| `sale_out` | Sales invoice, on create |
| `return_in` | Return invoice, on issue |
| `adjustment` | Manual correction |

There is no public endpoint for the raw ledger today. `product-stock` (§6) is the
client-visible view of it.

### Insufficient stock

Any outbound movement that would overdraw returns **400** with the numbers, so
you can show the actor exactly what is on hand instead of a bare failure:

```json
{
  "success": false,
  "message": "الكمية غير متوفرة في المستودع للمنتج: Rice 1kg",
  "errors": {
    "product_id": ["1"],
    "warehouse_id": ["1"],
    "available": ["384.000"],
    "requested": ["99999.000"]
  }
}
```

## 10. Hop ① — goods enter the company warehouse

`POST /api/companies/incoming-invoices/` — admin only, module
`incoming_invoices` + `can_action`.

This is the document that records a supplier or parent-company delivery. It is
the *only* way stock legitimately appears in a company warehouse.

**Creating leaves it a draft. Nothing moves until it is issued.** That split is
deliberate: the paperwork can be entered before the pallets are counted.

### Request

```json
{
  "warehouse": 1,
  "supplier_ref": "PO-2231",
  "notes": "Delivery from Al-Sham Mills",
  "lines": [
    { "product_id": 1, "quantity": "500", "unit_price": "7.50" },
    { "product_id": 2, "quantity": "200", "unit_price": "3.20", "tax_rate": "5" }
  ]
}
```

`warehouse` is **required** here — an incoming invoice has no default, because
"which door did the truck arrive at" is not something the server can guess. It
must be a company warehouse: pointing an incoming invoice at a rep's van is
rejected with `"المستودع المحدد يجب أن يكون مستودع الشركة"`. `unit_price` may be
omitted to let the catalog price resolve; `date` defaults to now; `tax_rate`
falls back to the product's.

### Response → 201

```json
{
  "success": true,
  "message": "تم إنشاء فاتورة الوارد كمسودة",
  "data": {
    "invoice": {
      "id": 1,
      "number": "INV-IN-00001",
      "date": "2026-08-30T09:17:24.801927Z",
      "supplier_ref": "PO-2231",
      "company_name": "Tredro Foods",
      "tax_registration_no": "",
      "currency": "SYP",
      "warehouse": 1,
      "warehouse_name": "Main store",
      "status": "draft",
      "total_amount": "4390.00",
      "notes": "Delivery from Al-Sham Mills",
      "issued_at": null,
      "cancelled_at": null,
      "created_at": "2026-08-30T09:17:24.803227Z",
      "updated_at": "2026-08-30T09:17:24.806708Z",
      "lines": [
        {
          "id": 1,
          "product": 1,
          "product_name": "Rice 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "quantity": "500.000",
          "unit_price": "7.50",
          "subtotal": "3750.00",
          "tax_rate": "0.00"
        },
        {
          "id": 2,
          "product": 2,
          "product_name": "Sugar 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "quantity": "200.000",
          "unit_price": "3.20",
          "subtotal": "640.00",
          "tax_rate": "5.00"
        }
      ]
    }
  }
}
```

`currency: "SYP"` is the Part A snapshot, pinned at this moment.

`subtotal` is `quantity × unit_price` and `total_amount` is the sum of subtotals
— **tax is recorded per line but not added into the total**. If your UI shows a
tax-inclusive figure, compute it client-side from `tax_rate`.

### `POST /api/companies/incoming-invoices/{id}/issue/` → 200

The step that actually increments the warehouse, atomically with the status
change. Response is the same detail object with `status: "issued"` and
`issued_at` set. Immediately afterwards, `product-stock` on that warehouse shows
`500.000` Rice and `200.000` Sugar (the §6 example above is this exact state).

### `POST /api/companies/incoming-invoices/{id}/cancel/` → 200

Only a draft can be cancelled. An issued invoice has already moved stock and is
terminal — correct it with an adjustment, not a cancel.

Also available: `GET /api/companies/incoming-invoices/` (filters `status`,
`warehouse`, `search`), `GET {id}/`, and `GET {id}/history/`.

## 11. Hop ② — stock transfer, company warehouse → rep's van

This is the answer to *"how does the rep get goods to start selling?"*

### The state machine

```
  rep POST /api/reps/stock-transfers/
        │
        ▼
    ┌─────────┐   admin approve      ┌───────────┐   rep receive   ┌──────────┐
    │ pending │─────────────────────▶│ confirmed │────────────────▶│ received │
    └─────────┘                      └───────────┘                 └──────────┘
        │                                  ▲                    ▲ STOCK MOVES
        │ admin modify                     │ rep confirm        │ HERE, AND
        ▼                                  │                    │ ONLY HERE
 ┌───────────────────┐            ┌──────────────────────────┐
 │ modified_by_admin │───────────▶│ pending_rep_confirmation │
 └───────────────────┘  (automatic)└──────────────────────────┘
        │                                  │ rep reject
        └──────────────┬───────────────────┘
                       ▼
                 ┌───────────┐
                 │ cancelled │   terminal
                 └───────────┘
```

Two things clients get wrong here:

- **`modified_by_admin` is transient.** One `modify` call performs both hops, so
  the response you get back already says `pending_rep_confirmation`. The
  intermediate state exists only in the audit history.
- **Confirming is not receiving.** Confirming means the rep agreed to the
  quantities; the goods have not left the building. Stock moves on `receive` and
  nowhere else.

### Who may do what

| Action | Endpoint | Actor | From status |
|---|---|---|---|
| Request goods | `POST /api/reps/stock-transfers/` | rep | — |
| Approve as requested | `POST /api/companies/stock-transfers/{id}/approve/` | admin | `pending` |
| Cut quantities | `POST /api/companies/stock-transfers/{id}/modify/` | admin | `pending` |
| Cancel | `POST /api/companies/stock-transfers/{id}/cancel/` | admin | `pending`, `modified_by_admin`, `pending_rep_confirmation`, `confirmed` |
| Accept cut quantities | `POST /api/reps/stock-transfers/{id}/confirm/` | rep | `pending_rep_confirmation` |
| Refuse cut quantities | `POST /api/reps/stock-transfers/{id}/reject/` | rep | `pending_rep_confirmation` |
| Confirm physical receipt | `POST /api/reps/stock-transfers/{id}/receive/` | rep | `confirmed` |

Admin endpoints need module `stock_transfers` (`can_view` to read, `can_action`
to act). Rep endpoints are auto-scoped: a rep only ever sees their own transfers.

An illegal hop returns **409 Conflict**:

```json
{
  "success": false,
  "message": "لا يمكن تنفيذ هذا الإجراء على الطلب في حالته الحالية",
  "errors": { "status": ["Cannot move from 'pending' to 'received'."] }
}
```

### Step 1 — the rep asks for goods

`POST /api/reps/stock-transfers/` → 201. **Send an `Idempotency-Key` header.**

```json
{
  "lines": [
    { "product_id": 1, "quantity": "120" },
    { "product_id": 2, "quantity": "60" }
  ],
  "notes": "Tuesday route"
}
```

Lines are product and quantity only — no prices, because nothing is being sold.
Both warehouses may be omitted; they default to the company's main warehouse and
the rep's own van (§5).

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
      "requested_at": "2026-08-30T09:17:24.870022Z",
      "approved_at": null,
      "received_at": null,
      "cancelled_at": null,
      "notes": "Tuesday route",
      "created_at": "2026-08-30T09:17:24.870328Z",
      "updated_at": "2026-08-30T09:17:24.870337Z",
      "lines": [
        {
          "id": 1,
          "product": 1,
          "product_name": "Rice 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "requested_qty": "120.000",
          "approved_qty": null,
          "effective_qty": "120.000"
        },
        {
          "id": 2,
          "product": 2,
          "product_name": "Sugar 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "requested_qty": "60.000",
          "approved_qty": null,
          "effective_qty": "60.000"
        }
      ]
    }
  }
}
```

Three quantities per line, and the distinction matters:

| Field | Meaning |
|---|---|
| `requested_qty` | What the rep asked for. Never changes. |
| `approved_qty` | What the admin allowed. `null` until an admin acts. |
| `effective_qty` | What will actually move: `approved_qty` if set, otherwise `requested_qty`. **Render this one.** |

Stock is **not** reserved at this point. A pending transfer holds nothing; the
goods are still fully available to everyone else.

Admins see the request in `GET /api/companies/stock-transfers/` (paginated;
filters `status`, `rep`, `search`) and are notified via
`stock_transfer.requested`.

### Step 2a — admin approves as requested

`POST /api/companies/stock-transfers/{id}/approve/` → 200. No body. Every line's
`approved_qty` is set equal to its `requested_qty`, and the transfer goes
straight to `confirmed`.

```json
{
  "success": true,
  "message": "تمت الموافقة على الطلب",
  "data": {
    "transfer": {
      "id": 2,
      "number": "TRF-00002",
      "rep": 1,
      "rep_name": "Sami",
      "source_warehouse": 1,
      "source_warehouse_name": "Main store",
      "destination_warehouse": 2,
      "destination_warehouse_name": "Sami's van",
      "status": "confirmed",
      "requested_at": "2026-08-30T09:17:24.983613Z",
      "approved_at": "2026-08-30T09:17:24.999075Z",
      "received_at": null,
      "cancelled_at": null,
      "notes": "",
      "created_at": "2026-08-30T09:17:24.983831Z",
      "updated_at": "2026-08-30T09:17:24.999197Z",
      "lines": [
        {
          "id": 3,
          "product": 2,
          "product_name": "Sugar 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "requested_qty": "10.000",
          "approved_qty": "10.000",
          "effective_qty": "10.000"
        }
      ]
    }
  }
}
```

### Step 2b — admin cuts the quantities

`POST /api/companies/stock-transfers/{id}/modify/` → 200.

```json
{
  "lines": [
    { "line_id": 1, "approved_qty": "100" }
  ]
}
```

- Identify lines by **`line_id`** (the transfer line's `id`), not by product id.
- Lines you do not list keep their requested quantity — you only send what you
  are cutting.
- `approved_qty` may be `0` (that line ships nothing) but must not exceed
  `requested_qty`: `"الكمية المعتمدة لا يمكن أن تتجاوز الكمية المطلوبة"`.
- If nothing actually differs, the call is refused with
  `"لم يتم تعديل أي كمية — استخدم الموافقة المباشرة بدلاً من ذلك"` — use
  `approve` instead.

The response comes back already in `pending_rep_confirmation`, with line 1 cut
from 120 to 100 and line 2 filled in at its requested 60:

```json
{
  "success": true,
  "message": "تم تعديل الكميات بانتظار موافقة المندوب",
  "data": {
    "transfer": {
      "id": 1,
      "number": "TRF-00001",
      "status": "pending_rep_confirmation",
      "approved_at": "2026-08-30T09:17:24.905014Z",
      "received_at": null,
      "lines": [
        {
          "id": 1,
          "product_name": "Rice 1kg",
          "requested_qty": "120.000",
          "approved_qty": "100.000",
          "effective_qty": "100.000"
        },
        {
          "id": 2,
          "product_name": "Sugar 1kg",
          "requested_qty": "60.000",
          "approved_qty": "60.000",
          "effective_qty": "60.000"
        }
      ]
    }
  }
}
```

*(trimmed to the fields that changed — the full object is as in step 1)*

The rep is notified via `stock_transfer.modified`.

### Step 3 — the rep accepts or refuses

`POST /api/reps/stock-transfers/{id}/confirm/` → 200, status becomes
`confirmed`, message `"تم تأكيد الكميات"`.

`POST /api/reps/stock-transfers/{id}/reject/` → 200, status becomes `cancelled`,
message `"تم رفض الطلب"`. Terminal — the rep raises a new request if they still
need goods.

Still no stock has moved.

### Step 4 — the rep confirms physical receipt

`POST /api/reps/stock-transfers/{id}/receive/` → 200. **This is the only call in
the entire flow that moves stock.** Send an `Idempotency-Key`: a rep tapping
"received" twice on a bad connection must not transfer the goods twice.

```json
{
  "success": true,
  "message": "تم تأكيد الاستلام وتحديث المستودعات",
  "data": {
    "transfer": {
      "id": 1,
      "number": "TRF-00001",
      "status": "received",
      "requested_at": "2026-08-30T09:17:24.870022Z",
      "approved_at": "2026-08-30T09:17:24.905014Z",
      "received_at": "2026-08-30T09:17:24.950955Z",
      "cancelled_at": null
    }
  }
}
```

In one transaction this writes: `-100` and `-60` on Main store, `+100` and `+60`
on Sami's van, and the status change. The van now holds sellable stock:

```json
{
  "success": true,
  "message": "",
  "data": {
    "stock": [
      {
        "id": 5,
        "warehouse": 2,
        "warehouse_name": "Sami's van",
        "product": 1,
        "product_name": "Rice 1kg",
        "quantity": "100.000",
        "created_at": "2026-08-30T09:17:24.945768Z",
        "updated_at": "2026-08-30T09:17:24.945777Z"
      },
      {
        "id": 6,
        "warehouse": 2,
        "warehouse_name": "Sami's van",
        "product": 2,
        "product_name": "Sugar 1kg",
        "quantity": "60.000",
        "created_at": "2026-08-30T09:17:24.945792Z",
        "updated_at": "2026-08-30T09:17:24.945796Z"
      }
    ]
  }
}
```

Note it moved `effective_qty` (100), not `requested_qty` (120).

Failure modes at this step:

- The company warehouse was drained by someone else in the meantime → 400
  insufficient stock (§9), nothing moves, the transfer stays `confirmed` and can
  be received again once restocked.
- Every approved quantity is `0` → 400,
  `"لا توجد كميات معتمدة لاستلامها"`.

### Audit trail

`GET /api/companies/stock-transfers/{id}/history/` returns the immutable trail,
newest first. Every transition is there, including the transient
`modified_by_admin` hop:

```json
{
  "success": true,
  "message": "",
  "data": {
    "history": [
      {
        "id": 7,
        "actor_type": "rep",
        "actor_id": 1,
        "entity_type": "stock_transfer",
        "entity_id": 1,
        "entity_number": "TRF-00001",
        "action": "received",
        "from_status": "confirmed",
        "to_status": "received",
        "changes": {
          "lines": 2,
          "source_warehouse_id": 1,
          "destination_warehouse_id": 2
        },
        "created_at": "2026-08-30T09:17:24.951985Z"
      },
      {
        "id": 6,
        "actor_type": "rep",
        "actor_id": 1,
        "action": "rep_confirmed",
        "from_status": "pending_rep_confirmation",
        "to_status": "confirmed",
        "changes": {},
        "created_at": "2026-08-30T09:17:24.920884Z"
      },
      {
        "id": 5,
        "actor_type": "subuser",
        "actor_id": 1,
        "action": "awaiting_rep_confirmation",
        "from_status": "modified_by_admin",
        "to_status": "pending_rep_confirmation",
        "changes": {},
        "created_at": "2026-08-30T09:17:24.907922Z"
      },
      {
        "id": 4,
        "actor_type": "subuser",
        "actor_id": 1,
        "action": "modified",
        "from_status": "pending",
        "to_status": "modified_by_admin",
        "changes": {
          "modified_lines": [
            { "line_id": 1, "approved": "100", "requested": "120.000" }
          ]
        },
        "created_at": "2026-08-30T09:17:24.906397Z"
      },
      {
        "id": 3,
        "actor_type": "rep",
        "actor_id": 1,
        "action": "requested",
        "from_status": "",
        "to_status": "pending",
        "changes": { "lines": 2 },
        "created_at": "2026-08-30T09:17:24.878962Z"
      }
    ]
  }
}
```

*(the repeated `entity_*` fields are trimmed from the later entries)*

### Notifications

| Event key | Sent to |
|---|---|
| `stock_transfer.requested` | company admins with the `stock_transfers` module |
| `stock_transfer.modified` | the rep |
| `stock_transfer.confirmed` | the rep (admin approved) or admins (rep confirmed) |
| `stock_transfer.received` | company admins |
| `stock_transfer.cancelled` | both sides |

## 12. Hop ③ — the rep sells from the van

`POST /api/reps/sales-invoices/` — documented in full in frontend.md §11. What
matters for stock: the sale deducts the **rep's warehouse at creation time**
(there is no draft/issue split for a sale), and its `warehouse` defaults to that
rep's van.

If the van is short, the sale is refused with the §9 insufficient-stock error and
no invoice is created.

## 13. Reverse flows

Goods can travel back up the pipeline:

| Situation | Document | Stock effect |
|---|---|---|
| Customer returns goods to the rep | Return invoice, created by rep | `+` the rep's van, on issue |
| Admin pulls defective goods out of circulation | Return invoice with an explicit `warehouse` | `+` whichever warehouse was named |
| Return against a company-direct sale | Return invoice, `rep: null` | `+` a company warehouse (§16) |
| Draft incoming invoice was wrong | Cancel it | none — a draft never moved stock |

A return only moves stock when it is **issued**, never at creation. There is no
"transfer back from van to company warehouse" document today; use a return, or a
manual adjustment.

## 14. Client flows

**Rep restocking the van**

1. `GET /api/companies/warehouses/{my_van_id}/product-stock/` — see what is
   running low.
2. `POST /api/reps/stock-transfers/` with an `Idempotency-Key` → `pending`.
3. Poll or await the notification. If it comes back
   `pending_rep_confirmation`, show requested vs approved per line and offer
   confirm / reject.
4. On arrival at the warehouse: `POST {id}/receive/` with an `Idempotency-Key`.
5. Re-read `product-stock` — the van now holds the goods.

**Admin fulfilling requests**

1. `GET /api/companies/stock-transfers/?status=pending`.
2. Check availability against
   `GET /api/companies/warehouses/{source_id}/product-stock/`.
3. `approve` if you can ship it all, otherwise `modify` with the lines you are
   cutting.
4. Wait for the rep's `receive` — that is when your warehouse actually drops.

**Admin receiving supplier stock**

1. `POST /api/companies/incoming-invoices/` → `draft`.
2. Count the delivery against the draft.
3. `POST {id}/issue/` → the warehouse increments.

---

# Part D — Admin-created sales invoices

## 15. Two shapes of sale

`POST /api/companies/sales-invoices/` is new. The endpoint used to be read-only
because the spec modelled the sale purely as the rep's field document. It now
covers two cases, distinguished **only** by whether you send `rep`:

| | Field sale | Company-direct sale |
|---|---|---|
| `rep` in the request | supplied | **omitted** |
| Written from | rep app, or admin on their behalf | admin dashboard |
| Goods leave | that rep's van | a company warehouse |
| `rep` / `rep_name` on the invoice | the rep | `null` |
| Payment's `collected_by` | the rep | `null` |
| Counts in rep cash settlement | yes | no — company cash |
| Visible on `/api/reps/sales-invoices/` | yes | no |

A direct sale is a walk-in: a customer buying from the company itself, collecting
from the warehouse, with no rep involved.

Both paths call the **same service** as the rep app, so numbering, stock
deduction, credit application, payment recording, atomicity and the audit trail
are identical. Only the warehouse and the rep attribution differ. In particular
both share one `INV-SALE-` sequence — there is no separate counter per channel.

Permission: module `sales_invoices` with `can_action`.

## 16. `POST /api/companies/sales-invoices/` → 201

### Request

Identical to the rep's body (frontend.md §11) plus one optional field:

| Field | Required | Notes |
|---|---|---|
| `customer_id` | yes | Must be an active customer |
| `lines[]` | yes | `product_id`, `quantity`, optional `unit_price`, `tax_rate`. Sellable products only. |
| `rep` | **no** | **New.** Omit for a direct sale; supply a rep id to record the sale on their behalf. Must belong to your company. |
| `warehouse` | no | Defaults per §5. Must match the sale's shape. |
| `date` | no | Defaults to now |
| `notes` | no | |
| `credit_ids[]` | no | Pending customer credits to apply |
| `payment_amount` | no | Cash settled on the spot |
| `payment_collected_at` | no | |
| `fulfils_request_ids[]` | no | Customer requests this delivery satisfies |

Omitting `unit_price` resolves the catalog price (customer-category price first,
then the general one). If a product has no resolvable price the whole call is a
400 listing the offending ids.

### A direct sale

```json
{
  "customer_id": 1,
  "lines": [
    { "product_id": 1, "quantity": "20", "unit_price": "10.00" }
  ],
  "payment_amount": "150.00",
  "notes": "Walk-in, collected from Main store"
}
```

```json
{
  "success": true,
  "message": "تم إنشاء فاتورة المبيعات بنجاح",
  "data": {
    "invoice": {
      "id": 1,
      "number": "INV-SALE-00001",
      "date": "2026-08-30T09:17:25.019427Z",
      "rep": null,
      "rep_name": null,
      "customer": 1,
      "customer_name": "Abu Ahmad Market",
      "customer_phone": "+963955555555",
      "warehouse": 1,
      "company_name": "Tredro Foods",
      "tax_registration_no": "",
      "currency": "SYP",
      "total_amount": "200.00",
      "paid_amount": "150.00",
      "returned_amount": "0.00",
      "balance_due": "50.00",
      "overage_amount": "0.00",
      "status": "partially_paid",
      "notes": "Walk-in, collected from Main store",
      "created_at": "2026-08-30T09:17:25.019743Z",
      "updated_at": "2026-08-30T09:17:25.036444Z",
      "lines": [
        {
          "id": 1,
          "product": 1,
          "product_name": "Rice 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "quantity": "20.000",
          "unit_price": "10.00",
          "subtotal": "200.00",
          "tax_rate": "0.00"
        }
      ],
      "payments": [
        {
          "id": 1,
          "sales_invoice": 1,
          "sales_invoice_number": "INV-SALE-00001",
          "amount": "150.00",
          "collected_by": null,
          "collected_by_name": null,
          "collected_at": "2026-08-30T09:17:25.019427Z",
          "source": "cash",
          "applied_credit": null,
          "note": "",
          "created_at": "2026-08-30T09:17:25.029422Z"
        }
      ],
      "returns": [],
      "fulfilled_request_ids": []
    }
  }
}
```

Three things to read off that response: `rep` and `rep_name` are `null`, the
payment's `collected_by` is `null`, and `warehouse: 1` is the company store — the
goods left Main store, not anyone's van.

The balance rules are unchanged: `balance_due = max(0, total − paid − returned)`,
and `status` derives from it. Paying nothing is fine — the invoice is simply
`deferred`. There is no credit limit.

### A sale on a rep's behalf

Add `rep`:

```json
{
  "customer_id": 1,
  "rep": 1,
  "lines": [ { "product_id": 2, "quantity": "5" } ]
}
```

```json
{
  "success": true,
  "message": "تم إنشاء فاتورة المبيعات بنجاح",
  "data": {
    "invoice": {
      "id": 2,
      "number": "INV-SALE-00002",
      "date": "2026-08-30T09:17:25.066332Z",
      "rep": 1,
      "rep_name": "Sami",
      "customer": 1,
      "customer_name": "Abu Ahmad Market",
      "customer_phone": "+963955555555",
      "warehouse": 2,
      "company_name": "Tredro Foods",
      "tax_registration_no": "",
      "currency": "SYP",
      "total_amount": "25.00",
      "paid_amount": "0.00",
      "returned_amount": "0.00",
      "balance_due": "25.00",
      "overage_amount": "0.00",
      "status": "deferred",
      "notes": "",
      "created_at": "2026-08-30T09:17:25.066554Z",
      "updated_at": "2026-08-30T09:17:25.074317Z",
      "lines": [
        {
          "id": 2,
          "product": 2,
          "product_name": "Sugar 1kg",
          "product_sku": "",
          "unit": 1,
          "unit_name": "Package",
          "quantity": "5.000",
          "unit_price": "5.00",
          "subtotal": "25.00",
          "tax_rate": "0.00"
        }
      ],
      "payments": [],
      "returns": [],
      "fulfilled_request_ids": []
    }
  }
}
```

`warehouse: 2` — the rep's van, deducted exactly as if they had posted it
themselves. `unit_price` was omitted and resolved to the catalog price (5.00).

This is deliberately indistinguishable from a field sale afterwards. If you need
to tell "the rep posted it" from "the office posted it for them" apart, read
`GET /api/companies/sales-invoices/{id}/history/`, where the audit entry records
which actor wrote it.

### Idempotency

The rep endpoint honours `Idempotency-Key`; **this admin endpoint does not**. It
is a desk-bound flow with a visible response, so a retry creates a second
invoice. Disable the submit button, and on a network timeout re-read the list
before retrying.

## 17. What a `null` rep changes downstream

### Lists

`GET /api/companies/sales-invoices/` mixes both kinds. `rep` and `rep_name` stay
present as `null` — DRF would otherwise drop the key entirely, so the object
shape is stable and you can render a fixed column:

```json
{
  "success": true,
  "message": "",
  "data": {
    "invoices": [
      {
        "id": 2,
        "number": "INV-SALE-00002",
        "rep": 1,
        "rep_name": "Sami",
        "warehouse": 2,
        "currency": "SYP",
        "total_amount": "25.00",
        "balance_due": "25.00",
        "status": "deferred"
      },
      {
        "id": 1,
        "number": "INV-SALE-00001",
        "rep": null,
        "rep_name": null,
        "warehouse": 1,
        "currency": "SYP",
        "total_amount": "200.00",
        "balance_due": "50.00",
        "status": "partially_paid"
      }
    ],
    "pagination": { "count": 2, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

*(trimmed to the columns a list screen uses)*

Filtering by `?rep=<id>` returns only that rep's invoices; there is no filter for
"direct sales only" today — filter client-side on `rep === null`.

### Rep endpoints exclude them

`GET /api/reps/sales-invoices/` filters on the authenticated rep's id, so a
direct sale never appears there. With the two invoices above, the rep sees only
`INV-SALE-00002`. This is correct: a direct sale is not their document, not their
stock and not their cash.

### Rep cash reconciliation

A direct sale's payment has `collected_by: null` and is excluded from
`GET /api/companies/reports/rep-cash/` entirely. That report answers "how much
should each rep hand in", and company-till money is not part of any rep's float.

### Overdue debt report

`GET /api/companies/reports/overdue-debts/` groups by rep, and direct-sale debt
lands in a bucket with `rep_id: null`:

```json
{
  "success": true,
  "message": "",
  "data": {
    "report": {
      "overdue_threshold_days": 0,
      "generated_at": "2026-08-30 09:17:25.173445+00:00",
      "totals": { "invoice_count": 2, "total_balance_due": "35.00" },
      "by_rep": [
        {
          "rep_id": 1,
          "rep_name": "Sami",
          "invoice_count": 1,
          "total_balance_due": "25.00"
        },
        {
          "rep_id": null,
          "rep_name": null,
          "invoice_count": 1,
          "total_balance_due": "10.00"
        }
      ],
      "by_customer": [
        {
          "customer_id": 1,
          "customer_name": "Abu Ahmad Market",
          "invoice_count": 2,
          "total_balance_due": "35.00",
          "invoices": [
            {
              "id": 1,
              "number": "INV-SALE-00001",
              "date": "2026-08-30 09:17:25.019427+00:00",
              "balance_due": "10.00",
              "status": "partially_paid",
              "days_overdue": 0
            },
            {
              "id": 2,
              "number": "INV-SALE-00002",
              "date": "2026-08-30 09:17:25.066332+00:00",
              "balance_due": "25.00",
              "status": "deferred",
              "days_overdue": 0
            }
          ]
        }
      ]
    }
  }
}
```

**Label that bucket, do not drop it.** Its balance is included in `totals`, so a
client that skips null rows shows per-rep figures that do not add up to the
total. "Company direct" / "مبيعات مباشرة" is the right label.

`by_customer` is unaffected — a customer is a customer either way.

## 18. Returns against a direct sale

Create them at `POST /api/companies/return-invoices/` exactly as usual; the only
difference is what the server infers:

- `rep` is inherited from the sale, so it is `null`.
- `warehouse` therefore defaults to a **company warehouse** instead of a van. An
  admin can still override it to pull defective goods somewhere specific.
- `currency` is inherited from the sale (Part A).
- `refund_method: "cash_refunded_by_rep"` on a direct sale writes **no** rep cash
  adjustment — the refund came out of the company till, not a rep's float. The
  sale is still closed out correctly at `balance_due: 0`.

```json
{
  "success": true,
  "message": "تم ترحيل فاتورة الإرجاع",
  "data": {
    "return_invoice": {
      "id": 1,
      "number": "INV-RET-00001",
      "sales_invoice": 1,
      "sales_invoice_number": "INV-SALE-00001",
      "rep": null,
      "rep_name": null,
      "warehouse": 1,
      "warehouse_name": "Main store",
      "currency": "SYP",
      "status": "issued",
      "amount": "40.00",
      "overage_amount": "0.00",
      "refund_method": "cash_refunded_by_rep",
      "issued_at": "2026-08-30T09:17:25.154894Z"
    },
    "invoice": {
      "id": 1,
      "number": "INV-SALE-00001",
      "rep": null,
      "rep_name": null,
      "currency": "SYP",
      "total_amount": "200.00",
      "paid_amount": "150.00",
      "returned_amount": "40.00",
      "balance_due": "10.00",
      "status": "partially_paid"
    }
  }
}
```

*(trimmed — the full objects carry the usual header and line fields)*

The overage rule and the two refund methods behave as documented in
frontend.md §13; only the rep-float adjustment is skipped.

## 19. Errors

| Situation | Status | Response |
|---|---|---|
| Company warehouse is short | 400 | Insufficient-stock payload (§9) — no invoice created |
| `warehouse` points at a rep's van on a direct sale | 400 | `"المستودع المحدد يجب أن يكون مستودع الشركة"`, `errors.warehouse: ["Expected owner_type=company."]` |
| `warehouse` points at another rep's van on a rep sale | 400 | `"المستودع لا يخص هذا المندوب"` |
| `rep` id belongs to another company | 400 | DRF `errors.rep` — the field is company-scoped, so a foreign id does not resolve |
| Company has no active company warehouse | 400 | `"لا يوجد مستودع نشط للشركة"` |
| No lines | 400 | `"لا يمكن إنشاء فاتورة بدون بنود"` |
| Product has no resolvable price | 400 | `errors.lines` lists the product ids |
| Caller lacks `sales_invoices` / `can_action` | 403 | Standard permission error |
| Rep token hitting this endpoint | 403 | Wrong prefix for the actor — reps use `/api/reps/...` |

Every failure is atomic: no invoice, no stock movement, no payment.

## 20. Client checklist

- [ ] Render `rep_name` with a fallback everywhere — invoice lists, details,
      returns, report rows. `null` means "company direct", not "missing data".
- [ ] Label the `rep_id: null` bucket in the overdue report instead of filtering
      it out.
- [ ] Format money with the document's `currency`, not the company's.
- [ ] Do not add tax onto `total_amount`; it is the sum of subtotals.
- [ ] Warehouse pickers: filter by `owner_type` to match the slot, and hide
      `is_active: false` rows.
- [ ] Omit `warehouse` unless the company genuinely has several of the right
      kind — the defaults are correct.
- [ ] Stock-transfer screens: render `effective_qty`, show
      `requested_qty` vs `approved_qty` when they differ, and never treat
      `confirmed` as "the rep has the goods".
- [ ] `modify` takes `line_id`, not `product_id`.
- [ ] Send `Idempotency-Key` on the rep's transfer create and receive. The admin
      sales-invoice create has no idempotency — guard the button instead.
- [ ] Treat a missing `product-stock` row as `0`.
- [ ] Handle 409 on stock-transfer actions by re-reading the transfer; someone
      else moved it on.
