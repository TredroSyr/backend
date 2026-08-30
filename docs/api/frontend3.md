# Invoice Permissions, List Filtering & Automatic Rep Warehouses

Third companion to [frontend.md](frontend.md) and [frontend2.md](frontend2.md).
Those two describe the invoicing module as it stands; this one covers three
changes made on top of them:

1. **The five invoice permission modules collapsed into one.** This is the only
   change here that can break an existing screen — read Part A before shipping.
2. **`customer` and `rep` filters across every invoice list**, admin and rep side.
3. **A rep gets their warehouse automatically** when the company creates them.

> Conventions — base URL, JWT auth, the `{success, message, data}` envelope,
> pagination, idempotency and error shapes — are unchanged. See frontend.md §2–§6.

---

## 0. What changed

| Change | Impact on the client |
|---|---|
| `incoming_invoices`, `sales_invoices`, `return_invoices`, `payment_collections`, `customer_credits` replaced by a single **`invoices`** module | **Breaking.** Any code reading `permissions["sales_invoices"]` now reads `undefined`. Replace all five with `permissions["invoices"]`. |
| `GET /api/modules` returns 10 entries instead of 14 | The role editor rebuilds itself from this list, so it picks the change up for free — but drop any hardcoded copy of the old keys. |
| `customer` added to 8 invoice list endpoints, `rep` added to 3 | "All invoices for this customer" and "all invoices for this rep" no longer need client-side filtering across pages. |
| `POST /api/companies/reps/` also creates the rep's warehouse | The "create a warehouse for the new rep" step disappears from the rep-creation flow. A new rep can sell immediately. |

No response body changed shape, no field changed type, and no field was removed
from a document. The only breaking surface is the permission map.

---

# Part A — One `invoices` permission

## 1. What changed

frontend.md §6 gave every invoicing document type its own permission module, so a
role could hold sales invoices without returns. That split was never used in
practice and made role editing tedious: granting "this person handles invoicing"
meant ticking five boxes that were always ticked together.

They are now one module: **`invoices`**.

| Old module key | Now |
|---|---|
| `incoming_invoices` | `invoices` |
| `sales_invoices` | `invoices` |
| `return_invoices` | `invoices` |
| `payment_collections` | `invoices` |
| `customer_credits` | `invoices` |

`invoices` gates all of:

- `/api/companies/incoming-invoices/`
- `/api/companies/sales-invoices/` — including `POST {id}/payments/`
- `/api/companies/return-invoices/`
- `/api/companies/payment-collections/`
- `/api/companies/customer-credits/`

`reports` and `settings` are untouched and still gate
`/api/companies/reports/...` and `/api/companies/invoice-settings/`
respectively.

**The crossover note in frontend.md §6 no longer applies.** Recording a payment
and reading the payment ledger were previously two different modules; both are
now `invoices` — `can_action` to record, `can_view` to read.

**Orders were not merged.** `stock_transfers` and `customer_requests` stay
separate modules. They are granted to different people than invoicing, which was
the original reason for splitting anything at all.

## 2. The catalog — `GET /api/modules`

Unchanged endpoint, shorter list. This is the complete current response:

```json
{
  "success": true,
  "message": "",
  "data": {
    "modules": [
      { "value": "products",          "label": "المنتجات",      "label_en": "Products" },
      { "value": "customers",         "label": "العملاء",        "label_en": "Customers" },
      { "value": "reps",              "label": "المندوبين",      "label_en": "Representatives" },
      { "value": "invoices",          "label": "الفواتير",       "label_en": "Invoices" },
      { "value": "stock_transfers",   "label": "طلبات البضاعة",  "label_en": "Stock transfers" },
      { "value": "customer_requests", "label": "طلبات العملاء",  "label_en": "Customer requests" },
      { "value": "notifications",     "label": "الإشعارات",      "label_en": "Notifications" },
      { "value": "reports",           "label": "التقارير",       "label_en": "Reports" },
      { "value": "billing",           "label": "الاشتراك",       "label_en": "Billing" },
      { "value": "settings",          "label": "الإعدادات",      "label_en": "Settings" }
    ]
  }
}
```

