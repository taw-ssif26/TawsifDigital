import os, hmac, hashlib, json, secrets, time, re, uuid, base64, struct
import html as _html
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import io
from urllib.parse import urlencode
from pathlib import Path
import httpx, nh3
from PIL import Image
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import RedirectResponse, FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy import create_engine, select, func, inspect, text, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship
from starlette.exceptions import HTTPException as HTTPEx
from starlette.middleware.sessions import SessionMiddleware

E = os.environ.get
BASE = E("BASE_URL", "http://localhost:8000").rstrip("/")
PROD = E("ENV") == "production"
SECRET = E("SECRET_KEY") or (None if PROD else "dev-only-secret")
assert SECRET, "SECRET_KEY is required in production"
ROOT = Path(__file__).parent
DATA = Path(E("DATA_DIR", str(ROOT.parent / "data")))
(DATA / "files").mkdir(parents=True, exist_ok=True)
(DATA / "img").mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = 40_000_000
G_ID, G_SECRET = E("GOOGLE_CLIENT_ID"), E("GOOGLE_CLIENT_SECRET")
engine = create_engine((E("DATABASE_URL") or f"sqlite:///{DATA/'app.db'}").replace("postgres://", "postgresql://", 1), pool_pre_ping=True)
ph = PasswordHasher()
ser = URLSafeTimedSerializer(SECRET, salt="verify")
OK_EXT = {".zip", ".pdf", ".docx", ".xlsx", ".pptx", ".json", ".txt", ".md", ".csv", ".png", ".jpg", ".exe", ".msi", ".dmg", ".7z"}
MAX_UP = 100 * 1024 * 1024

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    pw: Mapped[str] = mapped_column(String(255))
    country: Mapped[str] = mapped_column(String(60), default="")
    role: Mapped[str] = mapped_column(String(10), default="buyer")  # buyer | seller | admin
    verified: Mapped[bool] = mapped_column(default=False)
    wants_seller: Mapped[bool] = mapped_column(default=False)
    totp: Mapped[str] = mapped_column(String(32), default="")
    totp_last: Mapped[int] = mapped_column(default=0)
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)
class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(40), default="Download")
    price_cents: Mapped[int] = mapped_column(default=0)
    per: Mapped[str] = mapped_column(String(10), default="")  # "" one-time, or "month"
    pay_link: Mapped[str] = mapped_column(String(500), default="")  # Payoneer payment link, admin only (money must reach the admin)
    external_url: Mapped[str] = mapped_column(String(500), default="")  # product sold on its own website: buyers are sent there (admin only)
    offer_link: Mapped[str] = mapped_column(String(500), default="")  # Payoneer link for the discounted price while an offer runs
    file_name: Mapped[str] = mapped_column(String(255), default="")
    link: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(10), default="pending")  # live | hidden | pending
    image: Mapped[str] = mapped_column(String(80), default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    owner: Mapped["User"] = relationship()
class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    provider: Mapped[str] = mapped_column(String(10))  # payoneer | manual
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | paid | refunded
    amount_cents: Mapped[int] = mapped_column(default=0)
    license: Mapped[str] = mapped_column(String(40), default="")
    note: Mapped[str] = mapped_column(String(200), default="")  # buyer's payment reference
    claimed: Mapped[bool] = mapped_column(default=False)  # buyer says they have paid
    paid_until: Mapped[datetime | None] = mapped_column(nullable=True)  # manual (bKash/Nagad) subscriptions only
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    user: Mapped["User"] = relationship()
    product: Mapped["Product"] = relationship()
class Payment(Base):  # one row per money-in event: first payment, each renewal, manual confirmation. Seller payouts are computed from this.
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    ref: Mapped[str] = mapped_column(String(60), unique=True)
    amount_cents: Mapped[int] = mapped_column(default=0)
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)
class Payout(Base):
    __tablename__ = "payouts"
    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(default=0)
    note: Mapped[str] = mapped_column(String(200), default="")
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)
class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    who: Mapped[str] = mapped_column(String(255))
    what: Mapped[str] = mapped_column(String(300))
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)
class Blob(Base):  # product images live in the database, so they survive free hosts that wipe local disk
    __tablename__ = "blobs"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
class Page(Base):
    __tablename__ = "pages"
    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, default="")

