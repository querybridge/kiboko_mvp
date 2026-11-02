# Stripe setup for Kiboko

What to do in Stripe (and Django admin) to turn on billing. The code is already
wired; nothing charges until the steps below are done.

## How billing works

- A new customer asks for a trial code on Get Started, which we email through
  SendGrid. Redeeming it starts a **45-day free trial with no card**.
- During or after the trial, the org admin clicks **Add payment method** on the
  Billing page. That opens **Stripe Checkout** (Stripe's hosted page) for a monthly
  subscription. The Stripe trial is set to end on the same day as the Kiboko
  trial, so **no charge happens before the 45 days are up**.
- After that, **Manage payment & invoices** opens the **Stripe Customer Portal**
  (change card, see invoices, cancel).
- A **webhook** keeps Kiboko in step with Stripe: paid means the account stays open,
  and a failed payment means the account is locked until payment is fixed.
- If the trial ends with no payment, the org is locked: admins go to Billing, and
  everyone else sees a "contact your admin" page.
- Superusers (e.g. `method`) and orgs ticked **Comped** in admin are never locked.
  Use Comped for demo, sales, and internal accounts.

## 1. Start in a sandbox

Do all of this in a **Stripe sandbox** first (Dashboard, account menu, then
Sandboxes). A sandbox is a separate test environment with its own keys and data,
so nothing touches live money. Repeat the steps in live mode when you launch.

## 2. Create the products and prices

Create **one Product per plan**, each with one **recurring monthly Price** in USD.
Keep the amounts the same as the Plans in Django admin, since that's what the
pricing table shows.

| Product name | Monthly price | Kiboko plan (admin) |
|---|---|---|
| Kiboko Standard | $299 | `standard` |
| Kiboko Premium | $599 | `premium` |
| Kiboko Enterprise | $899 | `enterprise` |
| Premium Connection (add-on) | $150 | `premium-connection` |

Copy each Price id (starts with `price_`). The Premium Connection add-on is only
charged with Standard; Premium and Enterprise include it.

## 3. Create an API key

Developers, then API keys. Stripe recommends a **restricted key** (`rk_...`) over
the full secret key (`sk_...`). Give it **Write** access to:

- Customers
- Checkout Sessions
- Subscriptions
- Customer portal (Billing portal sessions)

Everything else can stay **None**. Also copy the **publishable key** (`pk_...`).

## 4. Add the webhook endpoint

Developers, then Webhooks, then Add endpoint.

- **URL:** `https://<your Kiboko address>/billing/stripe/webhook/`
  (for the PythonAnywhere site, likely `https://kiboko.pythonanywhere.com/billing/stripe/webhook/`)
- **Events to send:**
  - `checkout.session.completed`
  - `checkout.session.async_payment_succeeded`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.paid`
  - `invoice.payment_failed`
  - `charge.dispute.created`
  - `charge.refunded`
  - `radar.early_fraud_warning.created`

Copy the endpoint's **Signing secret** (`whsec_...`).

## 5. Turn on the Customer Portal

Settings, then Billing, then Customer portal. Turn it on and allow:

- Update payment methods
- View invoice history
- Cancel subscriptions (your choice: at period end is the gentler option)

Set the default return link to `https://<your Kiboko address>/app/billing/`.

## 6. Branding and receipts

- Settings, then Branding: logo, colors, and the business name customers see on
  Checkout and receipts.
- Settings, then Customer emails: turn on receipts for successful payments and
  refunds, and failed-payment emails.
- Settings, then Billing, then Subscriptions and emails: set up retries for failed
  payments (Smart Retries is fine) and what happens after the final retry.

## 7. Sales tax (decide before going live)

Stripe Tax is **not** turned on in Kiboko yet. If you'll charge US states or EU
customers that require it, set up your tax registrations in Stripe (Tax, then
Registrations) first. Then tell Claude to turn on automatic tax in Checkout.
Turning it on without a registration collects nothing.

## 8. Paste the values into Django admin

1. **Integration Settings:** Stripe secret key (the `rk_` key), publishable key,
   and webhook signing secret. Also set **App URL** to the Kiboko address.
2. **Plans:** paste each plan's `price_...` id into **Stripe price id** (and the
   product id if you like).

Until both are done, the Billing page says online payment isn't available yet.

## 9. Test it end to end (sandbox)

1. On Get Started, request a trial code, then sign up with it.
2. Log in as that new org admin, go to Billing, and click **Add payment method**.
3. Pay with test card `4242 4242 4242 4242`, any future expiry, any CVC.
4. Back on Billing, it should say a payment method is on file, with the first
   charge on the trial end date.
5. In Stripe, check the customer, subscription (status Trialing), and that the
   webhook deliveries succeeded.
6. Failed payment: in the Customer Portal (Manage payment & invoices), switch the
   card to `4000 0000 0000 0341` (it saves, then every charge fails). In Stripe,
   open the subscription and end the trial now. The charge fails, and Kiboko
   should lock the org until the card is updated.
7. Expired trial without payment: in admin, set an org's **Trial ends** to
   yesterday. Its admin should be sent to Billing on every page.

## 10. Go live

Repeat steps 2 to 6 in live mode (products, prices, key, webhook, portal,
branding), paste the live values into admin, and run one real low-risk test.
Review Stripe's go-live checklist:
https://docs.stripe.com/get-started/checklist/go-live

## Not handled in Kiboko yet

- **Disputes, refunds, fraud warnings:** the webhook logs them only. Review them
  in the Stripe Dashboard.
- **Plan changes:** an org admin can't switch plans in-app yet. Change the
  subscription in Stripe and the org's plan in admin.
- **Keys at rest:** API keys are stored unencrypted in the database (on the
  to-do list).