Build the role editor from this response rather than a hardcoded list, and the
next catalog change costs you nothing.

## 3. What the permission map looks like now

`data.user.permissions` in the signin response. An **owner**:

```json
{
  "products":          { "can_view": true, "can_action": true },
  "customers":         { "can_view": true, "can_action": true },
  "reps":              { "can_view": true, "can_action": true },
  "invoices":          { "can_view": true, "can_action": true },
  "stock_transfers":   { "can_view": true, "can_action": true },
  "customer_requests": { "can_view": true, "can_action": true },
  "notifications":     { "can_view": true, "can_action": true },
  "reports":           { "can_view": true, "can_action": true },
  "billing":           { "can_view": true, "can_action": true },
  "settings":          { "can_view": true, "can_action": true },
  "orders":            { "can_view": true, "can_action": true }
}
```

A **staff member** whose role holds `invoices` (view + action) and the legacy
`orders` (view only):

```json
{
  "invoices":          { "can_view": true, "can_action": true },
  "orders":            { "can_view": true, "can_action": false },
  "stock_transfers":   { "can_view": true, "can_action": false },
  "customer_requests": { "can_view": true, "can_action": false }
}
```

Two things to read off that:

- **A module the role does not hold is simply absent.** It is not `false`. Treat
  a missing key as "no access" — `permissions[key]?.can_view === true`, not
  `permissions[key].can_view`.
- **`orders` still appears.** It is a legacy key kept alive for older dashboards:
  a role holding it is expanded to `stock_transfers` + `customer_requests`, and
  the old key is kept in the map alongside them. It is deliberately *not* offered
  by `GET /api/modules` — do not assign it to new roles, but do not be surprised
  to see it.

There is no equivalent legacy key for invoices, because `invoices` is a live
catalog key again in its own right.

## 4. Existing roles are unaffected

The five granular keys were never assignable through the API — the role
serializer rejected them, so no stored role can be holding one. Nothing needs
migrating and no user loses access.

As a side effect of the same fix, three keys that were *wrongly* rejected are now
accepted when creating or updating a role: `settings`, `reports` and `billing`.
If your role editor hid them because the API rejected them with a 400, you can
show them.

## 5. Client migration

1. Search the codebase for the five old keys and replace each with `"invoices"`.
   Five separate guards around one screen usually collapse into one.
2. Delete any hardcoded module list; render the role editor from
   `GET /api/modules`.
3. Check every permission read handles a missing key.

---

# Part B — `customer` and `rep` filters

## 6. The complete filter table

New parameters are in **bold**. Everything else already existed and is listed so
you have one table to work from.

| Endpoint | Filters |
|---|---|
| `GET /companies/incoming-invoices/` | `status`, `warehouse`, `search` |
| `GET /companies/sales-invoices/` | `status`, `rep`, `customer`, `outstanding=true`, `date_from`, `date_to`, `search` |
| `GET /reps/sales-invoices/` | `status`, **`customer`**, `outstanding=true`, `date_from`, `date_to`, `search` |
| `GET /companies/return-invoices/` | `status`, `rep`, **`customer`**, `sales_invoice`, `search` |
| `GET /reps/return-invoices/` | `status`, **`customer`**, `sales_invoice` |
| `GET /companies/payment-collections/` | **`rep`**, **`customer`**, `sales_invoice`, `source`, `date_from`, `date_to` |
| `GET /reps/payments/` | **`customer`**, `sales_invoice`, `source`, `date_from`, `date_to` |
| `GET /companies/customer-credits/` | `status`, `customer`, **`rep`** |
| `GET /reps/customer-credits/` | `status`, `customer`, **`rep`** |

