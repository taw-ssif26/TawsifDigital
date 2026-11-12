# Digital store: FastAPI, server-rendered, Payoneer payment links

## Run locally
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    ADMIN_EMAIL=you@example.com uvicorn app.main:app --reload
Open http://localhost:8000 and register with ADMIN_EMAIL to become admin. With no RESEND_API_KEY the confirmation link prints in the terminal.
Tests: `pip install -r requirements-dev.txt && pytest`

## How payment works (no payment provider integration, so no webhooks to break)
1. Admin creates a **Payoneer payment request** for a product's price and pastes its link into the product in Studio ("Payoneer payment link"). Optionally set a second link for the offer price. Or set one default link in Admin > Site content.
2. Buyer clicks *Pay with Payoneer*, gets an order page with the amount, the order code and your link, pays, then presses *I've paid* (optionally adding a reference).
3. You get an email and the order shows "says paid" at the top of Admin > Orders. **Check the money in your Payoneer account**, then press *Mark paid*. The buyer gets a receipt with their license key and the product unlocks.
4. Bangladesh buyers also see *Pay with bKash or Nagad* (set the number in Site content). Same flow, and you confirm by hand.
Only the admin can set payment links, so a seller can never redirect money to themselves. Monthly products grant 31 days per confirmation: use *Renew +1 month* each cycle (expiring ones are listed in Admin).
When you run an offer, a Payoneer link has a fixed amount, so give each product an offer link at the discounted price, or buyers will pay the old amount. The order page always shows the amount due; confirm it matches before marking paid.

## Free deploy (Render + Neon)
1. Private GitHub repo. Neon free Postgres: copy the connection string into DATABASE_URL.
2. Render > New Web Service > Docker > Free. Env vars: ENV=production, PORT=8000, SECRET_KEY, BASE_URL, ADMIN_EMAIL, DATABASE_URL (see .env.example). Health check path /robots.txt.
3. Free web services sleep after ~15 minutes idle: add an UptimeRobot monitor on /robots.txt, or move to the $7 instance.
4. Product images are stored in the database. Delivery files uploaded in Studio sit on the server disk, which free hosts erase: use the delivery link field instead (a private cloud-storage link).
5. Register with ADMIN_EMAIL, turn on two-factor in Account, edit Site content, delete the demo products.
Existing databases get new columns and lose the old Lemon Squeezy columns automatically at startup (old SQLite files: delete the .db and start fresh).

## Other settings
- Email: RESEND_API_KEY and MAIL_FROM (needs a verified domain). Receipts, claim alerts, payout notices, resend-verification.
- Google login: OAuth Web client, redirect URI BASE_URL/auth/google/callback, set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (move the consent screen to production).
- Sellers: admin promotes users in Admin > Users and roles. Seller edits go back to "pending". Admin > Seller payouts tracks what each seller is owed (share % in Site content); you pay them yourself and record it.
- Backups: .github/workflows/backup.yml dumps Postgres daily (private repo only; secret DATABASE_URL, use Neon's direct connection string).
- Errors: SENTRY_DSN (optional, no personal data sent).
- Legal pages start as templates, not legal advice: edit them in Admin > Pages.

## Themes
Light (stone and ink, brass accents, faint dust), Dark (charcoal and emerald, champagne motes), Effects (jewel tones with a particle constellation that reacts to the cursor, aurora, tilt, magnetic buttons, scroll progress, page curtains). All respect reduced-motion.
