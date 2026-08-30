# Getting Goods Into a Rep's Van, and Selling Them

Fourth companion to [frontend.md](frontend.md), [frontend2.md](frontend2.md) and
[frontend3.md](frontend3.md). Those describe the invoicing module document by
document. This one is a **flow document**: it follows one journey end to end —
goods leave the company warehouse, land in a rep's van, and are sold to a
customer.

That journey has **two origins**. Either the rep asks for the goods, or the
office sends them unasked. They are the same document, the same ledger and the
same receipt; only the opening move differs, and they converge before anything
physically moves.

Everything here except the dispatch endpoint in §6d already existed. The rest is
the existing surface arranged in the order a client actually calls it, with the
rules that only become visible when you look at the whole sequence.

> Conventions — base URL, JWT auth, the `{success, message, data}` envelope,
> pagination, idempotency and error shapes — are unchanged. See frontend.md §2–§6.

---

## 0. The flow at a glance

```
  ┌─ admin creates the rep ───────────────────────────────────┐
  │  POST /api/companies/reps/  →  van warehouse auto-created │
  └───────────────────────────────────────────────────────────┘
                              │
     ORIGIN A: the rep asks   │   ORIGIN B: the office sends
     ┌────────────────────────┴────────────────────────┐
     ▼                                                 ▼
  POST /api/reps/stock-transfers/      POST /api/companies/stock-transfers/
              status: pending                    status: confirmed
                     │                                 │
        ┌────────────┴─────────────┐                   │
        │                          │                   │
  admin approves as-is    admin cuts quantities        │
  POST /companies/…/approve/   POST /companies/…/modify/
        │                          │                   │
        │                 modified_by_admin            │
        │                          ▼                   │
        │               pending_rep_confirmation       │
        │                  │                │          │
        │         rep confirms        rep rejects      │
        │    POST /reps/…/confirm/  POST /reps/…/reject/
        │                  │                │          │
        └────────┬─────────┘           cancelled       │
                 │                                     │
                 └──────────────┬──────────────────────┘
                                ▼
                            confirmed    ← agreed, nothing has moved
                                │
                                ▼
        rep collects the goods and taps "received"
        POST /api/reps/stock-transfers/{id}/receive/   status: received
                                │
                                ▼   ◄─── THE ONLY STOCK MOVEMENT IN THIS FLOW
             company warehouse −qty, rep van +qty
                                │
                                ▼
        rep visits the customer and sells
        POST /api/reps/sales-invoices/                 van −qty, cash in
```

**The one rule that governs everything below: stock moves on `received`, and
nowhere else.** Approving does not move stock. Confirming does not move stock.
**Neither does dispatching** — the office cannot put goods in a van by decree,
because a van's contents are what the rep is accountable for. A transfer sitting
at `confirmed` for a week has not changed a single quantity in any warehouse. If
your UI implies otherwise, it is lying to the rep.

### Every endpoint in this flow

| # | Actor | Call | Effect |
|---|---|---|---|
| 1 | Admin | `POST /api/companies/reps/` | Creates the rep **and their van** |
| 2 | Rep | `POST /api/auth/rep/signin` | Token carrying `rep_id` + `company_id` |
| 3 | Rep | `GET /api/companies/products/` | Browse what can be requested |
| 4 | Rep | `POST /api/reps/stock-transfers/` | **Origin A** — raise a request → `pending` |
| 4′ | Admin | `POST /api/companies/stock-transfers/` | **Origin B** — dispatch → `confirmed` |
| 5 | Admin | `GET /api/companies/stock-transfers/?status=pending` | The review queue |
| 6a | Admin | `POST /api/companies/stock-transfers/{id}/approve/` | → `confirmed` |
| 6b | Admin | `POST /api/companies/stock-transfers/{id}/modify/` | → `pending_rep_confirmation` |
| 6c | Admin | `POST /api/companies/stock-transfers/{id}/cancel/` | → `cancelled` |
| 7a | Rep | `POST /api/reps/stock-transfers/{id}/confirm/` | → `confirmed` |
| 7b | Rep | `POST /api/reps/stock-transfers/{id}/reject/` | → `cancelled` |
| 8 | Rep | `POST /api/reps/stock-transfers/{id}/receive/` | → `received`, **stock moves** |
| 9 | Rep | `GET /api/companies/warehouses/{van_id}/product-stock/` | What is in the van |
| 10 | Rep | `POST /api/reps/sales-invoices/` | The sale, deducts from the van |

Steps 5–7 exist only for Origin A. A dispatch skips straight from 4′ to 8.

---

# Part A — Before anything can move