# every key here is editable from /admin
DEF = {
 "site_name": ("Site name", "Tawsif Digital"),
 "hero_title": ("Homepage headline", "Software you buy once and actually own."),
 "hero_sub": ("Homepage subtext", "Source code, automations, templates and tools. Paid, unlocked and in your hands before you close the tab."),
 "cta_text": ("Main button text", "Browse the catalog"),
 "t1_h": ("Point 1 title", "Pay securely with Payoneer"), "t1_p": ("Point 1 text", "Use a secure Payoneer payment link, then tell me once you have paid."),
 "t2_h": ("Point 2 title", "bKash and Nagad for Bangladesh"), "t2_p": ("Point 2 text", "Choose Bangladesh when you register and the local option appears at checkout."),
 "t3_h": ("Point 3 title", "Unlocked after payment"), "t3_p": ("Point 3 text", "Files and keys reach your library only once the payment is verified."),
 "offer_on": ("Offer active (1 = on, 0 = off)", "0"), "offer_text": ("Offer banner text", "Launch week"),
 "offer_pct": ("Offer discount percent", "20"), "offer_ends": ("Offer ends, UTC (like 2026-12-01T00:00:00Z)", ""),
 "pay_default": ("Default Payoneer payment link (used when a product has none)", ""),
 "trust_bar": ("Trust bar items, separated by |", "Unlocked after payment | Yours to keep | Direct support | Pay with Payoneer"),
 "how_title": ("How-it-works headline", "How it works"),
 "cta_title": ("Closing headline", "Ready when you are."), "cta_sub": ("Closing subtext", "Pick a product, pay securely, and it unlocks in your library as soon as I confirm it."),
 "bd_phone": ("bKash / Nagad number", "+880 1XXX-XXXXXX"),
 "seller_share": ("Seller share of each sale, percent (used for payouts)", "80"),
 "seo_desc": ("Default meta description", "Source code, n8n automations, templates and software subscriptions with instant delivery."),
 "footer": ("Footer line", "Built and supported by Tawsif."),
}
PAGES = {"about": ("About", "<p>Tell your story here. Edit this page from the admin dashboard.</p>"),
 "contact": ("Contact", "<p>How to reach you.</p>"),
 "terms": ("Terms", "<p>By buying you receive a personal licence to use what you purchased. Do not resell, share or redistribute files, keys or source code unless the product page says you can.</p><p>Products are delivered to your account once payment is confirmed. Subscriptions renew until you cancel, and you keep access until the period you paid for ends. Products are provided as described, without a guarantee of uninterrupted service.</p><p><i>Starter text, not legal advice. Replace it with your own terms before launch.</i></p>"),
 "refunds": ("Refunds", "<p>Because digital products can be copied the moment they are delivered, sales are generally final. If a product does not work as described, contact me within 7 days of purchase and I will fix it or refund you.</p><p><i>Starter text. Edit it to match your policy.</i></p>"),
 "privacy": ("Privacy", "<p>I store your name, email, country and purchase history so I can deliver what you bought. Payments are made through Payoneer payment links and I never see your card details. Emails are sent through Resend. If you sign in with Google I receive your name and verified email address only.</p><p>I do not sell your data. To see or delete your data, contact me.</p><p><i>Starter text, not legal advice. Review before launch.</i></p>")}

ADDS = {"products": {"image": "VARCHAR(80) DEFAULT ''", "pay_link": "VARCHAR(500) DEFAULT ''", "offer_link": "VARCHAR(500) DEFAULT ''", "external_url": "VARCHAR(500) DEFAULT ''"}, "orders": {"paid_until": "TIMESTAMP", "note": "VARCHAR(200) DEFAULT ''", "claimed": "BOOLEAN DEFAULT FALSE"},
        "users": {"wants_seller": "BOOLEAN DEFAULT FALSE", "totp": "VARCHAR(32) DEFAULT ''", "totp_last": "BIGINT DEFAULT 0"}}
LEGACY = {"products": ["ls_variant"], "orders": ["ls_order_id", "ls_sub_id", "sub_status", "renews_at", "ends_at", "portal_url"]}  # from the removed Lemon Squeezy integration
def migrate():  # adds new columns and drops the old Lemon Squeezy ones on databases created earlier
    insp = inspect(engine)
    with engine.begin() as c:
        for t, cols in ADDS.items():
            have = {x["name"] for x in insp.get_columns(t)}
            for n, ddl in cols.items():
                if n not in have: c.execute(text(f"ALTER TABLE {t} ADD COLUMN {n} {ddl}"))
    for t, cols in LEGACY.items():
        have = {x["name"] for x in inspect(engine).get_columns(t)}
        for n in cols:
            if n in have:
                try:
                    with engine.begin() as c: c.execute(text(f"ALTER TABLE {t} DROP COLUMN {n}"))
                except Exception as e: print(f"[migrate] could not drop {t}.{n}: {e}")  # old SQLite files: delete the .db and start fresh

def init():
    Base.metadata.create_all(engine); migrate()
    with Session(engine) as db:
        have = {s.key for s in db.scalars(select(Setting))}
        for k, (_, v) in DEF.items():
            if k not in have: db.add(Setting(key=k, value=v))
        for s, (t, b) in PAGES.items():
            if not db.get(Page, s): db.add(Page(slug=s, title=t, body=b))
        if not db.scalar(select(func.count(Product.id))):
            for t, s, k, c, per in [("Invoice Autopilot", "n8n workflow pack that reads invoices from email and files them in your sheet.", "Automation", 2900, ""),
                                    ("ClinicDesk source code", "Full clinic management app with admin, doctor and patient panels.", "Source code", 14900, ""),
                                    ("Scrape on demand", "Pay-as-you-go scraping API. Your key is issued once payment clears.", "Subscription", 900, "month")]:
                db.add(Product(slug=slugify(t), title=t, summary=s, body=f"<p>{s}</p>", kind=k, price_cents=c, per=per, status="live"))
        db.commit()

