# Digital store: FastAPI, server-rendered, Payoneer payment links

## Run locally
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    ADMIN_EMAIL=you@example.com uvicorn app.main:app --reload
Open http://localhost:8000 and register with ADMIN_EMAIL to become admin. With no BREVO_API_KEY the confirmation link prints in the terminal.
Tests: `pip install -r requirements-dev.txt && pytest`

## How payment works (no payment provider integration, so no webhooks to break)
1. Admin creates a **Payoneer payment request** for a product's price and pastes its link into the product in Studio ("Payoneer payment link"). Optionally set a second link for the offer price. Or set one default link in Admin > Site content.
2. Buyer clicks *Pay with Payoneer*, gets an order page with the amount, the order code and your link, pays, then presses *I've paid* (optionally adding a reference).
3. You get an email and the order shows "says paid" at the top of Admin > Orders. **Check the money in your Payoneer account**, then press *Mark paid*. The buyer gets a receipt with their license key and the product unlocks.
4. Bangladesh buyers also see *Pay with bKash or Nagad* (set the number in Site content). Same flow, and you confirm by hand.
Only the admin can set payment links, so a seller can never redirect money to themselves. Monthly products grant 31 days per confirmation: use *Renew +1 month* each cycle (expiring ones are listed in Admin).
When you run an offer, a Payoneer link has a fixed amount, so give each product an offer link at the discounted price, or buyers will pay the old amount. The order page always shows the amount due; confirm it matches before marking paid.

## Reviews and ratings
- **Product reviews** (1 to 5 stars, headline, text) can only be written by people who actually got the product (a paid order, or a free one). They show a "Verified purchase" label. Products sold on their own website can't be reviewed here.
- **Platform reviews** about the store itself can be written by any signed-in user (on /reviews) and appear on the home page.
- **Nothing is public until you approve it** in Admin > Reviews (pending ones are listed first and counted in the stats). You can approve, reject, delete, and add a public reply. Editing an approved review sends it back to pending. One review per person per target.
- Public names are first name plus last initial, never the email. Approved ratings feed star averages on cards and product pages, the "Top rated" search sort, and (for products only) schema.org review data for Google. Spam protection: hidden honeypot field and 10 reviews per hour.

## Invoices
Every payment above zero (first payment, each monthly renewal, manual bKash/Nagad confirmation) gets its own sequential invoice number, e.g. INV-2026-00007. When you mark an order paid, the buyer's receipt email includes a link to the online invoice and a **PDF attached**. Buyers see all invoices under Account > Invoices (View / print, or PDF). The web invoice has a Print button and clean print styles; refunded orders show a "Refunded" stamp. Free items produce no invoice. Admin > Orders has "Resend invoice". Set your business name, address, email, registration number and footer note in Admin > Site content (they print on every invoice). The PDF uses basic Latin text (non-Latin names appear as "?" in the PDF only; the web invoice shows them correctly). Invoices contain no tax calculation: add the tax wording you need to the footer note, and check your local rules on invoice requirements.

## Search
A search button sits in the header (also press `/` or Ctrl/Cmd+K): a live overlay shows the top matches as you type, with highlighted words, price and cover, arrow-key and Enter navigation, and a link to the full `/search` page (sort by best match, newest or price; filter by type). Every word must match; titles rank highest, then type, summary and the description text. Misspellings are rescued ("autpilot" finds Autopilot), and when nothing matches it offers the custom-work form. Only live products are searched, no-JS visitors get the full page, results pages are `noindex`, the API is rate limited, and the home page declares a SearchAction for search engines. It scans live products in memory, which is instant up to a few thousand products.

## Custom work requests
Customers (signed in, so you can reach them) send a request at **/request**: title, type, description, optional budget, deadline and contact. You get an email, and it appears at the top of Admin > Custom requests (newest unhandled first, counted in the stats). Open one to chat with the customer (each message emails the other side), set a status, enter a quote and a Payoneer link for that quote, and keep a private note the customer never sees. Saving with a changed status or quote emails the customer. They accept or decline the quote with one click, and only after accepting do they see your Payoneer link. Customers can cancel before a quote is accepted. The page text and an on/off switch ("Accepting custom requests") are in Admin > Site content. Spam protection: account required, a hidden honeypot field, and 5 requests per hour per visitor. Custom-work income is not counted in the Admin revenue figure (that tracks shop orders only).

## Free products
Set a product's price to 0 and it becomes free for anyone with a verified account: the button reads "Get it free", there is no payment link, no order to approve and no license key, and it goes straight into the buyer's library. Visitors without an account are sent to register. Free products never lapse, even if set to monthly, and they don't count toward revenue or seller payouts. (A product sold on its own website with price 0 is not free here: it simply hides the price.)

## Products sold on their own website
In Studio, an admin can set **"Sold on its own website"** on any product. The product keeps its page here (description, cover, SEO, structured data), but the button becomes "Buy on theirsite.com" and sends the buyer straight there. Nothing is charged here, no order is created, and our offers and Payoneer/bKash options are hidden for it. Leave the price at 0 to hide the price. Only the admin can set this, so a seller can't send buyers (and their money) off-site. Sales on those sites don't appear in Admin or in seller payouts.

## Free deploy (Render + Neon)
1. Private GitHub repo. Neon free Postgres: copy the connection string into DATABASE_URL.
2. Render > New Web Service > Docker > Free. Env vars: ENV=production, PORT=8000, SECRET_KEY, BASE_URL, ADMIN_EMAIL, DATABASE_URL (see .env.example). Health check path /robots.txt.
3. Free web services sleep after ~15 minutes idle: add an UptimeRobot monitor on /robots.txt, or move to the $7 instance.
4. Product images are stored in the database. Delivery files uploaded in Studio sit on the server disk, which free hosts erase: use the delivery link field instead (a private cloud-storage link).
5. Register with ADMIN_EMAIL, turn on two-factor in Account, edit Site content, delete the demo products.
Existing databases get new columns and lose the old Lemon Squeezy columns automatically at startup (old SQLite files: delete the .db and start fresh).

## Other settings
- Email (Brevo): create an API key (Settings > SMTP & API), verify your sender address or domain in Brevo, then set BREVO_API_KEY and MAIL_FROM="Your Store <you@yourdomain.com>". Without a verified sender Brevo rejects the mail. The free plan has a daily send limit, so check its current size. Receipts, claim alerts, payout notices, resend-verification.
- Google login: OAuth Web client, redirect URI BASE_URL/auth/google/callback, set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (move the consent screen to production).
- Sellers: admin promotes users in Admin > Users and roles. Seller edits go back to "pending". Admin > Seller payouts tracks what each seller is owed (share % in Site content); you pay them yourself and record it.
- Backups: .github/workflows/backup.yml dumps Postgres daily (private repo only; secret DATABASE_URL, use Neon's direct connection string).
- Errors: SENTRY_DSN (optional, no personal data sent).
- Legal pages start as templates, not legal advice: edit them in Admin > Pages.

## Themes
Light (stone and ink, brass accents, faint dust), Dark (charcoal and emerald, champagne motes), Effects (jewel tones with a particle constellation that reacts to the cursor, aurora, tilt, magnetic buttons, scroll progress, page curtains). All respect reduced-motion.