## 1. The rep needs a van

A rep's stock lives in a `Warehouse` row with `owner_type: "rep"` and `rep` set
to their id. Informally: their van.

Since the change described in frontend3.md Part C, `POST /api/companies/reps/`
creates this warehouse automatically in the same transaction. **For any rep
created through the current API there is nothing to do here.** The van is what
makes the rest of this document possible: the transfer's destination, the sale's
source, and the return's destination all default to it.

Reps created before that change have no van and never got one backfilled. They
fail at step 4 and again at step 10 with:

```json
{
  "success": false,
  "message": "لا يوجد مستودع مرتبط بهذا المندوب",
  "errors": { "warehouse": ["The rep has no active warehouse."] }
}
```

Recovery is `POST /api/companies/warehouses/` with `owner_type: "rep"` and their
`rep` id. Same error, same fix, if an admin **deactivated** the van — the system
deliberately will not mint a replacement, because deactivation was a decision.

## 2. Rep signin

```
POST /api/auth/rep/signin
```

Note: no trailing slash. The auth routes are hand-written paths; everything else
in this document comes from a DRF router and **does** take a trailing slash.

```json
{ "phone": "+963933333333", "password": "…" }
```

```json
{
  "success": true,
  "message": "تم تسجيل الدخول بنجاح",
  "data": {
    "rep": {
      "id": 1,
      "name": "Kamal",
      "phone": "+963933333333",
      "referral_code": "REP-KAMAL",
      "is_active": true,
      "company": { "id": 1, "name": "Tredro Foods" }
    },
    "tokens": { "access": "…", "refresh": "…" }
  }
}
```

The access token carries `actor_type: "rep"`, `rep_id` and `company_id`. Every
`/api/reps/...` endpoint reads `rep_id` from the token, never from the URL or the
body — **a rep can only ever act as themselves, and no parameter changes that.**

Signin fails with 401 on bad credentials, and **403** if either the rep or the
company has been deactivated. Those are different messages and deserve different
UI: a 403 is not a typo the user can fix by retyping their password.

## 3. Browsing the catalog

There is no rep-specific product endpoint. Reps call the company one:

```
GET /api/companies/products/?is_active=true&search=زيت
```

This works because the products viewset requires only authentication and scopes
its queryset to the token's `company_id` — the rep's token carries one. The same
holds for `/api/companies/product-categories/`, `/api/companies/warehouses/` and
the stock endpoints in §9.

Filters: `category`, `is_active`, `is_sellable`, `is_purchasable`, `brand`,
`search` (name / SKU / barcode), `ordering` (`name`, `sku`, `created_at`, each
with an optional `-` prefix; anything else is ignored and you get `-created_at`).

**This list is not paginated.** It returns `data.products` as a plain array with
no `pagination` object — unlike every list in Part B. Do not write a shared list
component that assumes `data.pagination` exists.

### `is_sellable` matters more than it looks

A product flagged `is_sellable: false` can still be **requested and received into
stock** — the stock transfer does not filter on it. It can never be **sold**: the
sales invoice rejects it. Packaging, samples and raw inputs behave this way.

So the correct filter depends on which screen you are building:

| Screen | Filter |
|---|---|
| "Request goods from the company" | `?is_active=true` |
| "Add a line to a sales invoice" | `?is_active=true&is_sellable=true` |

Filtering the request screen by `is_sellable` hides goods the rep is legitimately
allowed to carry. Not filtering the sales screen produces a 400 at submit time,
after the rep has typed the whole invoice.

---

# Part B — The stock transfer

## 4. The state machine

Six states and **two entry points**. The server rejects any hop not in this table,
whichever endpoint asks:

| From | Allowed next | Who triggers it |
|---|---|---|
| *(new — rep request)* | `pending` | Rep |
| *(new — office dispatch)* | `confirmed` | Admin |
| `pending` | `confirmed`, `modified_by_admin`, `cancelled` | Admin |
| `modified_by_admin` | `pending_rep_confirmation`, `cancelled` | *Automatic* |
| `pending_rep_confirmation` | `confirmed`, `cancelled` | Rep |
| `confirmed` | `received`, `cancelled` | Rep receives; either side cancels |
| `received` | — terminal | — |
| `cancelled` | — terminal | — |

A dispatch enters at `confirmed` because there is nobody left to approve: the
office asked and answered in one act. **Past that point the two origins are
indistinguishable** — the same `receive`, the same cancel rules, the same
document shape. Only the audit trail records which one it was.