def slugify(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80] or "item"
def fmt(c): return f"${c/100:,.0f}" if c % 100 == 0 else f"${c/100:,.2f}"
def price(p, S):
    try: pct = min(90, max(0, int(S["offer_pct"])))
    except ValueError: pct = 0
    if S["offer_on"] == "1" and pct and p.price_cents and not p.external_url: return p.price_cents * (100 - pct) // 100, p.price_cents
    return p.price_cents, None
def clean(html): return nh3.clean(html or "")

if E("SENTRY_DSN"):
    import sentry_sdk; sentry_sdk.init(dsn=E("SENTRY_DSN"), send_default_pii=False, traces_sample_rate=0)  # error alerts only, no personal data
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET, https_only=PROD, same_site="lax", max_age=14 * 86400)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
T = Jinja2Templates(directory=ROOT / "templates")
init()

@app.middleware("http")
async def headers(request: Request, call_next):
    r = await call_next(request)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
    if PROD: r.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return r

def get_db():
    with Session(engine) as s: yield s
def settings(db): return {**{k: v[1] for k, v in DEF.items()}, **{r.key: r.value for r in db.scalars(select(Setting))}}
def me(request, db):
    uid = request.session.get("uid")
    return db.get(User, uid) if uid else None
def csrf(request: Request, csrf_token: str = Form("")):
    if not hmac.compare_digest(csrf_token, request.session.get("csrf", "-")): raise HTTPEx(403, "Session expired. Reload the page and try again.")
def need(request, db, *roles):
    u = me(request, db)
    if not u: raise HTTPEx(303, headers={"Location": "/login"})
    if roles and u.role not in roles: raise HTTPEx(403, "You don't have access to this page.")
    return u
HITS = defaultdict(list)
def limit(request, key, n=8, secs=300):
    k, now = f"{key}:{request.client.host}", time.time()
    HITS[k] = [t for t in HITS[k] if now - t < secs]
    if len(HITS[k]) >= n: raise HTTPEx(429, "Too many attempts. Try again in a few minutes.")
    HITS[k].append(now)
def flash(request, msg): request.session["flash"] = msg
def go(url): return RedirectResponse(url, 303)
def render(request, db, name, status=200, **ctx):
    S = settings(db)
    request.session.setdefault("csrf", secrets.token_urlsafe(24))
    ctx.update(request=request, S=S, u=me(request, db), csrf=request.session["csrf"], flash=request.session.pop("flash", None), base=BASE,
               fmt=fmt, show=lambda p: price(p, S), access=has_access, google=bool(G_ID), pages=db.scalars(select(Page)).all())
    return T.TemplateResponse(request, name, ctx, status_code=status)
def mail(to, subject, html):
    if not E("RESEND_API_KEY"): print(f"[mail] {to} | {subject}\n{html}"); return
    try: httpx.post("https://api.resend.com/emails", headers={"Authorization": "Bearer " + E("RESEND_API_KEY")}, timeout=10, json={"from": E("MAIL_FROM", "onboarding@resend.dev"), "to": [to], "subject": subject, "html": html})
    except Exception as e: print("[mail failed]", e)  # never let a mail outage break a webhook or a checkout
def send_verify(u): mail(u.email, "Confirm your email", f'<p>Confirm your account: <a href="{BASE}/verify/{ser.dumps(u.id)}">verify email</a>. The link lasts 24 hours.</p>')
def notify_paid(o):
    t = _html.escape(o.product.title)
    mail(o.user.email, f"Your purchase: {o.product.title}", f'<p>Thank you! <b>{t}</b> is ready in your library: <a href="{BASE}/account">open library</a>.</p>' + (f"<p>License key: <b>{o.license}</b></p>" if o.license else "") + (f"<p>Access runs until {o.paid_until:%b %d, %Y}.</p>" if o.paid_until else ""))
def audit(db, u, what): db.add(Audit(who=u.email if u else "system", what=what[:300]))
def share(db):
    try: return min(100, max(0, int(settings(db)["seller_share"])))
    except ValueError: return 80
def balance(db, sid, pct):  # gross comes from real payment rows on non-refunded orders, so refunds claw back automatically
    gross = db.scalar(select(func.coalesce(func.sum(Payment.amount_cents), 0)).join(Order, Order.id == Payment.order_id).join(Product, Product.id == Order.product_id).where(Product.owner_id == sid, Order.status == "paid"))
    out = db.scalar(select(func.coalesce(func.sum(Payout.amount_cents), 0)).where(Payout.seller_id == sid)); owed = gross * pct // 100
    return {"gross": gross, "owed": owed, "paid": out, "due": owed - out}