All values are ids (`customer=12`, `rep=3`). Filters combine with AND. An empty
or absent parameter is ignored, so `?customer=` is the same as sending nothing.
Ordering and pagination are unchanged.

Incoming invoices take neither: they are supplier documents with no customer and
no rep.

## 7. What `customer` and `rep` mean per document

Only sales invoices carry both columns directly. The rest inherit them, and the
inherited meaning is not always the obvious one:

| Endpoint | `customer` resolves through | `rep` resolves through |
|---|---|---|
| Sales invoices | the invoice's own `customer` | the invoice's own `rep` — the seller |
| Return invoices | **the sale being credited** | the return's own `rep` |
| Payment collections | **the paid invoice's customer** | **`collected_by` — who took the money, not who sold** |
| Customer credits | the credit's own `customer` | **the rep on the return that raised the credit** |

The payments one is the trap. A payment recorded by an admin at the office has
`collected_by: null`, so it belongs to no rep and `?rep=<anyone>` will not return
it — even though the invoice it pays was sold by a rep. `rep` on this endpoint
answers "what did this rep collect", which is the settlement question; it does
not answer "what came in against this rep's sales".

Company-direct documents have a `null` rep throughout (frontend2.md §0), so a
`rep` filter never returns them. To list them you need the unfiltered list.

## 8. Rep-side lists are scoped first, then filtered

`/api/reps/...` lists are already restricted to the authenticated rep. The
`customer` filter narrows that set; it cannot widen it. Asking for another rep's
customer returns an empty list, not that rep's rows:

```
GET /api/reps/sales-invoices/?customer=99   →  { "invoices": [], ... }
```

Two rep endpoints are deliberately **not** rep-scoped:

- `GET /reps/customer-credits/` is company-wide by design — a rep must be able to
  check any customer's pending credit before invoicing them (frontend.md §3.7).
- `GET /reps/payments/` is scoped by `collected_by`, not by who sold. A rep sees
  what they collected, which may include a payment against another rep's invoice.

## 9. Examples

One customer's invoices from one rep, in a single call:

```
GET /api/companies/sales-invoices/?customer=1&rep=1
```