`modified_by_admin` is a **pass-through state you will almost never see.** One
`modify` call writes both hops in a single transaction, so the transfer is
already at `pending_rep_confirmation` by the time the response reaches you. Still
handle the value — it appears in the audit history (§11), and in a list snapshot
taken mid-write.

An illegal transition returns **409**, not 400:

```json
{
  "success": false,
  "message": "لا يمكن تنفيذ هذا الإجراء على الطلب في حالته الحالية",
  "errors": { "status": ["Cannot move from 'pending' to 'received'."] }
}
```

Treat 409 as "your screen is stale" — refetch the transfer and re-render, rather
than showing a raw error. The realistic cause is two people acting at once: the
rep taps *receive* while the admin is cancelling.

### Which state means what to a rep

| Status | What the rep should be told |
|---|---|
| `pending` | Sent. Waiting on the office. |
| `pending_rep_confirmation` | **The office changed your quantities. Act.** |
| `confirmed` | Ready to collect from the warehouse. |
| `received` | In your van. Sellable. |
| `cancelled` | Dead. Raise a new one. |

Two states are blocked on the rep and cannot be unblocked by anyone else, so
those are the two that deserve a badge: `pending_rep_confirmation`, and
`confirmed` — which now includes goods the office sent unprompted and is waiting
for the rep to collect. A dispatched transfer appears in the rep's list already
at `confirmed` and never passes through `pending`, so a screen that only watches
`pending_rep_confirmation` will show the rep nothing at all.

## 5. Raising a request — the rep

```
POST /api/reps/stock-transfers/
Idempotency-Key: <uuid>
```

```json
{
  "lines": [
    { "product_id": 1, "quantity": "10" },
    { "product_id": 2, "quantity": "5.5" }
  ],
  "notes": "تحضير جولة الأحد"
}
```

| Field | Required | Notes |
|---|---|---|
| `lines[].product_id` | ✅ | Must belong to the company and be `is_active` |
| `lines[].quantity` | ✅ | Decimal, 3 dp, **minimum `0.001`** — zero is rejected |
| `source_warehouse` | — | Defaults to the company's oldest active warehouse |
| `destination_warehouse` | — | Defaults to the rep's oldest active van |
| `notes` | — | Free text |

**Send neither warehouse.** The defaults are the entire point: the field client
should not know warehouse ids, and hardcoding one breaks the day the company adds
a second depot. If you do send them, `source_warehouse` must be
`owner_type: "company"` and `destination_warehouse` must be a van belonging to
*this* rep — both are validated, and the error names which field was wrong.

Response is **201** with the full detail object (§7). `status` is `pending` and
every line's `approved_qty` is `null`.

Every admin who can act on the `stock_transfers` module gets a
`stock_transfer.requested` notification.

### Errors

| Condition | Status | `message` |
|---|---|---|
| `lines: []` | 400 | `لا يمكن إرسال طلب فارغ` |
| Unknown / inactive product | 400 | `بعض المنتجات غير موجودة أو غير متاحة` |
| Quantity below `0.001` | 400 | DRF field error on `lines` |
| Rep has no van | 400 | `لا يوجد مستودع مرتبط بهذا المندوب` |
| Company has no warehouse | 400 | `لا يوجد مستودع نشط للشركة` |

The unknown-product error lists the offending ids in `errors.lines[0]` —
`"Unknown or unavailable product ids: [7, 9]"` — so you can highlight the exact
rows instead of failing the whole form anonymously.

**There is no stock check at this point.** A rep may request 500 units of
something the company holds 3 of. The request is a request; availability is the
admin's problem at approval time, and the hard check happens at receipt (§8).

## 6. The office acts — the admin

Everything in this section requires the `stock_transfers` module with
`can_action`; listing needs `can_view`.

The three **responses** to a rep's request (6a–6c) live on
`/api/companies/stock-transfers/{id}/`, take an **empty body** except `modify`,
and return the updated detail object. The fourth (6d) is a `POST` to the
collection and starts a transfer of the office's own.

### The review queue

```
GET /api/companies/stock-transfers/?status=pending
```

Filters: `status`, `rep`, `search` — **`search` matches `number` only**, not
product or rep names. Ordered `-requested_at`, paginated.

### 6a. Approve as-is

```
POST /api/companies/stock-transfers/{id}/approve/
```

Copies each `requested_qty` into `approved_qty` and goes straight to `confirmed`.
Sets `approved_at` and `approved_by`. The rep gets `stock_transfer.confirmed`.
**No stock moves.**

### 6b. Modify quantities

```
POST /api/companies/stock-transfers/{id}/modify/
```

```json
{
  "lines": [
    { "line_id": 1, "approved_qty": "6" },
    { "line_id": 2, "approved_qty": "0" }
  ]
}
```