def totp_code(secret, counter):  # RFC 6238, SHA-1, 6 digits
    h = hmac.new(base64.b32decode(secret), struct.pack(">Q", counter), "sha1").digest(); o = h[-1] & 15
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 10**6:06d}"
def totp_ok(secret, last, code):  # returns the matched counter, never one already used
    now = int(time.time() // 30)
    for c in (now - 1, now, now + 1):
        if c > last and hmac.compare_digest(totp_code(secret, c), (code or "").strip()): return c
def finish_login(request, u):
    request.session.clear()
    if u.totp: request.session["pre"] = u.id; return go("/login/2fa")
    request.session["uid"] = u.id; return go("/admin" if u.role == "admin" else "/account")
def fulfil(o):
    o.status = "paid"
    o.license = o.license or "TS-" + "-".join(secrets.token_hex(2).upper() for _ in range(3))

def has_access(o):
    if o.status != "paid": return False
    if o.product.per: return bool(o.paid_until) and o.paid_until > datetime.utcnow()  # monthly products lapse unless renewed
    return True
def pay_url(p, S):
    if S["offer_on"] == "1" and p.offer_link: return p.offer_link
    return p.pay_link or S["pay_default"]
def record(db, o, ref, cents):
    if not db.scalar(select(Payment.id).where(Payment.ref == ref)): db.add(Payment(order_id=o.id, ref=ref, amount_cents=cents))
def save_image(up, db):
    data = up.file.read(3 * 1024 * 1024 + 1)
    try:
        if len(data) > 3 * 1024 * 1024: raise ValueError
        im = Image.open(io.BytesIO(data)); im.verify(); im = Image.open(io.BytesIO(data))
        if im.format not in ("PNG", "JPEG", "WEBP"): raise ValueError
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB"); im.thumbnail((1600, 1600))
        name = uuid.uuid4().hex + ".webp"; buf = io.BytesIO(); im.save(buf, "WEBP", quality=85)  # re-encoding strips metadata and any payload
        db.add(Blob(name=name, data=buf.getvalue())); return name
    except Exception: raise ValueError("Upload a PNG, JPG or WebP image under 3 MB.")

@app.exception_handler(HTTPEx)
async def err(request: Request, e: HTTPEx):
    if e.status_code == 303: return RedirectResponse(e.headers["Location"], 303)
    with Session(engine) as db: return render(request, db, "error.html", e.status_code, code=e.status_code, msg=e.detail if e.status_code != 404 else "That page doesn't exist.")

# ---------- public ----------
@app.get("/")
def home(request: Request, db=Depends(get_db)):
    ps = db.scalars(select(Product).where(Product.status == "live").order_by(Product.created.desc()).limit(6)).all()
    return render(request, db, "home.html", products=ps)
@app.get("/products")
def products(request: Request, kind: str = "", db=Depends(get_db)):
    q = select(Product).where(Product.status == "live").order_by(Product.created.desc())
    if kind: q = q.where(Product.kind == kind)
    kinds = db.scalars(select(Product.kind).where(Product.status == "live").distinct()).all()
    return render(request, db, "products.html", products=db.scalars(q).all(), kinds=kinds, kind=kind)
@app.get("/p/{slug}")
def product(slug: str, request: Request, db=Depends(get_db)):
    p = db.scalar(select(Product).where(Product.slug == slug))
    u = me(request, db)
    if not p or (p.status != "live" and not (u and (u.role == "admin" or p.owner_id == u.id))): raise HTTPEx(404)
    owned = bool(u and any(has_access(o) for o in db.scalars(select(Order).where(Order.user_id == u.id, Order.product_id == p.id))))
    return render(request, db, "product.html", p=p, owned=owned)
@app.get("/pages/{slug}")
def page(slug: str, request: Request, db=Depends(get_db)):
    pg = db.get(Page, slug)
    if not pg: raise HTTPEx(404)
    return render(request, db, "page.html", pg=pg)

# ---------- auth ----------
@app.get("/register")
def register_form(request: Request, db=Depends(get_db)): return render(request, db, "auth.html", mode="register")
@app.post("/register")
def register(request: Request, db=Depends(get_db), _=Depends(csrf), email: str = Form(), name: str = Form(), password: str = Form(), country: str = Form()):
    limit(request, "reg"); email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(password) < 10 or len(password) > 200:
        flash(request, "Use a valid email and a password of at least 10 characters."); return go("/register")
    if not db.scalar(select(User.id).where(User.email == email)):
        u = User(email=email, name=name.strip()[:120], pw=ph.hash(password), country=country.strip()[:60], role="admin" if email == (E("ADMIN_EMAIL") or "").lower() else "buyer")
        db.add(u); db.commit()
        send_verify(u)
    flash(request, "Check your inbox for a confirmation link."); return go("/login")
@app.get("/verify/{token}")
def verify(token: str, request: Request, db=Depends(get_db)):
    try: u = db.get(User, ser.loads(token, max_age=86400))
    except BadSignature: raise HTTPEx(400, "This link is invalid or has expired. Register again to get a new one.")
    if u: u.verified = True; db.commit()
    flash(request, "Email confirmed. You can sign in."); return go("/login")
@app.get("/login")
def login_form(request: Request, db=Depends(get_db)): return render(request, db, "auth.html", mode="login")
@app.post("/login")
def login(request: Request, db=Depends(get_db), _=Depends(csrf), email: str = Form(), password: str = Form()):
    limit(request, "login", 10); u = db.scalar(select(User).where(User.email == email.strip().lower()))
    try:
        ok = bool(u) and ph.verify(u.pw, password)
    except VerifyMismatchError: ok = False
    if not ok or not u.verified:
        flash(request, "Wrong email or password, or the email isn't confirmed yet."); return go("/login")
    return finish_login(request, u)
@app.post("/logout")
def logout(request: Request, _=Depends(csrf)): request.session.clear(); return go("/")

# ---------- buyer ----------
@app.get("/account")
def account(request: Request, db=Depends(get_db)):
    u = need(request, db)
    return render(request, db, "account.html", new2fa=request.session.get("new2fa"), orders=db.scalars(select(Order).where(Order.user_id == u.id).order_by(Order.created.desc())).all())
@app.post("/account")
def account_save(request: Request, db=Depends(get_db), _=Depends(csrf), name: str = Form(""), country: str = Form("")):
    u = need(request, db); u.name, u.country = name.strip()[:120], country.strip()[:60]; db.commit(); flash(request, "Profile saved."); return go("/account")
@app.post("/buy/{pid}")
def buy(pid: int, request: Request, db=Depends(get_db), _=Depends(csrf), provider: str = Form("payoneer")):
    u = need(request, db); limit(request, "buy", 15); p = db.get(Product, pid); S = settings(db)
    if not p or p.status != "live": raise HTTPEx(404)
    if p.external_url: raise HTTPEx(400, "This product is sold on its own website.")
    if provider not in ("payoneer", "manual"): raise HTTPEx(400, "Unknown payment method.")
    if provider == "manual" and u.country != "Bangladesh": raise HTTPEx(403, "Manual payment is only for buyers in Bangladesh.")
    if provider == "payoneer" and not pay_url(p, S): raise HTTPEx(503, "Payment isn't set up for this product yet. Please contact me.")
    o = db.scalar(select(Order).where(Order.user_id == u.id, Order.product_id == p.id, Order.provider == provider, Order.status == "pending"))
    if not o: o = Order(code=secrets.token_hex(4).upper(), user_id=u.id, product_id=p.id, provider=provider); db.add(o)
    if not o.claimed: o.amount_cents = price(p, S)[0]
    db.commit(); return go(f"/order/{o.code}")
@app.post("/order/{code}/claim")
def claim(code: str, request: Request, db=Depends(get_db), _=Depends(csrf), note: str = Form("")):
    u = need(request, db); limit(request, "claim", 10)
    o = db.scalar(select(Order).where(Order.code == code, Order.user_id == u.id, Order.status == "pending"))
    if not o: raise HTTPEx(404)
    o.claimed, o.note = True, note.strip()[:200]; db.commit()
    if E("ADMIN_EMAIL"): mail(E("ADMIN_EMAIL"), "Payment to confirm", f"<p>{_html.escape(u.email)} says they paid for <b>{_html.escape(o.product.title)}</b> ({fmt(o.amount_cents)}, order {o.code}, via {o.provider}). Reference: {_html.escape(o.note) or 'none'}. Confirm in Admin &gt; Orders.</p>")
    flash(request, "Thanks! I'll check and unlock your product as soon as the payment shows up."); return go(f"/order/{o.code}")
@app.get("/order/{code}")
def order(code: str, request: Request, db=Depends(get_db)):
    u = need(request, db); o = db.scalar(select(Order).where(Order.code == code, Order.user_id == u.id))
    if not o: raise HTTPEx(404)
    return render(request, db, "order.html", o=o, pay=pay_url(o.product, settings(db)) if o.provider == "payoneer" else "")
@app.get("/download/{code}")
def download(code: str, request: Request, db=Depends(get_db)):
    u = need(request, db); o = db.scalar(select(Order).where(Order.code == code, Order.user_id == u.id))
    if not o or not has_access(o): raise HTTPEx(404, "No active access for this order.")
    p = o.product
    if p.file_name and (DATA / "files" / p.file_name).is_file(): return FileResponse(DATA / "files" / p.file_name, filename=p.slug + Path(p.file_name).suffix)
    if p.link: return go(p.link)
    raise HTTPEx(404, "Nothing to download for this product.")

# ---------- seller + admin product studio ----------
@app.get("/studio")
def studio(request: Request, db=Depends(get_db)):
    u = need(request, db, "seller", "admin")
    q = select(Product).order_by(Product.created.desc())
    if u.role == "seller": q = q.where(Product.owner_id == u.id)
    ps = db.scalars(q).all(); ids = [p.id for p in ps]
    sold = db.execute(select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount_cents), 0)).join(Order, Order.id == Payment.order_id).where(Order.product_id.in_(ids), Order.status == "paid")).one() if ids else (0, 0)
    return render(request, db, "studio.html", products=ps, sold=sold, bal=balance(db, u.id, share(db)))