```json
{
  "success": true,
  "message": "",
  "data": {
    "invoices": [
      {
        "id": 1,
        "number": "INV-SALE-00001",
        "date": "2026-08-30T13:14:23.491970Z",
        "rep": 1,
        "rep_name": "Sami",
        "customer": 1,
        "customer_name": "Abu Ahmad Market",
        "customer_phone": "+963955555555",
        "warehouse": 1,
        "company_name": "Tredro Foods",
        "tax_registration_no": "",
        "currency": "SYP",
        "total_amount": "40.00",
        "paid_amount": "25.00",
        "returned_amount": "0.00",
        "balance_due": "15.00",
        "overage_amount": "0.00",
        "status": "partially_paid",
        "notes": "",
        "created_at": "2026-08-30T13:14:23.493996Z",
        "updated_at": "2026-08-30T13:14:23.529510Z"
      }
    ],
    "pagination": { "count": 1, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

What a rep collected from one customer. Note `total_amount`: it is summed over
the **filtered** set, so it directly answers "how much has this customer paid
this rep".

```
GET /api/companies/payment-collections/?customer=1&rep=1
```

```json
{
  "success": true,
  "message": "",
  "data": {
    "payments": [
      {
        "id": 1,
        "sales_invoice": 1,
        "sales_invoice_number": "INV-SALE-00001",
        "amount": "25.00",
        "collected_by": 1,
        "collected_by_name": "Sami",
        "collected_at": "2026-08-30T13:13:55.393721Z",
        "source": "cash",
        "applied_credit": null,
        "note": "",
        "created_at": "2026-08-30T13:13:55.393989Z"
      }
    ],
    "total_amount": "25.00",
    "pagination": { "count": 1, "page": 1, "page_size": 50, "total_pages": 1 }
  }
}
```

The same holds for `total_amount` on `/reps/payments/` and
`/reps/customer-credits/`: it always reflects the filters you sent.

A customer statement screen is now four parallel calls with the same
`?customer=<id>`: sales invoices, return invoices, payment collections and
customer credits.

---

# Part C — Reps get a warehouse automatically

## 10. What changed

Creating a rep through `POST /api/companies/reps/` now also creates that rep's
warehouse — their van — if they do not already have one.

This closes a real hole. Every field document defaults its warehouse to the rep's
own (frontend2.md §5): a sale deducts from it, a return lands in it, a stock
transfer delivers into it. A rep with no warehouse could therefore do none of
those, and failed with:

```json
{
  "success": false,
  "message": "لا يوجد مستودع مرتبط بهذا المندوب",
  "errors": { "warehouse": ["The rep has no active warehouse."] }
}
```

The only fix was for an admin to notice and create one by hand on a different
screen. Now there is nothing to notice.

## 11. What you get

The request and the response of `POST /api/companies/reps/` are **unchanged** —
the warehouse is not in the payload:

```json
{
  "success": true,
  "message": "تم إضافة المندوب بنجاح",
  "data": {
    "rep": {
      "id": 1,
      "name": "Kamal",
      "phone": "+963933333333",
      "referral_code": "REP-KAMAL",
      "is_active": true,
      "created_at": "2026-08-30T13:13:14.959846Z",
      "updated_at": "2026-08-30T13:13:14.959865Z"
    }
  }
}
```

The warehouse it created shows up on the warehouse endpoints immediately:

```
GET /api/companies/warehouses/?owner_type=rep
```

```json
{
  "success": true,
  "message": "",
  "data": {
    "warehouses": [
      {
        "id": 1,
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

It is named `مستودع <rep name>`, is active, and has empty `address` and `kind`.
It is an ordinary warehouse row — rename it, give it an address, or deactivate it
through `PATCH /api/companies/warehouses/{id}/` like any other.

## 12. The rules

**Only on create.** Updating a rep creates nothing. Neither does re-activating
one.

**Never a second van.** If the rep already has a warehouse, none is created. That
includes an **inactive** one: a deactivated van was deactivated on purpose, and
minting a replacement would work around that decision. Such a rep still cannot
sell until the warehouse is re-activated — intended behaviour, not a regression.

**Same transaction as the rep.** A rejected request (duplicate phone, duplicate
referral code) creates neither the rep nor a warehouse. There are no orphans.

**Reps created before this change still have no warehouse.** Nothing was
backfilled. If you see the "no active warehouse" error above on an existing rep,
that is why — create one for them through `POST /api/companies/warehouses/` with
`owner_type: "rep"` and their `rep` id.

## 13. What the client should do

- Drop the "now create a warehouse" step from the new-rep flow.
- Keep the warehouse-creation screen. It is still how you give a rep a second
  van, fix a name, or fill the gap for a rep created before this change.
- Do not assume a rep has exactly one warehouse. The defaults always pick their
  **oldest active** one (frontend2.md §4).

---

## 14. Client checklist

- [ ] Replace `incoming_invoices` / `sales_invoices` / `return_invoices` /
      `payment_collections` / `customer_credits` with `invoices` everywhere.
- [ ] Read permissions defensively: a missing key means no access, not `false`.
- [ ] Render the role editor from `GET /api/modules`, not a hardcoded list.
- [ ] Do not offer `orders` for new roles, but tolerate it in the permission map.
- [ ] Move customer/rep filtering off the client and onto the query string —
      client-side filtering only ever saw the current page.
- [ ] On payment lists, label the `rep` filter "collected by", not "sold by".
- [ ] Remember `total_amount` on payment and credit lists follows the filters.
- [ ] Remove the manual warehouse step from rep creation.
- [ ] Keep handling `"لا يوجد مستودع مرتبط بهذا المندوب"` — reps created before
      this change can still hit it.