`line_id` is the **line's** id, from `lines[].id` — not the product id, and not
the transfer id. That is the most common integration bug on this endpoint. The
server catches a wrong id (`بعض البنود لا تنتمي لهذا الطلب`) only because it
happens not to exist on this transfer; a product id that collides with another
line's id would silently modify the wrong row.

Four rules, all enforced server-side:

- **Lines you omit keep their requested quantity.** Send only what you changed.
- **`approved_qty` may not exceed `requested_qty`.** An admin can cut, never
  inflate. To send more, cancel and have the rep raise a new request.
- **`0` is legal** and means "none of this one". The line stays on the document
  for the record but moves nothing at receipt.
- **At least one quantity must actually differ.** A `modify` that changes nothing
  is rejected with `لم يتم تعديل أي كمية — استخدم الموافقة المباشرة بدلاً من ذلك`
  — the server telling you to call `approve` instead. Compare against the
  original before enabling the submit button.

The response comes back at `pending_rep_confirmation`, and the rep gets
`stock_transfer.modified`.

### 6c. Cancel

```
POST /api/companies/stock-transfers/{id}/cancel/
```

Legal from `pending`, `modified_by_admin`, `pending_rep_confirmation` and
`confirmed`. Terminal, and there is no un-cancel. Notifies both sides.

Cancelling a `confirmed` transfer is legitimate and safe — no stock has moved, so
there is nothing to reverse. But if the rep already physically collected the
goods, the paperwork now disagrees with the van. Warn on this one.

### 6d. Dispatch — sending goods nobody asked for

```
POST /api/companies/stock-transfers/
```

For the van loaded overnight, the promotion pushed to the whole team, the stock
the office decides a rep should be carrying. Same body as a rep's request (§5),
plus the rep being sent to:

```json
{
  "rep": 3,
  "lines": [
    { "product_id": 1, "quantity": "10" },
    { "product_id": 2, "quantity": "5.5" }
  ],
  "notes": "تحميل ليلي"
}
```

| Field | Required | Notes |
|---|---|---|
| `rep` | ✅ | Must be **active and in your company** |
| `lines[].product_id` | ✅ | Same rules as §5 — `is_active`, not necessarily sellable |
| `lines[].quantity` | ✅ | Decimal, 3 dp, minimum `0.001` |
| `source_warehouse` | — | Defaults to the company's oldest active warehouse |
| `destination_warehouse` | — | Defaults to **that rep's** oldest active van |
| `notes` | — | Free text |

Returns **201** with the same detail object as everything else, at `confirmed`:

```json
{
  "id": 7,
  "number": "TRF-00007",
  "status": "confirmed",
  "rep": 3,
  "rep_name": "Kamal",
  "requested_at": "2026-08-30T05:40:00Z",
  "approved_at": "2026-08-30T05:40:00Z",
  "received_at": null,
  "lines": [
    {
      "id": 12,
      "product": 1,
      "product_name": "زيت دوار الشمس 1ل",
      "requested_qty": "10.000",
      "approved_qty": "10.000",
      "effective_qty": "10.000"
    }
  ]
}
```

Message: `تم إرسال البضاعة بانتظار استلام المندوب`.

Four things to read off that response:

- **`approved_qty` is already filled.** There is no proposal stage; the office
  set the quantity, so requested and approved are the same number from birth.
- **`requested_at` and `approved_at` are both set, to the same instant.** Do not
  render "requested by the rep at…" off `requested_at` without checking the
  origin — on a dispatch nobody requested anything. See below for how to tell.
- **`status` is `confirmed`, never `pending`.** It will not appear in a
  `?status=pending` review queue, which is correct: there is nothing to review.
- **No `Idempotency-Key`.** Unlike the rep's three field writes, this endpoint is
  not idempotent — it follows the same pattern as the other admin document
  creates. A double-submitted form is two transfers. Disable the button.

#### Telling the two origins apart

The document itself does not say which origin it came from. Two reliable tests,
in order of convenience:

1. **`status` on arrival.** A transfer that has ever been `pending` was
   rep-raised. In practice: if you see it at `confirmed` and it has no `pending`
   history, it was dispatched.
2. **The audit trail** (§11) is authoritative. A dispatch opens with the action
   `dispatched`; a request opens with `requested`. The two never both appear.

If the origin matters to your UI — and on a rep's list it does, because "your
request was approved" and "the office is sending you goods" are different
sentences — read the notification event key instead (§13), which is distinct per
origin and does not cost an extra call.

#### What the rep can do about it