@app.get("/studio/edit")
def studio_edit(request: Request, id: int = 0, db=Depends(get_db)):
    u = need(request, db, "seller", "admin"); p = db.get(Product, id) if id else None
    if id and (not p or (u.role == "seller" and p.owner_id != u.id)): raise HTTPEx(404)
    return render(request, db, "edit.html", p=p)
@app.post("/studio/edit")
def studio_save(request: Request, db=Depends(get_db), _=Depends(csrf), id: int = Form(0), title: str = Form(), summary: str = Form(""), body: str = Form(""), kind: str = Form("Download"),
                price_usd: float = Form(0), per: str = Form(""), link: str = Form(""), pay_link: str = Form(None), offer_link: str = Form(None), external_url: str = Form(None), status: str = Form("pending"), file: UploadFile = File(None), image: UploadFile = File(None)):
    u = need(request, db, "seller", "admin"); p = db.get(Product, id) if id else Product(owner_id=u.id, slug="")
    if id and (not p or (u.role == "seller" and p.owner_id != u.id)): raise HTTPEx(404)
    p.title, p.summary, p.body, p.kind = title.strip()[:160], summary.strip()[:300], clean(body), kind.strip()[:40]
    p.price_cents, p.per = max(0, round(price_usd * 100)), ("month" if per == "month" else "")
    if link and not link.startswith("https://"): flash(request, "Product links must start with https://"); return go(f"/studio/edit?id={id}")
    p.link = link.strip()[:500]
    if u.role == "admin":  # only the admin may set where customers pay; a seller can never redirect money
        for attr, val in (("pay_link", pay_link), ("offer_link", offer_link), ("external_url", external_url)):
            if val is None: continue
            val = val.strip()[:500]
            if val and not val.startswith("https://"): flash(request, "Links must start with https://"); return go(f"/studio/edit?id={id}")
            setattr(p, attr, val)
    if u.role == "admin" and status in ("live", "hidden", "pending"): p.status = status
    elif u.role == "seller": p.status = "pending"  # every seller change needs re-approval
    if not p.slug:
        base_s = slugify(p.title); p.slug = base_s + ("-" + secrets.token_hex(2) if db.scalar(select(Product.id).where(Product.slug == base_s)) else "")
    if file and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in OK_EXT: flash(request, "That file type isn't allowed. Zip it first."); return go(f"/studio/edit?id={id}")
        name, size = uuid.uuid4().hex + ext, 0
        with open(DATA / "files" / name, "wb") as f:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UP: f.close(); (DATA / "files" / name).unlink(); flash(request, "File is over 100 MB."); return go(f"/studio/edit?id={id}")
                f.write(chunk)
        p.file_name = name
    if image and image.filename:
        try: new_img = save_image(image, db)
        except ValueError as e: flash(request, str(e)); return go(f"/studio/edit?id={id}")
        if p.image: db.query(Blob).filter_by(name=p.image).delete()
        p.image = new_img
    db.add(p); audit(db, u, f"{'Edited' if id else 'Created'} product {p.title} ({p.status})"); db.commit(); flash(request, "Saved." if u.role == "admin" else "Saved. It goes live after admin approval."); return go("/studio")

