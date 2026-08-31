# Rep App API — Home Screen

Integration reference for the sales rep application, screen by screen. This first
part covers **Home** (`الرئيسية`) — the dashboard a rep lands on after signing in.

Every example below is real output captured from the API, not hand-written.

> Conventions — base URL, JWT auth, the `{success, message, data}` envelope,
> pagination, idempotency and error shapes — are shared with the invoicing guide.
> See [frontend.md](frontend.md) §2–§6. Nothing here departs from them.

---

## 1. What the home screen shows, and where each figure comes from

```
┌──────────────────────────────────────────────────────┐
│  🔔            DASHBOARD                             │
│  ↑             أهلاً محمد            ← rep.name       │
│  notifications.unread_count                          │
├──────────────────────────────────────────────────────┤
│  [ × ]                          2026-08-31  📅       │  ← ?date=
├──────────────────────────────────────────────────────┤
│  ┌───────────────────┐  ┌─────────────────────────┐  │
│  │ إجمالي المستحقات   │  │ مبيعات الفترة (N فاتورة) │  │
│  │ receivables       │  │ sales.total_amount      │  │
│  │  .total_balance_due│  │ sales.invoice_count     │  │
│  └───────────────────┘  └─────────────────────────┘  │
├──────────────────────────────────────────────────────┤
│  📈 المبيعات                      sales.invoices[]   │
│  ↺  مرتجعات الفترة  N            returns.count       │
│                                  returns.return_…[] │
│  📦 مستودع السيارة  N قطعة        warehouse.…quantity │
│                                  warehouse.items[]  │
└──────────────────────────────────────────────────────┘
```

**One call fills the whole screen**: `GET /api/reps/dashboard/`.

The two headline cards answer *different questions*, and mixing them up is the
most likely bug when wiring this screen:

| Card | Question | Period-scoped? |
|---|---|---|
| `مبيعات الفترة` — `sales` | "what did I sell in this period" | **yes**, follows the date picker |
| `إجمالي المستحقات` — `receivables` | "what am I still owed" | **no**, always all-time |

That is why the screenshot can show `0 ل.س` of period sales next to `2,039,000`
of receivables. Debt from last week is still debt today; scoping it to the picker
would show every rep zero outstanding every morning. Do not apply the date filter
to the receivables card client-side.

---

## 2. Endpoints

| # | Call | Purpose |
|---|---|---|
| 1 | `GET /api/reps/dashboard/` | **Everything on this screen, in one read** |
| 2 | `GET /api/reps/inventory/` | The van's full contents, paged and searchable |
| 3 | `GET /api/reps/sales-invoices/` | The sales list past the inline preview |
| 4 | `GET /api/reps/return-invoices/` | The returns list past the inline preview |
| 5 | `GET /api/notifications/` | The bell menu |
| 6 | `GET /api/notifications/unread-count/` | The badge on its own |
| 7 | `POST /api/notifications/{id}/read/` | Mark one read |
| 8 | `POST /api/notifications/read-all/` | Mark the whole inbox read |
| 9 | `GET /api/reps/profile/` | The rep's own profile (pre-existing) |

3 and 4 already existed; 4 gained `date_from` / `date_to` so the same picker
drives it. Everything else is new.

The other screens are documented below: **stores** §7–11, **orders**
(customer requests) §12–16, **warehouse requests** §17–22.

All of these require a rep token (`actor_type: "rep"`). A subuser or customer
token gets **403**; no token gets **401**.

---

## 3. `GET /api/reps/dashboard/`

### Query parameters

| Param | Meaning |
|---|---|
| `date` | `YYYY-MM-DD`. The day picker's shorthand — expands to **that whole day** |
| `date_from` | Lower bound. A bare date means 00:00:00 of that day |
| `date_to` | Upper bound. A bare date means **23:59:59.999999** of that day |
| `limit` | Rows returned inline per section. Default `10`, max `50` |

Pass either `date`, or `date_from`/`date_to`. If both are sent, `date` wins.
Either bound may also be a full ISO 8601 timestamp, which is honoured exactly as
written.

**Sending no date parameters means no period filter** — which is exactly what the
`×` button on the picker should do. `sales` and `returns` then cover all time. Do
not substitute a client-side default; there is nothing to send to mean "all", the
absence *is* the signal.

> **The whole-day rule matters.** Document dates are timestamps. Were `date_to`
> compared as a plain date it would pin to midnight and silently drop everything
> written since — so `date_to=2026-08-31` covers that entire day. The same rule
> applies on the sales, returns and payment lists, so one pair of values drives
> every screen to the same answer.

An unparseable date returns **400** with the offending field named:

```json
{
  "success": false,
  "message": "صيغة التاريخ غير صالحة",
  "errors": { "date": ["Expected YYYY-MM-DD or an ISO 8601 timestamp."] }
}
```

### Response

```http
GET /api/reps/dashboard/?limit=2
```