Exactly what they could do with a transfer they raised themselves:

- **Receive it** — `POST /api/reps/stock-transfers/{id}/receive/`, §8. No special
  case, no new endpoint, and it is where the stock finally moves.
- **Refuse it** — `POST /api/reps/stock-transfers/{id}/reject/`. `confirmed →
  cancelled` was already a legal hop, so a rep who will not carry the goods can
  decline. Worth exposing: goods the rep never asked for are exactly the goods
  they might not want.

What nobody can do is approve or modify it again. Both return **409** on a
dispatched transfer, because it opened past the point where those apply. If your
dashboard renders action buttons off status rather than origin, this needs no
special handling — `confirmed` already hides them.

#### Errors

| Condition | Status | Body |
|---|---|---|
| Unknown, inactive, or other company's rep | 400 | `errors.rep` — `المندوب غير موجود أو غير نشط` |
| Empty `lines` | 400 | `لا يمكن إرسال طلب فارغ` |
| Unknown / inactive product | 400 | `بعض المنتجات غير موجودة أو غير متاحة` |
| That rep has no van | 400 | `لا يوجد مستودع مرتبط بهذا المندوب` |
| `destination_warehouse` is another rep's van | 400 | `المستودع لا يخص هذا المندوب` |
| Caller is a rep, not a subuser | 403 | — |

A rep id from another company fails as "not found" rather than "forbidden" — the
lookup is scoped to your company, so cross-tenant ids simply do not resolve.

**There is still no stock check here**, exactly as in §5. The office can dispatch
more than the warehouse holds; it fails at receipt (§8), not at dispatch.

## 7. The rep responds to a modification

```
POST /api/reps/stock-transfers/{id}/confirm/     → confirmed
POST /api/reps/stock-transfers/{id}/reject/      → cancelled
```

Both take an empty body and are only legal from `pending_rep_confirmation`.
`reject` is terminal — the rep raises a fresh request rather than negotiating on
the same document. Make that irreversibility visible before the tap.

Show the rep both numbers, per line, before they choose. The detail object gives
you all three:

```json
{
  "id": 1,
  "number": "TRF-00001",
  "rep": 1,
  "rep_name": "Kamal",
  "source_warehouse": 1,
  "source_warehouse_name": "المستودع الرئيسي",
  "destination_warehouse": 2,
  "destination_warehouse_name": "مستودع Kamal",
  "status": "pending_rep_confirmation",
  "requested_at": "2026-08-30T09:00:00Z",
  "approved_at": "2026-08-30T10:15:00Z",
  "received_at": null,
  "cancelled_at": null,
  "notes": "تحضير جولة الأحد",
  "created_at": "2026-08-30T09:00:00Z",
  "updated_at": "2026-08-30T10:15:00Z",
  "lines": [
    {
      "id": 1,
      "product": 1,
      "product_name": "زيت دوار الشمس 1ل",
      "product_sku": "OIL-1L",
      "unit": 1,
      "unit_name": "قطعة",
      "requested_qty": "10.000",
      "approved_qty": "6.000",
      "effective_qty": "6.000"
    }
  ]
}
```

`effective_qty` is the field to render everywhere except the "what changed"
comparison. It is `approved_qty` when set, `requested_qty` otherwise — the
quantity that will actually move. Computing it client-side from a null check
duplicates a server rule for no gain.

`approved_by` is **not** on the serializer. If the office needs to know who
approved, read the audit history (§11).

## 8. Receipt — the only stock movement

```
POST /api/reps/stock-transfers/{id}/receive/
Idempotency-Key: <uuid>
```

Empty body. Legal only from `confirmed`. In one transaction it writes a
`transfer_out` movement against the company warehouse, a `transfer_in` against
the van, sets `received_at`, and moves the status to `received`.

**Identical for both origins.** A dispatched transfer is received through this
same call, with no flag and no variant — which is the point of having the office
enter the machine at `confirmed` rather than inventing a second path.

Lines with `effective_qty` of `0` are skipped. If **every** line is zero — an
admin approved nothing — the call fails with `لا توجد كميات معتمدة لاستلامها`
rather than producing an empty receipt.

### Send the idempotency key. This is the call that needs it.

A rep in a warehouse basement taps *received*, the server commits, the response
times out, the app retries. Without `Idempotency-Key` that is a second transfer
of the same goods — the company warehouse drops twice and the van gains twice,
with no error anywhere, because the second call is individually valid.

With the header, the retry replays the original response verbatim. Rules:

- **Generate the key once per user intent**, when the rep taps the button, and
  reuse it for every retry of *that* tap. A key generated per HTTP request is a
  key that does nothing.