# ---------- admin ----------
@app.get("/admin")
def admin(request: Request, db=Depends(get_db)):
    need(request, db, "admin")
    paid = db.execute(select(func.count(Payment.id), func.coalesce(func.sum(Payment.amount_cents), 0)).join(Order, Order.id == Payment.order_id).where(Order.status == "paid")).one()
    sh = share(db); now = datetime.utcnow()
    sellers = db.scalars(select(User).where(User.role != "admin", (User.role == "seller") | User.id.in_(select(Product.owner_id).where(Product.owner_id.is_not(None))))).all()
    bals = [(x, balance(db, x.id, sh)) for x in sellers]
    expiring = db.scalars(select(Order).where(Order.status == "paid", Order.paid_until.is_not(None), Order.paid_until < now + timedelta(days=7)).order_by(Order.paid_until)).all()
    log = db.scalars(select(Audit).order_by(Audit.id.desc()).limit(40)).all()
    claims = db.scalar(select(func.count(Order.id)).where(Order.status == "pending", Order.claimed == True))  # noqa: E712
    return render(request, db, "admin.html", DEF=DEF, paid=paid, bals=bals, sh=sh, expiring=expiring, log=log, claims=claims, users=db.scalars(select(User).order_by(User.created.desc())).all(),
                  orders=db.scalars(select(Order).order_by(Order.status != "pending", Order.claimed.desc(), Order.created.desc()).limit(60)).all(), pending=db.scalar(select(func.count(Product.id)).where(Product.status == "pending")))
@app.post("/admin/settings")
async def admin_settings(request: Request, db=Depends(get_db)):
    adm = need(request, db, "admin"); f = await request.form(); csrf(request, f.get("csrf_token", ""))
    for k in DEF:
        if k in f: db.merge(Setting(key=k, value=str(f[k])[:2000]))
    audit(db, adm, "Edited site content"); db.commit(); flash(request, "Site content saved."); return go("/admin")
@app.post("/admin/page")
def admin_page(request: Request, db=Depends(get_db), _=Depends(csrf), slug: str = Form(), title: str = Form(), body: str = Form(""), delete: str = Form("")):
    adm = need(request, db, "admin"); slug = slugify(slug)
    if delete: db.query(Page).filter_by(slug=slug).delete()
    else: db.merge(Page(slug=slug, title=title[:120], body=clean(body)))
    audit(db, adm, f"{'Deleted' if delete else 'Saved'} page {slug}"); db.commit(); flash(request, "Page saved."); return go("/admin")
