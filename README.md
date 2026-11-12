# Tawsif Digital: storefront + backend (FastAPI, server-rendered)

## Run locally
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    ADMIN_EMAIL=you@example.com uvicorn app.main:app --reload
Open http://localhost:8000. Register with ADMIN_EMAIL to become admin. With no RESEND_API_KEY the verification link prints in the terminal.

## Free deploy
1. Push to GitHub. Create a free Postgres on Neon or Supabase and copy its URL into DATABASE_URL (free hosts wipe local disks).
2. Deploy the Dockerfile on Render or Koyeb free web service. Set the env vars from .env.example.
3. Uploaded delivery files live in DATA_DIR/files. On free hosts use a persistent disk, or deliver by https link instead of upload.
4. Free-tier services sleep when idle: first visit after a pause is slow. Ping /robots.txt every 10 min with UptimeRobot.

## Lemon Squeezy
- Create a product and variant per item. Paste the variant ID into the product in /studio. Price shown must equal the variant price.
- Settings > Webhooks: URL https://yourdomain/webhooks/lemonsqueezy, events order_created, order_refunded, subscription_created, subscription_updated, subscription_cancelled, subscription_expired, subscription_resumed, subscription_paused, subscription_payment_success, subscription_payment_failed, signing secret = LS_WEBHOOK_SECRET.
- Offers: create a discount code in Lemon Squeezy, then set the same % and code in Admin > Site content.

## Roles
Admin promotes users to seller in Admin > Users and roles. Seller edits go back to "pending" until admin sets "live". Manual bKash/Nagad orders: buyer sees your number and an order code; mark it paid in Admin > Orders.

## Security in place
Argon2 hashing, signed httpOnly session cookies, CSRF tokens on every POST, email verification, rate limits, HMAC-verified idempotent webhooks, role checks server-side, HTML sanitized with nh3, upload type/size limits, files served only to paying owners, CSP and security headers.

## Google login
Google Cloud Console > Credentials > OAuth client (Web). Authorized redirect URI: https://yourdomain/auth/google/callback. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET; the button appears automatically. Free.

## Subscriptions
Renewals, failed payments, cancellations and expiry arrive by webhook. A cancelled subscription keeps access until its paid period ends; expired or refunded orders lose downloads. Buyers get a Manage billing link to Lemon Squeezy's portal. Every payment (first, renewal, manual) is one row in the payments table, which is what seller payouts should be calculated from.

## Tests
    pip install -r requirements-dev.txt && pytest
Existing databases get the new columns automatically at startup.

## Operations
- **Payouts:** Admin > Seller payouts shows each seller's sales, their share (set the percent in Site content), what you've paid and what's due. Pay them yourself, then record it. Refunds reduce what's owed.
- **Manual (bKash/Nagad) subscriptions:** marking a monthly order paid grants 31 days; use Renew +1 month each cycle. Orders lapsing within 7 days are listed in Admin.
- **Emails:** buyers get a receipt with their license key; failed card renewals email the buyer a billing link; sellers get a payout email. Needs RESEND_API_KEY and a verified sending domain.
- **Two-factor:** every user can enable authenticator-app codes in Account. Turn it on for admin first. A code can't be reused.
- **Backups:** `.github/workflows/backup.yml` dumps Postgres daily to a private-repo artifact (30 days). Add DATABASE_URL as a repo secret. Keep the repo private: dumps contain emails. Uploaded files are not in the dump, so keep originals of what you upload.
- **Errors:** set SENTRY_DSN (free tier) for alerts. No personal data is sent.
- **Legal pages:** Terms, Refunds and Privacy start as plain-language templates, not legal advice. Edit them in Admin > Pages before launch.
# TawsifDigital