- A retry that arrives while the first is **still in flight** gets **409**. Back
  off and retry; do not surface it as a failure.
- The same key with a **different body** is rejected. That is a client bug, and
  the server refuses to paper over it.
- On failure the key is released, so the rep can fix the input and retry with the
  same key.

The same applies to `POST /reps/stock-transfers/` (§5) and
`POST /reps/sales-invoices/` (§10). Those three are the field app's entire
idempotent surface.

### Insufficient stock

Receipt is where availability is finally checked, against the **company**
warehouse. If someone else drained it between approval and collection:

```json
{
  "success": false,
  "message": "الكمية غير متوفرة في المستودع للمنتج: زيت دوار الشمس 1ل",
  "errors": {
    "product_id": ["1"],
    "warehouse_id": ["1"],
    "available": ["4.000"],
    "requested": ["6.000"]
  }
}
```

Nothing is written — not one line of the transfer moves, and the status stays
`confirmed`. The rep can retry after the office restocks.

`available` and `requested` are in the payload precisely so the rep sees the two
numbers rather than a bare failure. Render them. Note that the obvious recovery,
an admin `modify`, is **not legal from `confirmed`** — so in practice the office
cancels and the rep re-requests. Say that in the error UI; a rep staring at
"quantity unavailable" with no next step will phone the office instead.

---

# Part C — Selling

## 9. What is in the van

The van's warehouse id is not in the token or the signin response. Get it from:

```
GET /api/companies/warehouses/?owner_type=rep&is_active=true
```

```json
{
  "success": true,
  "data": {
    "warehouses": [
      {
        "id": 2,
        "name": "مستودع Kamal",
        "address": "",
        "kind": "",
        "owner_type": "rep",
        "rep": 1,
        "rep_name": "Kamal",
        "is_active": true,
        "created_at": "2026-08-30T13:13:14.965271Z",
        "updated_at": "2026-08-30T13:13:14.965286Z"
      }
    ]
  }
}
```

**This list is company-wide.** `?owner_type=rep` returns *every* rep's van, and
there is no `rep` query parameter. The client must match on
`rep === <own rep_id>` from the token. Two consequences: never render this list
raw in a rep app, and never assume the first row is theirs.

Then read the contents:

```
GET /api/companies/warehouses/{van_id}/product-stock/
```

Returns `data.stock` — an unpaginated array, one row per product, each carrying
`quantity`, `product_name`, `product_sku`, `product_barcode`, `unit_name`,
`reorder_point` and `is_low_stock`. This is the "what can I sell today" screen,
and `is_low_stock` is the natural trigger for "time to raise a transfer", looping
back to §5.

Per-product across all warehouses is the mirror endpoint:
`GET /api/companies/products/{id}/warehouse-stock/`.

## 10. The sale

```
POST /api/reps/sales-invoices/
Idempotency-Key: <uuid>
```

The whole visit in one call — the sale, any credits applied, and any cash handed
over. All of it commits together or none of it does.

```json
{
  "customer_id": 1,
  "lines": [
    { "product_id": 1, "quantity": "3" },
    { "product_id": 2, "quantity": "1", "unit_price": "12.50" }
  ],
  "payment_amount": "25.00",
  "fulfils_request_ids": [4],
  "notes": ""
}
```

| Field | Required | Notes |
|---|---|---|
| `customer_id` | ✅ | Must exist and be active |
| `lines[].product_id` | ✅ | **Must be `is_sellable`** — unlike the transfer |
| `lines[].quantity` | ✅ | Min `0.001` |
| `lines[].unit_price` | — | Omit to resolve from the catalog |
| `lines[].tax_rate` | — | Omit to use the company default |
| `warehouse` | — | **Defaults to the rep's van. Omit it.** |
| `date` | — | Defaults to now |
| `credit_ids` | — | Customer credits to apply |
| `payment_amount` | — | Cash collected on the spot |
| `payment_collected_at` | — | Defaults to the invoice date |
| `fulfils_request_ids` | — | Customer requests this delivery closes (§12) |
| `currency` | — | Defaults to the company's |

Omitting `unit_price` resolves the customer-category price first, then the
general price, on the document's currency. That is the same number the catalog
screen shows, so a rep can invoice without typing prices at all.

The stock deduction hits the **van**, not the company warehouse, and the
validation pins it to *this* rep — one rep cannot sell out of another's van even
by passing an explicit `warehouse` id.

An overdraw returns the same `الكمية غير متوفرة` shape as §8, with the van's
`warehouse_id` and its `available`. Nothing is written: no invoice, no partial
deduction, no payment.