@app.post("/admin/order/{oid}")
def admin_order(oid: int, request: Request, db=Depends(get_db), _=Depends(csrf), action: str = Form()):
    adm = need(request, db, "admin"); o = db.get(Order, oid)
    if not o: raise HTTPEx(404)
    nxt = lambda: max(datetime.utcnow(), o.paid_until or datetime.utcnow()) + timedelta(days=31); fresh = False
    if action == "paid" and o.status != "paid":
        fulfil(o); db.flush(); fresh = True
        if not db.scalar(select(Payment.id).where(Payment.order_id == o.id)): record(db, o, "manual-" + o.code, o.amount_cents)
        if o.product.per: o.paid_until = nxt()
    elif action == "renew" and o.status == "paid" and o.product.per:
        o.paid_until = nxt(); db.flush(); record(db, o, f"manual-{o.code}-{int(time.time())}", o.amount_cents); fresh = True
    elif action == "refunded": o.status = "refunded"
    audit(db, adm, f"Order {o.code}: {action}"); db.commit()
    if fresh: notify_paid(o)
    flash(request, f"Order {o.code} updated."); return go("/admin")
@app.post("/admin/payout")
def admin_payout(request: Request, db=Depends(get_db), _=Depends(csrf), seller_id: int = Form(), amount_usd: float = Form(), note: str = Form("")):
    adm = need(request, db, "admin"); sl = db.get(User, seller_id); c = round(amount_usd * 100)
    if not sl or c <= 0: flash(request, "Enter a payout amount above zero."); return go("/admin")
    db.add(Payout(seller_id=sl.id, amount_cents=c, note=note[:200])); audit(db, adm, f"Payout {fmt(c)} to {sl.email}"); db.commit()
    mail(sl.email, "Payout sent", f"<p>I've sent you a payout of <b>{fmt(c)}</b>. {_html.escape(note[:200])}</p>"); flash(request, "Payout recorded."); return go("/admin")
@app.post("/admin/user/{uid}")
def admin_user(uid: int, request: Request, db=Depends(get_db), _=Depends(csrf), role: str = Form()):
    a = need(request, db, "admin"); u = db.get(User, uid)
    if u and u.id != a.id and role in ("buyer", "seller", "admin"): u.role = role; u.wants_seller = False; audit(db, a, f"Set {u.email} to {role}"); db.commit()
    flash(request, "Role updated."); return go("/admin")

# ---------- resend, seller applications, two-factor ----------
@app.post("/resend")
def resend(request: Request, db=Depends(get_db), _=Depends(csrf), email: str = Form()):
    limit(request, "resend", 4); u = db.scalar(select(User).where(User.email == email.strip().lower()))
    if u and not u.verified: send_verify(u)
    flash(request, "If that account is waiting for confirmation, a new link is on its way."); return go("/login")
@app.post("/account/apply")
def apply_seller(request: Request, db=Depends(get_db), _=Depends(csrf)):
    u = need(request, db, "buyer"); u.wants_seller = True; db.commit()
    if E("ADMIN_EMAIL"): mail(E("ADMIN_EMAIL"), "Seller application", f"<p>{_html.escape(u.email)} applied to sell. Review in Admin &gt; Users and roles.</p>")
    flash(request, "Application sent. I'll review it soon."); return go("/account")
@app.post("/account/2fa/start")
def tfa_start(request: Request, db=Depends(get_db), _=Depends(csrf)):
    need(request, db); request.session["new2fa"] = base64.b32encode(secrets.token_bytes(20)).decode(); return go("/account")
@app.post("/account/2fa/confirm")
def tfa_confirm(request: Request, db=Depends(get_db), _=Depends(csrf), code: str = Form()):
    u = need(request, db); sec = request.session.get("new2fa"); c = totp_ok(sec, 0, code) if sec else None
    if not c: flash(request, "That code didn't match. Check the key and your phone's clock."); return go("/account")
    u.totp, u.totp_last = sec, c; audit(db, u, "Enabled two-factor"); db.commit(); request.session.pop("new2fa"); flash(request, "Two-factor sign-in is on."); return go("/account")
@app.post("/account/2fa/off")
def tfa_off(request: Request, db=Depends(get_db), _=Depends(csrf), code: str = Form()):
    u = need(request, db); limit(request, "2fa", 8)
    if not u.totp or not totp_ok(u.totp, u.totp_last, code): flash(request, "Wrong code."); return go("/account")
    u.totp = ""; audit(db, u, "Disabled two-factor"); db.commit(); flash(request, "Two-factor sign-in is off."); return go("/account")
@app.get("/login/2fa")
def tfa_form(request: Request, db=Depends(get_db)):
    if not request.session.get("pre"): return go("/login")
    return render(request, db, "login2fa.html")
@app.post("/login/2fa")
def tfa_login(request: Request, db=Depends(get_db), _=Depends(csrf), code: str = Form()):
    limit(request, "2fa", 8); u = db.get(User, request.session.get("pre") or 0); c = totp_ok(u.totp, u.totp_last, code) if u and u.totp else None
    if not c: flash(request, "Wrong or already-used code."); return go("/login/2fa")
    u.totp_last = c; db.commit(); request.session.clear(); request.session["uid"] = u.id
    return go("/admin" if u.role == "admin" else "/account")

# ---------- password reset ----------
rser = URLSafeTimedSerializer(SECRET, salt="reset")
def reset_user(token, db):  # token embeds the tail of the current hash, so it dies the moment the password changes (single use)
    try: uid, tail = rser.loads(token, max_age=3600)
    except (BadSignature, ValueError): raise HTTPEx(400, "This reset link is invalid or has expired.")
    u = db.get(User, uid)
    if not u or u.pw[-12:] != tail: raise HTTPEx(400, "This reset link is invalid or has expired.")
    return u
