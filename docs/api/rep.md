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

**`الفواتير`** — rows come from `SalesInvoiceSerializer` (see §3). The badge maps
from `status`:

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