**There is no credit limit.** An invoice with no payment and no credits is not an
error — it is `deferred`, a supported outcome. Do not require a payment amount.

See frontend.md §3.4 for the response object, status derivation
(`fully_paid` / `partially_paid` / `deferred`) and the payment endpoints.

---

# Part D — Things that will bite you

## 11. The audit history is admin-only

```
GET /api/companies/stock-transfers/{id}/history/
```

Every transition — `requested`, `dispatched`, `approved`, `modified`,
`awaiting_rep_confirmation`, `rep_confirmed`, `rep_rejected`, `cancelled`,
`received` — with `actor_type`, `actor_id`, `from_status`, `to_status`, a
`changes` object and a timestamp. `modified` carries the per-line before/after in
`changes.modified_lines`, and it is the **only** place `approved_by` is visible.

The first entry names the origin and is the authoritative test for it:
`requested` for a rep's own, `dispatched` for the office's. A dispatched
transfer's trail is short — `["dispatched", "received"]` — because there was
never an approval step to record.

There is no `/history/` on `/api/reps/stock-transfers/{id}/`. A rep-facing
timeline has to be built from the four timestamps on the document itself
(`requested_at`, `approved_at`, `received_at`, `cancelled_at`), which is enough
for a progress bar but cannot tell the rep *who* cut their quantities.

## 12. Customer requests are not stock transfers

Both live under the same app and both have lines with quantities. They are
unrelated documents, and conflating them is the most likely design error here.

| | Stock transfer | Customer request |
|---|---|---|
| Who raises it | **Rep** → the company | **Customer** → the company |
| Endpoint | `/api/reps/stock-transfers/` | `/api/customers/requests/` |
| Means | "Send me goods to sell" | "I'd like these on your next visit" |
| Moves stock | **Yes**, on `received` | **Never** |
| Approval | Full state machine | None — nothing to approve |
| Resolved by | The rep receiving it | The rep delivering a sales invoice |
| Has prices | No | No |

A customer request creates no commitment and no financial record. There is no
"fulfil" action: the rep closes one by passing its id in `fulfils_request_ids`
when writing the sale (§10). An invoice never has to reference a request, and a
request never has to become an invoice.

Admins see them read-only at `/api/companies/customer-requests/` (module
`customer_requests`, filters `status`, `customer`, `rep`); reps see the ones
assigned to them at `/api/reps/customer-requests/`.

## 13. Notifications are written, but there is no API to read them

Every step in Part B writes `Notification` rows — `stock_transfer.requested`,
`.dispatched`, `.modified`, `.confirmed`, `.received`, `.cancelled`, each with
Arabic title and body copy, plus `stock_transfer_id` and `number` in the payload.

`.dispatched` is deliberately distinct from `.confirmed`: one tells a rep the
office is sending goods they never asked for
(`بضاعة بانتظارك في المستودع`), the other tells them their own request was
approved (`طلب البضاعة جاهز للاستلام`). Both leave the transfer at `confirmed`,
so the event key is the cheapest way to render the right sentence.

**The notifications app exposes no URLs.** There is no list endpoint, no unread
count, no mark-as-read, and no push delivery. The rows accumulate server-side and
nothing can currently fetch them.

So the badge on the rep's transfer list has to come from polling and counting.
Poll **both** states that wait on the rep, or a dispatch will arrive silently:

```
GET /api/reps/stock-transfers/?status=pending_rep_confirmation
GET /api/reps/stock-transfers/?status=confirmed
```

Build it that way now; it will keep working when a notifications endpoint lands.
Do not design a screen around a notification feed that does not exist.

## 14. There is no way back to the depot

Transfers are strictly one-directional. `source_warehouse` must be
`owner_type: "company"` and `destination_warehouse` must be the rep's van — both
enforced, and there is no `direction` field. **The dispatch endpoint does not
change this**: it lets the office *start* a transfer, not reverse one. Both
origins move goods company → van.

Return invoices do not fill the gap either: when a rep is on the return, the
goods default **back into the rep's van**, because the normal case is a customer
handing goods back mid-round.

So "rep returns unsold stock to the warehouse at the end of the season" has no
first-class flow. The workaround is an admin creating a return invoice with an
explicit company `warehouse` — which credits the customer as a side effect, and
is therefore wrong for stock the rep never sold. **Do not build a rep-facing
"return to warehouse" button on top of it.** If the product needs one, it needs a
new endpoint.

## 15. Permissions and scoping, summarised