```json
{
  "success": true,
  "message": "",
  "data": {
    "rep": {
      "id": 1,
      "name": "Sami",
      "phone": "+963911111111",
      "work_days": [],
      "company": { "id": 1, "name": "Tredro Foods" }
    },
    "period": { "date_from": null, "date_to": null },
    "currency": { "code": "SYP", "name": "Syrian Pound", "symbol": "L.S" },
    "sales": {
      "invoice_count": 1,
      "total_amount": "30.00",
      "paid_amount": "10.00",
      "balance_due": "10.00",
      "invoices": [
        {
          "id": 1,
          "number": "INV-SALE-00001",
          "date": "2026-08-31T08:33:39.018217Z",
          "rep": 1,
          "rep_name": "Sami",
          "customer": 1,
          "customer_name": "Abu Ahmad Market",
          "customer_phone": "+963955555555",
          "warehouse": 1,
          "company_name": "Tredro Foods",
          "tax_registration_no": "",
          "currency": "SYP",
          "line_count": 1,
          "total_amount": "30.00",
          "paid_amount": "10.00",
          "returned_amount": "10.00",
          "balance_due": "10.00",
          "overage_amount": "0.00",
          "status": "partially_paid",
          "notes": "",
          "created_at": "2026-08-31T08:33:39.019211Z",
          "updated_at": "2026-08-31T08:33:39.076785Z"
        }
      ]
    },
    "returns": {
      "count": 1,
      "total_amount": "10.00",
      "draft_count": 0,
      "return_invoices": [
        {
          "id": 1,
          "number": "INV-RET-00001",
          "date": "2026-08-31T08:33:39.057213Z",
          "sales_invoice": 1,
          "sales_invoice_number": "INV-SALE-00001",
          "rep": 1,
          "rep_name": "Sami",
          "warehouse": 1,
          "warehouse_name": "Sami's van",
          "company_name": "Tredro Foods",
          "tax_registration_no": "",
          "currency": "SYP",
          "status": "issued",
          "amount": "10.00",
          "overage_amount": "0.00",
          "refund_method": "",
          "notes": "",
          "issued_at": "2026-08-31T08:33:39.072113Z",
          "created_at": "2026-08-31T08:33:39.057623Z",
          "updated_at": "2026-08-31T08:33:39.073540Z"
        }
      ]
    },
    "receivables": {
      "invoice_count": 1,
      "total_balance_due": "10.00",
      "overdue_invoice_count": 0,
      "overdue_balance_due": "0.00"
    },
    "warehouse": {
      "id": 1,
      "name": "Sami's van",
      "total_quantity": "198.000",
      "product_count": 2,
      "items": [
        {
          "id": 1,
          "product_id": 1,
          "product_name": "Rice 1kg",
          "product_sku": "",
          "product_barcode": "",
          "unit": 1,
          "unit_name": "Package",
          "unit_code": "package",
          "quantity": "98.000",
          "unit_price": "10.00",
          "is_low_stock": null,
          "image": null,
          "updated_at": "2026-08-31T08:33:38.997078Z"
        },
        {
          "id": 2,
          "product_id": 2,
          "product_name": "Sugar 1kg",
          "product_sku": "",
          "product_barcode": "",
          "unit": 1,
          "unit_name": "Package",
          "unit_code": "package",
          "quantity": "100.000",
          "unit_price": "5.00",
          "is_low_stock": null,
          "image": null,
          "updated_at": "2026-08-31T08:33:38.997095Z"
        }
      ]
    },
    "notifications": { "unread_count": 1 }
  }
}
```

### Field notes

**All money is a fixed-precision string**, never a JSON number — parse it as a
decimal, not a float. `quantity` and `total_quantity` are strings with 3 decimal
places for the same reason.

`period` echoes the resolved window back, so the client can confirm what the
server actually filtered on. `null`/`null` means all time.

`currency` is the company's currency with its symbol (`ل.س`), so the screen does
not hard-code one.

**`sales`** — over invoices whose `date` falls in the period:

| Field | Meaning |
|---|---|
| `invoice_count` | The `(N فاتورة)` on the card |
| `total_amount` | The card's headline figure |
| `paid_amount` | Of that period's invoices, how much has been paid **to date** |
| `balance_due` | Of that period's invoices, how much is still owed |
| `invoices[]` | First `limit` rows, newest first — identical shape to the sales list |

Every sales-invoice row also carries `line_count` — how many products are on the
invoice, the `N صنف` the list prints beside the date. It is counted in the list
query itself, so it costs nothing per row.

`paid_amount` and `balance_due` describe *those invoices' current state*, not cash
collected during the window. For cash-in over a window, read
`GET /api/reps/payments/?date_from=…&date_to=…`, which returns `total_amount`.

**`returns`** — `count` and `total_amount` cover **issued** returns only, because
only an issued return moved goods or money. `draft_count` is returns the rep
started and has not committed; badge it as unfinished work rather than adding it
to the total. `مرتجعات الفترة N` is `returns.count`.

**`receivables`** — all-time, never period-scoped:

| Field | Meaning |
|---|---|
| `total_balance_due` | `إجمالي المستحقات` — the headline figure |
| `invoice_count` | How many invoices are still owed |
| `overdue_balance_due` | The subset past the company's overdue threshold |
| `overdue_invoice_count` | How many of those there are |

The overdue threshold is the company's own `overdue_threshold_days` (default 7),
the same one the admin overdue report uses — so "late" means one thing in both
apps.

**`warehouse`** — `مستودع السيارة`. **May be `null`**, when the rep has no active
van. Render "no warehouse assigned", not an empty van; they are different things
to a rep about to load up. Handle this case — do not assume the object exists.

`total_quantity` is the `314 قطعة` figure: a plain sum of quantities across
products, deliberately adding cartons to bags. It is a count of things loaded;
the per-line `unit_name` is what carries the meaning.

`items[]` is the first `limit` rows, sorted by product name, and **omits products
that have run out**. `unit_price` is the general catalog price in the company's
currency, or `null` when the catalog has none — it is the shelf price, and the
price actually charged is still resolved per customer when the invoice is
written, because a customer category can override it.