@app.get("/forgot")
def forgot_form(request: Request, db=Depends(get_db)): return render(request, db, "forgot.html")
@app.post("/forgot")
def forgot(request: Request, db=Depends(get_db), _=Depends(csrf), email: str = Form()):
    limit(request, "forgot", 5); u = db.scalar(select(User).where(User.email == email.strip().lower()))
    if u: mail(u.email, "Reset your password", f'<p><a href="{BASE}/reset/{rser.dumps([u.id, u.pw[-12:]])}">Choose a new password</a>. The link works once and lasts one hour.</p>')
    flash(request, "If that email has an account, a reset link is on its way."); return go("/login")
@app.get("/reset/{token}")
def reset_form(token: str, request: Request, db=Depends(get_db)):
    reset_user(token, db); return render(request, db, "reset.html", token=token)
@app.post("/reset/{token}")
def reset(token: str, request: Request, db=Depends(get_db), _=Depends(csrf), password: str = Form()):
    limit(request, "reset", 10); u = reset_user(token, db)
    if not 10 <= len(password) <= 200: flash(request, "Use a password of at least 10 characters."); return go(f"/reset/{token}")
    u.pw = ph.hash(password); u.verified = True; db.commit(); request.session.clear()
    flash(request, "Password changed. Sign in with the new one."); return go("/login")

# ---------- Google sign-in (OAuth code flow, no extra dependency) ----------
@app.get("/auth/google")
def google_start(request: Request):
    if not G_ID: raise HTTPEx(404)
    st = request.session["gst"] = secrets.token_urlsafe(24)
    return go("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"client_id": G_ID, "redirect_uri": BASE + "/auth/google/callback", "response_type": "code", "scope": "openid email profile", "state": st, "prompt": "select_account"}))
@app.get("/auth/google/callback")
def google_cb(request: Request, code: str = "", state: str = "", db=Depends(get_db)):
    if not G_ID or not code or not hmac.compare_digest(state, request.session.pop("gst", "-")): raise HTTPEx(400, "Google sign-in failed. Please try again.")
    limit(request, "goog", 20)
    try:
        tok = httpx.post("https://oauth2.googleapis.com/token", timeout=10, data={"code": code, "client_id": G_ID, "client_secret": G_SECRET, "redirect_uri": BASE + "/auth/google/callback", "grant_type": "authorization_code"}).json()
        info = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=10, headers={"Authorization": "Bearer " + tok["access_token"]}).json()
    except Exception: raise HTTPEx(502, "Couldn't reach Google. Try again shortly.")
    email = (info.get("email") or "").lower()
    if not email or info.get("email_verified") is not True: raise HTTPEx(400, "Your Google email isn't verified.")
    u = db.scalar(select(User).where(User.email == email))
    if not u: u = User(email=email, name=(info.get("name") or "")[:120], pw=ph.hash(secrets.token_urlsafe(32)), verified=True, role="admin" if email == (E("ADMIN_EMAIL") or "").lower() else "buyer")
    elif not u.verified: u.verified = True; u.pw = ph.hash(secrets.token_urlsafe(32))  # Google proved ownership: wipe any password a squatter set
    db.add(u); db.commit(); r = finish_login(request, u)
    if not u.country and not u.totp: flash(request, "Welcome! Set your country below so the right payment options show.")
    return r

# ---------- product images ----------
@app.get("/img/{name}")
def img(name: str, db=Depends(get_db)):
    b = db.get(Blob, name) if re.fullmatch(r"[0-9a-f]{32}\.webp", name) else None
    if not b: raise HTTPEx(404)
    return Response(b.data, media_type="image/webp", headers={"Cache-Control": "public, max-age=31536000, immutable"})

# ---------- SEO ----------
@app.get("/robots.txt")
def robots():
    ai = "\n".join(f"User-agent: {b}\nAllow: /\n" for b in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"))
    return PlainTextResponse(f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /studio\nDisallow: /account\nDisallow: /buy\nDisallow: /download\n\n{ai}\nSitemap: {BASE}/sitemap.xml\n")
@app.get("/sitemap.xml")
def sitemap(db=Depends(get_db)):
    urls = ["/", "/products"] + [f"/pages/{p.slug}" for p in db.scalars(select(Page))] + [f"/p/{p.slug}" for p in db.scalars(select(Product).where(Product.status == "live"))]
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{BASE}{u}</loc></url>" for u in urls) + "</urlset>", media_type="application/xml")
@app.get("/llms.txt")
def llms(db=Depends(get_db)):
    S = settings(db); ps = db.scalars(select(Product).where(Product.status == "live")).all()
    return PlainTextResponse(f"# {S['site_name']}\n\n> {S['seo_desc']}\n\n## Products\n" + "\n".join(f"- [{p.title}]({BASE}/p/{p.slug}): {p.summary} ({(fmt(price(p, S)[0]) + ('/' + p.per if p.per else '') + ', ') if price(p, S)[0] else ''}{p.kind}{', sold on its own website' if p.external_url else ''})" for p in ps) + "\n")