| Surface | Guard |
|---|---|
| `/api/companies/stock-transfers/` | `stock_transfers` — `can_view` to read, `can_action` to dispatch/approve/modify/cancel |
| `/api/companies/customer-requests/` | `customer_requests` — read-only |
| `/api/companies/products/`, `/warehouses/` | Authentication only, scoped by the token's company |
| `/api/reps/...` | `IsRep`, scoped to `rep_id` from the token |

Dispatching is `can_action` on `stock_transfers`, the same grant that already
allows approving and cancelling. A role that could approve a rep's request can
now also send goods unprompted — if that distinction matters to you, it needs a
new module rather than a client-side check.

Reps and customers hold **no** module permissions — the permission check returns
false for any actor that is not a subuser, so the `/api/companies/stock-transfers/`
endpoints are closed to reps regardless of the permission map. Owners bypass the
map entirely.

Note the asymmetry with §3 and §9: the *product* and *warehouse* endpoints under
`/api/companies/` are guarded by authentication alone, which is exactly why the
rep app can call them. They are still tenant-scoped, so a rep sees only their own
company — but within it, they see the whole catalog and every warehouse.

## 16. Numbers, quantities and money

- Transfer numbers are `TRF-00001`, per company, gapless, allocated at creation.
  A cancelled transfer keeps its number; the sequence does not rewind.
- Quantities are strings with 3 decimal places (`"10.000"`). Money has 2. **Both
  arrive as strings and must not be parsed into floats** — `0.1 + 0.2` will
  eventually put the wrong number in front of a customer. Use a decimal library
  for arithmetic, and send strings back.
- A transfer carries no money at all. No `total_amount`, no tax, no prices —
  nothing is being sold when goods move company → rep. Do not build a total row.

---

## 17. Client checklist

**Rep app**

- [ ] Filter the request screen by `is_active` only; filter the *sales* line
      picker by `is_sellable` too.
- [ ] Omit `source_warehouse` and `destination_warehouse` on transfer creation,
      and `warehouse` on sales invoices. Let the server default them.
- [ ] Send `Idempotency-Key` on create-transfer, receive, and create-invoice.
      Generate it per user intent, not per HTTP request.
- [ ] Treat 409 on receive as "refetch and re-render", not as an error toast.
- [ ] Render `effective_qty`, not `requested_qty`, everywhere except the
      "what the office changed" comparison.
- [ ] Badge **both** `pending_rep_confirmation` and `confirmed` by polling — no
      notification API exists, and a dispatch arrives straight at `confirmed`.
- [ ] Do not assume a transfer in the rep's list was raised by the rep. Label a
      dispatch "the office is sending you goods", not "your request was approved".
- [ ] Expose `reject` on a dispatched transfer too — goods the rep never asked
      for are the goods they are most likely to refuse.
- [ ] Match the van by `rep === own rep_id`; `?owner_type=rep` returns everyone's.
- [ ] Surface `available` vs `requested` on an insufficient-stock error, with a
      real next step ("ask the office to cancel and re-request").
- [ ] Make `reject` visibly terminal before the tap.
- [ ] Handle `لا يوجد مستودع مرتبط بهذا المندوب` for pre-existing reps.

**Admin dashboard**

- [ ] Send `line_id` — the line's id — to `modify`, never `product_id`.
- [ ] Send only changed lines; omitted ones keep their requested quantity.
- [ ] Disable submit on `modify` when nothing differs; call `approve` instead.
- [ ] Cap the quantity input at `requested_qty`; the server rejects more.
- [ ] Warn before cancelling a `confirmed` transfer — the rep may already hold
      the goods.
- [ ] Gate the whole screen on `stock_transfers`, and the action buttons on
      `can_action`.
- [ ] Use `/history/` for the "who approved this" question — it is not on the
      document. Its first entry (`requested` vs `dispatched`) is also the
      authoritative origin test.
- [ ] Remember `search` on the transfer list matches the number only.
- [ ] Disable the submit button on dispatch — that endpoint is **not**
      idempotent, so a double submit is two transfers.
- [ ] Do not offer approve/modify on a dispatched transfer; both 409 from
      `confirmed`.
- [ ] Expect a dispatch never to appear in the `?status=pending` review queue.

**Both**

- [ ] Never imply stock has moved before `received` — dispatching is not
      delivering.
- [ ] Treat `confirmed` as reachable from two directions, and never assume a
      transfer passed through `pending`.
- [ ] Handle `modified_by_admin` as a state even though you will rarely see it.
- [ ] Keep quantities and money as strings end to end.
- [ ] Do not assume `data.pagination` exists — product, warehouse and stock lists
      are unpaginated; transfer and invoice lists are not.