`is_low_stock` is tri-state: `true`/`false` against the product's reorder point,
and `null` when the product has no reorder point set — "not tracked", not
"healthy".

**`notifications.unread_count`** is the bell badge.

### Reading past the previews

`invoices[]`, `return_invoices[]` and `warehouse.items[]` are a first page, not
the whole set. Beyond `limit`, use the paged endpoints — they accept the same
dates, so "see all" needs no re-filtering:

```
GET /api/reps/sales-invoices/?date_from=…&date_to=…
GET /api/reps/return-invoices/?date_from=…&date_to=…
GET /api/reps/inventory/
```

---

## 4. `GET /api/reps/inventory/` — the van, in full

Read-only. A van's quantities are the stock ledger's answer and move only through
the documents that move goods — receiving a transfer, writing a sale, taking a
return. There is nothing here to edit.

| Param | Meaning |
|---|---|
| `search` | Matches product name, SKU or barcode |
| `include_empty` | `true` keeps products that have run out. Default hides them |
| `page`, `page_size` | Standard pagination |

```http
GET /api/reps/inventory/
```

```json
{
  "success": true,
  "message": "",
  "data": {
    "items": [
      {
        "id": 1,
        "product_id": 1,
        "product_name": "Rice 1kg",
        "product_sku": "",
        "product_barcode": "",
        "unit": 1,
        "unit_name": "Package",
        "unit_code": "package",
        "quantity": "98.000",
        "unit_price": "10.00",
        "is_low_stock": null,
        "image": null,
        "updated_at": "2026-08-31T08:33:38.997078Z"
      }
    ],
    "warehouse": { "id": 1, "name": "Sami's van" },
    "total_quantity": "198.000",
    "product_count": 2,
    "currency": "SYP",
    "pagination": { "count": 2, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

`warehouse`, `total_quantity` and `product_count` describe the **whole filtered
set**, not the current page — they are the header the van screen prints above the
list. `warehouse` is `null` when the rep has no active van, and `items` is then
empty.

`items[]` rows are the same shape as `dashboard.warehouse.items[]`, so one cell
component renders both. `image` is `{id, image, alt_text}` for the product's cover
image, with an absolute URL, or `null`.

---

## 5. Notifications — the bell

Rows are written by the events that raise them; a client can only read them and
mark them read. There is no create or delete.

`GET /api/notifications/` is **not** under `/api/reps/` — the recipient is
whoever holds the token, so the same URL serves the rep app, the admin dashboard
and the customer app, each seeing only their own.

### `GET /api/notifications/`

| Param | Meaning |
|---|---|
| `unread` | `true` returns only unread rows |
| `event_key` | Filter to one event type, e.g. `stock_transfer.dispatched` |
| `page`, `page_size` | Standard pagination |

```json
{
  "success": true,
  "message": "",
  "data": {
    "notifications": [
      {
        "id": 1,
        "event_key": "stock_transfer.dispatched",
        "title": "بضاعة بانتظارك في المستودع",
        "body": "أرسلت لك الإدارة بضاعة جاهزة للاستلام من المستودع.",
        "payload": { "title": "…", "body": "…" },
        "is_read": false,
        "read_at": null,
        "created_at": "2026-08-31T08:33:39.101Z"
      }
    ],
    "unread_count": 1,
    "pagination": { "count": 1, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

`unread_count` counts the **whole** unread inbox, not the filtered page — a rep
viewing "unread only" still needs the total for the badge.

`title` and `body` are ready-to-render Arabic copy lifted out of `payload`. A
client that renders its own wording, or needs ids to deep-link into the document
that raised the event, reads `payload` and ignores them.

Event keys a rep can receive today: `stock_transfer.dispatched`,
`stock_transfer.modified`, `stock_transfer.confirmed`, `stock_transfer.cancelled`,
`customer_request.created`.

### The rest

| Call | Returns |
|---|---|
| `GET /api/notifications/unread-count/` | `{"unread_count": 1}` — cheap enough to poll |
| `POST /api/notifications/{id}/read/` | `{"notification": {…}}` with `is_read: true` |
| `POST /api/notifications/read-all/` | `{"updated_count": 3, "unread_count": 0}` |

Marking an already-read notification read again is a no-op — `read_at` keeps the
timestamp it was first seen at. Acting on a notification addressed to someone else
returns **404**, not 403: it is not yours to know about.

---

## 6. Suggested client flow

```
signin  →  POST /api/auth/rep/signin

open home, today selected:
        →  GET /api/reps/dashboard/?date=<today>          (one call, whole screen)

user clears the picker (×):
        →  GET /api/reps/dashboard/                       (no params = all time)

user taps a section's "see all":
   sales   → GET /api/reps/sales-invoices/?date_from=…&date_to=…
   returns → GET /api/reps/return-invoices/?date_from=…&date_to=…
   van     → GET /api/reps/inventory/

user taps the bell:
        →  GET /api/notifications/
        →  POST /api/notifications/{id}/read/   on tap
```

Poll `GET /api/notifications/unread-count/` for the badge while the app is open,
or simply re-read the dashboard — it carries the same number.

### Things that will bite

- **Money and quantities are strings.** Parse as decimal. `"2039000.00"`.
- **`warehouse` can be `null`.** A rep without an active van still gets a
  dashboard.
- **`unit_price` can be `null`.** The catalog has no general price for that
  product in the company's currency. Show the quantity without a price rather
  than `0`.
- **`is_low_stock` is tri-state**, `null` means untracked.
- **Do not date-filter receivables** client-side; the server deliberately did not.
- **Only issued returns count.** `returns.count` excludes drafts by design.
- **Access token lifetime is short.** Refresh via `POST /api/auth/token/refresh`
  and retry, rather than bouncing the rep to the sign-in screen.


---
---

# Rep App API — Stores

The stores list (`المحلات`) and the store page. A "store" is a `Customer` the rep
is assigned to; the API calls them customers throughout.

---

## 7. What the two screens show

```
STORES LIST                              STORE PAGE
┌───────────────────────────────┐        ┌──────────────────────────────────┐
│ المحلات          STORES 5     │        │ بقالية الشهباء          السبت     │
│                  ↑ data.total │        │  ↑ name        work_days[0] ↑    │
├───────────────────────────────┤        ├──────────────────────────────────┤
│ بقالية الشهباء             >  │        │ إجمالي  │ المدفوع  │ المتبقي      │
│ شارع النيل، الفرقان، حلب       │        │ الفواتير │         │              │
│   ↑ address                   │        │ total_  │ paid_   │ balance_due  │
│ ┌────────┬─────────┬────────┐ │        │ invoiced│ amount  │              │
│ │ اليوم  │ مدفوع   │ متبقي  │ │        ├──────────────────────────────────┤
│ │ السبت  │ 580,000 │989,000 │ │        │ +963944111222       <- phone     │
│ └────────┴─────────┴────────┘ │        ├──────────────────────────────────┤
│  work_days  paid_   balance_  │        │ السجل │ فاتورة │ الدفعات│المرتجعات │
│             amount  due       │        ├──────────────────────────────────┤
└───────────────────────────────┘        │ الطلبات السابقة  <- customer-    │
                                         │   زيت دوار الشمس x24   requests  │
                                         │ الفواتير         <- sales-       │
                                         │   INV-6528 ... معلقة    invoices │
                                         └──────────────────────────────────┘
```

**The row and the page carry the same fields.** `total_invoiced`, `paid_amount`
and `balance_due` are on the customer object in both responses — the list row
shows two of them, the page shows all three. One model, one cell component.

**The balance is what this store owes _this rep_.** A store may also buy direct
from the company, or from another rep; those invoices belong to that rep's
figures, not this one's. Everything under `/api/reps/` is scoped this way.

---

## 8. `GET /api/reps/customers/` — the stores list

| Param | Meaning |
|---|---|
| `search` | Matches name, phone **or address** |
| `work_day` | One day, e.g. `saturday` — "today's route" |
| `is_active` | `true` / `false` |

`work_day` matches the days assigned for *this* rep–store pair, falling back to
the rep's own default days when the pair names none — the same rule that decides
the badge printed on the row, so filter and badge can never disagree.

```json
{
  "success": true,
  "message": "",
  "data": {
    "customers": [
      {
        "id": 1,
        "name": "Abu Ahmad Market",
        "phone": "+963955555555",
        "email": null,
        "category_details": null,
        "assigned_reps_count": 1,
        "assigned_reps_details": [
          {
            "id": 1,
            "name": "Sami",
            "phone": "+963911111111",
            "company_id": 1,
            "referral_code": "REP-SAMI",
            "work_days": ["saturday"]
          }
        ],
        "referral_code_used": null,
        "address": "شارع النيل، الفرقان، حلب",
        "latitude": null,
        "longitude": null,
        "is_active": true,
        "created_at": "2026-08-31T08:58:14.950341Z",
        "updated_at": "2026-08-31T08:58:14.950349Z",
        "work_days": ["saturday"],
        "invoice_count": 1,
        "total_invoiced": "100.00",
        "paid_amount": "40.00",
        "returned_amount": "0.00",
        "balance_due": "60.00"
      },
      {
        "id": 2,
        "name": "ماركت السريان",
        "phone": "+963955000009",
        "address": "السريان الجديدة، دوار الرازي",
        "work_days": ["monday"],
        "invoice_count": 0,
        "total_invoiced": "0.00",
        "paid_amount": "0.00",
        "returned_amount": "0.00",
        "balance_due": "0.00"
      }
    ],
    "total": 2
  }
}
```

*(the second row is abridged — every row has the same fields)*

`data.total` is the `STORES 5` count. This list is **not paged**; it returns the
rep's whole assigned set, unchanged from before.

### Fields

| Field | Notes |
|---|---|
| `address` | **New.** Free text: street, neighbourhood, city. `""` when unset, never null |
| `work_days` | Days *this* rep visits *this* store. `[]` when neither the pair nor the rep names any |
| `total_invoiced` | `إجمالي الفواتير` — sum of this rep's invoices to this store |
| `paid_amount` | `مدفوع` |
| `returned_amount` | Credited back by issued returns |
| `balance_due` | `متبقي` — what is still owed |
| `invoice_count` | How many invoices make up those figures |

All money is a **fixed-precision string**. A store with no invoices reports
`"0.00"`, not `null` — that is the `0 ل.س` card, and it means "nothing owed", not
"unknown".

`assigned_reps_details[]` is unchanged and still lists every rep on the store;
the top-level `work_days` is the shortcut for the asking rep's own row, which is
what the badge shows.

---

## 9. `GET /api/reps/customers/{id}/` — the store page

Same object, wrapped as `{"customer": {…}}`. **404** if the store is not assigned
to the asking rep.

```json
{
  "success": true,
  "message": "",
  "data": {
    "customer": {
      "id": 1,
      "name": "Abu Ahmad Market",
      "phone": "+963955555555",
      "address": "شارع النيل، الفرقان، حلب",
      "work_days": ["saturday"],
      "invoice_count": 1,
      "total_invoiced": "100.00",
      "paid_amount": "40.00",
      "returned_amount": "0.00",
      "balance_due": "60.00",
      "latitude": null,
      "longitude": null,
      "is_active": true
    }
  }
}
```

The three header cards are `total_invoiced` / `paid_amount` / `balance_due`. The
phone under them is `phone` — dial it as-is.

### The four tabs

There is no separate "store detail with everything" endpoint. Each tab is an
existing document list filtered by `?customer={id}`, so each pages and filters on
its own:

| Tab | Call | Rows under |
|---|---|---|
| `السجل` → الطلبات السابقة | `GET /api/reps/customer-requests/?customer={id}` | `requests` |
| `السجل` → الفواتير | `GET /api/reps/sales-invoices/?customer={id}` | `invoices` |
| `الدفعات` | `GET /api/reps/payments/?customer={id}` | `payments` |
| `المرتجعات` | `GET /api/reps/return-invoices/?customer={id}` | `return_invoices` |

All four also accept `date_from` / `date_to` (§3's whole-day rule applies).
`payments` and `return_invoices` additionally return a `total_amount` for the
filtered set.

**`الطلبات السابقة`** — the rep's request list carries its `lines` inline, so
`زيت دوار الشمس ١ ل ×24` renders without a second call:

```json
{
  "requests": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "Abu Ahmad Market",
      "status": "pending",
      "fulfilled_by_invoice": null,
      "fulfilled_by_invoice_number": null,
      "created_at": "2026-08-31T08:58:15.013172Z",
      "lines": [
        {
          "id": 1,
          "product": 2,
          "product_name": "زيت دوار الشمس ١ ل",
          "product_sku": "",
          "unit": 1,
          "unit_name": "عبوة",
          "desired_quantity": "24.000"
        }
      ]
    }
  ]
}
```

A request is a *wishlist signal*, not an order — nothing is reserved and nothing
is owed. Filter to `?status=pending` for "still outstanding". A rep resolves one
by passing its id in `fulfils_request_ids` when writing the sales invoice.

**`الفواتير`** — rows come from `SalesInvoiceSerializer` (see §3), which carries
`line_count`: the `N صنف` printed beside the date, i.e. how many products the
invoice holds. The badge maps from `status`:

| `status` | Badge |
|---|---|
| `fully_paid` | `مدفوعة` |
| `partially_paid`, `deferred` | `معلقة` |

---

## 10. Writes on a store

### `POST /api/reps/customers/`

Creates the store **and assigns it to the calling rep** in one step.

```json
{
  "name": "بقالية الهلك",
  "phone": "+963944111222",
  "address": "الهلك، الشارع الرئيسي",
  "email": "optional@example.com",
  "latitude": 33.513805,
  "longitude": 36.276527,
  "work_days": ["tuesday"]
}
```

`name` and `phone` are required; the phone must be `+963XXXXXXXXX` and unique
across all customers. `work_days` sets the new assignment's days. Returns **201**
with the same customer shape as the list (balances at `"0.00"`).

### `PATCH /api/reps/customers/{id}/`

The rep standing outside the shop is the one who knows where it is, so address,
pin and visiting days are all theirs to correct. Send only what changed:

```json
{
  "address": "السليمانية، شارع الحمام",
  "latitude": 33.513805,
  "longitude": 36.276527,
  "work_days": ["sunday", "wednesday"]
}
```

`latitude` and `longitude` must be sent **together or not at all**. `work_days`
updates this rep's own assignment, not the rep's global default — for that, use
`PATCH /api/reps/profile/`. The response message names what changed
(`تم تحديث العنوان و أيام العمل بنجاح`).

Nothing else about a store is editable by a rep: name, phone and category belong
to the admin dashboard.

---

## 11. Things that will bite

- **`total`, not `pagination`.** The stores list returns the whole set under
  `data.total`; the four tab endpoints are paged as usual.
- **Balances are per-rep.** Two reps serving one store see two different
  `balance_due` values, and both are correct.
- **`work_days` is a list**, even though the badge shows one day. A store may be
  visited more than once a week.
- **`address` is `""` when unset**, never `null` — every customer created before
  this field reads `""`.
- **404, not 403**, when opening a store that is not assigned to you.


---
---

# Rep App API — Orders

The rep's orders screen (`الطلبات`): what customers have asked for, and the rep's
answer. One endpoint family — `/api/reps/customer-requests/`.

---

## 12. What a request is, and what answering one does

A customer request is a **wishlist signal**, not an order. The customer app sends
it; nothing is reserved, no stock moves, no money is owed.

Answering does not change that:

- **`قبول` (accept)** is a promise to visit, not a reservation. The goods stay in
  the van, sellable to whoever the rep reaches first.
- **`رفض` (reject)** is a decline, optionally with a reason the customer sees.
- **Neither moves stock nor creates a debt.**

**`تم التسليم` is not an endpoint here.** A delivery is a Sales Invoice — the only
document that deducts the van and creates the debt — so the button opens the
invoice screen prefilled from the request's lines, and the request is marked
delivered by that invoice:

```
                POST /reps/customer-requests/{id}/accept/
  pending ──────────────────────────────────────> accepted
     │                                               │
     │  POST .../reject/                             │  POST /api/reps/sales-invoices/
     ▼                                               │  { fulfils_request_ids: [id] }
  rejected                                           ▼
                                                 fulfilled
```

A request may also reach `cancelled` — the **customer** withdrawing it from their
own app. `rejected` and `cancelled` are both closed-without-delivery but are not
the same event, and the API keeps them apart so either side can see who ended it.

Both `pending` and `accepted` are deliverable. Only `fulfilled`, `rejected` and
`cancelled` are closed.

### Status → UI

| `status` | Badge | Buttons |
|---|---|---|
| `pending` | `بانتظار الموافقة` | `قبول` / `رفض` |
| `accepted` | `مقبول` | `تم التسليم` → invoice screen |
| `fulfilled` | `تم التسليم` | none |
| `rejected` | `مرفوض` | none |
| `cancelled` | withdrawn by customer | none |

The filter tabs map straight onto `?status=`: `الكل` (omit), `معلق` → `pending`,
`مقبول` → `accepted`, `مسلم` → `fulfilled`, `مرفوض` → `rejected`.

---

## 13. `GET /api/reps/customer-requests/`

Scoped to the authenticated rep. Newest first, paged.

| Param | Meaning |
|---|---|
| `status` | One of the five above — the filter tabs |
| `customer` | One store — the store page's `الطلبات السابقة` section |
| `date`, `date_from`, `date_to` | Filters on `created_at`. Same whole-day rule as §3 |

`ORDERS 4` is `data.pagination.count`.

```json
{
  "success": true,
  "message": "",
  "data": {
    "requests": [
      {
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
        "accepted_at": null,
        "rejected_at": null,
        "rejection_reason": "",
        "line_count": 2,
        "notes": "",
        "created_at": "2026-08-31T09:30:50.095404Z",
        "updated_at": "2026-08-31T09:30:50.095414Z",
        "lines": [
          {
            "id": 1,
            "product": 1,
            "product_name": "Rice 1kg",
            "product_sku": "",
            "unit": 1,
            "unit_name": "Package",
            "desired_quantity": "3.000",
            "unit_price": "10.00",
            "line_total": "30.00"
          },
          {
            "id": 2,
            "product": 2,
            "product_name": "Sugar 1kg",
            "product_sku": "",
            "unit": 1,
            "unit_name": "Package",
            "desired_quantity": "24.000",
            "unit_price": "5.00",
            "line_total": "120.00"
          }
        ],
        "estimated_total": "150.00"
      }
    ],
    "pagination": { "count": 2, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

### The money on a card is indicative

`unit_price`, `line_total` and `estimated_total` are **resolved from the catalog
on read and never stored**. Nothing has been agreed — the rep prices the goods
when the Sales Invoice is written, and the invoice is what binds.

They are what this customer would be charged *today*, honouring their category
override, so the number matches what the invoice screen will propose. If the
catalog changes before the visit, the next read shows the new figure. That is
correct: no price was ever promised.

**`null` means "not priced", which is not "free".** A product the catalog has no
price for in the company's currency comes back with `unit_price: null` and
`line_total: null`, and is *skipped* rather than counted as zero when summing.
`estimated_total` is `null` when nothing on the request could be priced — render
"no price", not `0`. If a card must be honest about a partial total, compare each
line's `unit_price` against null.

### Other fields

| Field | Notes |
|---|---|
| `line_count` | Rows on the request, for a summary badge |
| `accepted_at` / `rejected_at` | Set by the two actions below |
| `rejection_reason` | `""` unless the rep gave one. Shown to the customer |
| `fulfilled_by_invoice_number` | The invoice that delivered it, e.g. `INV-SALE-00001` |
| `notes` | Free text from the customer at request time |

`GET /api/reps/customer-requests/{id}/` returns one, wrapped as `{"request": …}`,
with the same shape. **404** if the request belongs to another rep.

---

## 14. Answering a request

### `POST /api/reps/customer-requests/{id}/accept/`

No body. Returns the updated request in the shape above:

```json
{
  "success": true,
  "message": "تم قبول الطلب",
  "data": {
    "request": {
      "id": 2,
      "status": "accepted",
      "accepted_at": "2026-08-31T09:30:50.745503Z",
      "rejection_reason": "",
      "line_count": 1,
      "lines": [ … ],
      "estimated_total": "120.00"
    }
  }
}
```

*(abridged — the response carries every field the list row does)*

### `POST /api/reps/customer-requests/{id}/reject/`

```json
{ "reason": "المنتج غير متوفر حالياً" }
```

`reason` is optional; omit it or send `""` for a bare decline. It is stored on
`rejection_reason` and shown to the customer.

### Both

**Only a `pending` request can be answered.** Accepting twice, or flipping an
accepted request to rejected, returns **400**:

```json
{
  "success": false,
  "message": "لا يمكن الرد على طلب تم الرد عليه مسبقاً",
  "errors": {
    "status": ["Only a pending request can be answered; this one is 'accepted'."]
  }
}
```

Telling a customer yes and then silently switching to no is a conversation, not a
status edit — so the API will not do it. Disable the buttons once `status` is
anything but `pending`.

The customer is notified either way, on their own bell
(`GET /api/notifications/`, §5):

| Event key | Copy |
|---|---|
| `customer_request.accepted` | `وافق المندوب على طلبك` |
| `customer_request.rejected` | `تعذر تنفيذ طلبك` |

---

## 15. Delivering — `تم التسليم`

There is no delivery endpoint on this viewset. The button opens the sales-invoice
screen with the request's lines prefilled, and the rep posts:

```http
POST /api/reps/sales-invoices/
Idempotency-Key: <uuid>
```

```json
{
  "customer": 1,
  "lines": [{ "product": 1, "quantity": "12.000" }],
  "fulfils_request_ids": [2],
  "payment_amount": "120000.00"
}
```

That one call deducts the van, creates the debt, records any cash collected, and
flips the request to `fulfilled` with `fulfilled_by_invoice` and `fulfilled_at`
set — all in one transaction. See [frontend4.md](frontend4.md) for the full sales
flow.

Things worth knowing:

- **The invoice need not match the request.** A rep may deliver more, less, or
  different products; prices are decided at invoice time. The request is a
  starting point for the screen, not a contract.
- **One invoice can fulfil several requests** — pass all their ids.
- **`fulfils_request_ids` is optional.** A rep may sell to a walk-in with no
  request at all.
- **A closed request cannot be delivered against.** Passing a `fulfilled`,
  `rejected` or `cancelled` id returns **400** naming the offending ids.

---

## 16. Things that will bite

- **Prices are indicative and can be `null`.** Never render `null` as `0`.
- **Accepting reserves nothing.** If the UI implies stock is held for that
  customer, it is lying to both of them.
- **Answer once.** Buttons are live only while `status == "pending"`.
- **`rejected` ≠ `cancelled`.** The rep declined vs. the customer withdrew.
- **Delivery goes through the invoice endpoint**, and the request updates itself
  as a side effect — re-read it, or read `fulfilled_request_ids` off the invoice
  response.
- **404, not 403**, for another rep's request.


---
---

# Rep App API — Warehouse Requests

The rep's `طلباتي` screen: asking the company warehouse for goods to load into
the van, and the history of past requests.

---

## 17. What this screen is, and what it is not

A **stock transfer** moves goods from a company warehouse into the rep's van. It
is not an invoice: no tax fields, no debt, **nobody is charged**. Both warehouses
belong to the same company; the goods simply change location.

The money shown on these cards is therefore the **shelf value of the goods**, not
a bill — it is there so the rep can see what they are asking to carry.

### The one rule that governs the whole flow

**Stock moves on `received`, and nowhere else.** Sending the request does not move
it. The admin approving does not move it. A transfer sitting at `confirmed` for a
week has changed no quantity in any warehouse. Only the rep tapping "استلمت"
does, at which point the company warehouse drops and the van rises, atomically.

```
  rep sends            admin approves as-is        rep collects
  POST /reps/          POST /companies/…/approve/  POST /reps/…/receive/
  stock-transfers/            │                            │
      │                       │                            │
   pending ──────────────> confirmed ──────────────────> received
      │                       ▲                     ← THE ONLY STOCK MOVEMENT
      │ admin cuts quantities │
      ▼                       │ rep accepts
  modified_by_admin ─> pending_rep_confirmation ─┤
                                                 └ rep rejects → cancelled
```

### Status → UI

| `status` | Badge |
|---|---|
| `pending` | بانتظار موافقة المستودع |
| `modified_by_admin`, `pending_rep_confirmation` | تم تعديل الكميات — needs `confirm`/`reject` |
| `confirmed` | جاهز للاستلام |
| `received` | تم التسليم · ✓ أضيفت لمستودع السيارة |
| `cancelled` | ملغى |

Full flow, including the office-dispatch origin, is in
[frontend4.md](frontend4.md).

---

## 18. `GET /api/reps/products/` — the picker

The list behind `طلب بضاعة جديد`. The company's sellable catalog, with the shelf
price and — the reason this exists rather than `/api/companies/products/` —
**`van_quantity`**, the `بالسيارة N` under each row.

A rep ordering stock has to see what they are already carrying, or they order a
second carton of tea that is sitting in the van.

> Not the same as `/api/reps/inventory/` (§4). That one answers *"what is in my
> van"* and hides sold-out rows. This one answers *"what could I ask for"* and
> lists products with `van_quantity: "0.000"` — on a restock screen those are the
> important rows.

| Param | Meaning |
|---|---|
| `search` | Name, SKU or barcode |
| `category` | Product category id |
| `page`, `page_size` | Standard pagination |

```json
{
  "success": true,
  "message": "",
  "data": {
    "products": [
      {
        "id": 1,
        "name": "Rice 1kg",
        "sku": "",
        "barcode": "",
        "category": null,
        "unit": 1,
        "unit_name": "Package",
        "unit_code": "package",
        "price": "10.00",
        "van_quantity": "24.000",
        "image": null
      },
      {
        "id": 2,
        "name": "Sugar 1kg",
        "price": "5.00",
        "van_quantity": "0.000",
        "image": null
      }
    ],
    "currency": "SYP",
    "pagination": { "count": 2, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

Only **active, sellable** products appear. `price` is the general shelf price and
is `null` when the catalog has none — `null` means "not priced", never "free".
`van_quantity` is always a number, `"0.000"` when the rep carries none: not
carrying something is a known quantity, not a missing one.

---

## 19. `POST /api/reps/stock-transfers/` — send the request

```http
POST /api/reps/stock-transfers/
Idempotency-Key: <uuid>
```

```json
{
  "lines": [
    { "product_id": 1, "quantity": "24" },
    { "product_id": 2, "quantity": "40" }
  ],
  "pickup_within_hours": 3,
  "notes": ""
}
```

| Field | Notes |
|---|---|
| `lines[].product_id` | **`product_id`**, not `product` |
| `lines[].quantity` | String or number, must be > 0 |
| `pickup_within_hours` | Optional. `وقت الاستلام` — the chips 1/2/3/4/6. Any 1–24 accepted |
| `source_warehouse`, `destination_warehouse` | Optional; default to the company's main warehouse and the rep's own van |
| `notes` | Optional free text |

Send an `Idempotency-Key`: a dropped response on a bad connection must not turn
one request into two. Returns **201** with the transfer at `pending`, and the
warehouse staff get a notification.

### About `pickup_within_hours`

It is **information, not a rule.** It tells the warehouse keeper when to have the
goods on the dock. Nothing enforces it: a transfer does not expire, is not
cancelled when the window passes, and the rep can still collect a day later.

`pickup_deadline` is returned alongside it and is simply `requested_at +
pickup_within_hours` — derived on read, so the two can never drift apart. Both are
`null` when no window was given, which is always the case for a transfer the
office dispatched (the rep never asked, so promised nothing).

That is the `مهلة الاستلام 3 ساعة · حتى 14:30` on each card: the window, and the
deadline it implies.

---

## 20. `GET /api/reps/stock-transfers/` — the history

Scoped to the rep, newest first, paged. Every row carries its lines and total —
the card renders without a second call.

| Param | Meaning |
|---|---|
| `status` | One of the six statuses |
| `date`, `date_from`, `date_to` | Filters on `requested_at`. Same whole-day rule as §3. Omit for `كل التواريخ` |

```json
{
  "success": true,
  "message": "",
  "data": {
    "transfers": [
      {
        "id": 1,
        "number": "TRF-00001",
        "rep": 1,
        "rep_name": "Sami",
        "source_warehouse": 2,
        "source_warehouse_name": "Main store",
        "destination_warehouse": 1,
        "destination_warehouse_name": "Sami's van",
        "status": "received",
        "requested_at": "2026-08-31T12:09:22.745206Z",
        "pickup_within_hours": 3,
        "pickup_deadline": "2026-08-31T15:09:22.745206Z",
        "approved_at": "2026-08-31T12:09:22.760970Z",
        "received_at": "2026-08-31T12:09:22.775271Z",
        "cancelled_at": null,
        "line_count": 1,
        "notes": "",
        "created_at": "2026-08-31T12:09:22.749159Z",
        "updated_at": "2026-08-31T12:09:22.775383Z",
        "lines": [
          {
            "id": 1,
            "product": 1,
            "product_name": "Rice 1kg",
            "product_sku": "",
            "unit": 1,
            "unit_name": "Package",
            "requested_qty": "24.000",
            "approved_qty": "24.000",
            "effective_qty": "24.000",
            "unit_price": "10.00",
            "line_total": "240.00"
          }
        ],
        "estimated_total": "240.00"
      }
    ],
    "pagination": { "count": 2, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

### Quantities: which one to show

| Field | Meaning |
|---|---|
| `requested_qty` | What the rep asked for |
| `approved_qty` | What the admin allowed. **`null` until an admin acts** |
| `effective_qty` | What will actually move — approved if set, else requested |

**Render `effective_qty`.** It is the one that is always correct, and it is what
`line_total` and `estimated_total` are priced on: once an admin trims 24 down to
10, the card's total drops with it. Show `requested_qty` beside it only on a
`modified_by_admin` card, where the difference is the point.

### The money

`unit_price`, `line_total` and `estimated_total` are resolved from the catalog on
read and **never stored** — a transfer carries no money, and this is the shelf
value of the goods, not a charge. A product the catalog cannot price is `null`
and is skipped rather than counted as free, so `estimated_total` can be partial;
`null` means nothing on the transfer could be priced.

---

## 21. The rest of the flow

| Call | When | Effect |
|---|---|---|
| `POST /api/reps/stock-transfers/{id}/confirm/` | status is `pending_rep_confirmation` | Rep accepts the admin's cut quantities → `confirmed` |
| `POST /api/reps/stock-transfers/{id}/reject/` | status is `pending_rep_confirmation` | Rep refuses → `cancelled`, terminal |
| `POST /api/reps/stock-transfers/{id}/receive/` | status is `confirmed` | **Moves the stock.** Company warehouse −, van + → `received` |

`receive` takes an `Idempotency-Key` and must have one: tapping "استلمت" twice on
a flaky connection must not transfer the goods twice.

An illegal transition returns **409**, not 400 — e.g. receiving something still
`pending`. Drive the buttons off `status` rather than letting the rep find out.

After a successful `receive`, the van quantities in `/api/reps/inventory/` and
`/api/reps/products/` reflect the new stock immediately — that is the
`✓ أضيفت لمستودع السيارة` confirmation.

---

## 22. Things that will bite

- **`product_id`, not `product`**, in the request body's lines. The read
  serializers return `product`; the write serializer takes `product_id`.
- **Price the card off `effective_qty`**, not `requested_qty`.
- **`approved_qty` is `null` before an admin acts** — do not render it as 0.
- **`pickup_within_hours` is a promise, not a timer.** Nothing expires. Do not
  show a countdown that implies the request dies.
- **Stock moves only on `receive`.** If the UI shows the van filling up when the
  admin approves, it is lying to the rep.
- **Send an `Idempotency-Key`** on both `create` and `receive`.
- **`van_quantity` is `"0.000"`, `price` can be `null`** — different meanings,
  don't collapse them.
