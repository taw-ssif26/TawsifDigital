import io, re
from datetime import datetime, timedelta
from PIL import Image
from helpers import *

def iso(days): return (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")

def test_public_pages_and_seo():
    pid, slug = product(); c = C()
    for u in ("/", "/products", f"/p/{slug}", "/pages/about", "/login", "/register"): assert c.get(u).status_code == 200
    assert f"/p/{slug}" in c.get("/sitemap.xml").text and "Sitemap:" in c.get("/robots.txt").text and slug in c.get("/llms.txt").text
    assert '"Product"' in c.get(f"/p/{slug}").text
    assert "frame-ancestors 'none'" in c.get("/").headers["content-security-policy"]

def test_register_verify_login():
    c = C(); r = c.form("/register", email="new@t.com", name="N", password="longpassword1", country="Bangladesh"); assert r.status_code == 303
    assert c.form("/login", email="new@t.com", password="longpassword1").status_code == 303 and c.get("/account").status_code == 303  # unverified cannot sign in
    with m.Session(m.engine) as db: uid = db.scalar(m.select(m.User.id).where(m.User.email == "new@t.com"))
    assert c.get(f"/verify/{m.ser.dumps(uid)}").status_code == 303
    c.form("/login", email="new@t.com", password="longpassword1"); assert c.get("/account").status_code == 200
    assert C().get("/verify/garbage").status_code == 400

def test_csrf_and_rate_limit():
    c = C(); assert c.post("/login", data={"email": "a@b.com", "password": "x"}).status_code == 403
    codes = [c.form("/register", email=f"x{i}@t.com", name="N", password="short", country="Other").status_code for i in range(10)]
    assert 429 in codes

def test_role_guards():
    assert C().get("/admin").headers["location"] == "/login"
    for role in ("buyer", "seller"): assert login(role).get("/admin").status_code == 403
    assert login("buyer").get("/studio").status_code == 403
    assert login("admin").get("/admin").status_code == 200

def test_seller_scope_approval_and_xss():
    s1, s2, a = login("seller"), login("seller"), login("admin")
    form = dict(title="Seller Thing", summary="x", body='<p>ok</p><script>alert(1)</script><img src=x onerror=alert(2)>', kind="Template", price_usd="10", status="live")
    assert s1.files("/studio/edit", {}, **form).status_code == 303
    with m.Session(m.engine) as db: p = db.scalar(m.select(m.Product).where(m.Product.title == "Seller Thing"))
    assert p.status == "pending" and "<script" not in p.body and "onerror" not in p.body  # seller can't self-approve; HTML sanitized
    assert C().get(f"/p/{p.slug}").status_code == 404 and p.slug not in C().get("/sitemap.xml").text
    assert s2.get(f"/studio/edit?id={p.id}").status_code == 404 and s2.files("/studio/edit", {}, id=p.id, title="hijack").status_code == 404
    a.files("/studio/edit", {}, id=p.id, title="Seller Thing", status="live", body=p.body); assert C().get(f"/p/{p.slug}").status_code == 200
    s1.files("/studio/edit", {}, id=p.id, title="Seller Thing v2"); assert C().get(f"/p/{p.slug}").status_code == 404  # edits need re-approval

def test_uploads_validated():
    a = login("admin")
    r = a.files("/studio/edit", {"file": ("x.php", b"<?php", "text/plain")}, title="BadFile"); assert r.headers["location"].startswith("/studio/edit")
    r = a.files("/studio/edit", {"image": ("x.png", b"not an image", "image/png")}, title="BadImg"); assert r.headers["location"].startswith("/studio/edit")
    buf = io.BytesIO(); Image.new("RGB", (40, 30), "red").save(buf, "PNG")
    r = a.files("/studio/edit", {"image": ("x.png", buf.getvalue(), "image/png")}, title="GoodImg", status="live"); assert r.headers["location"] == "/studio"
    with m.Session(m.engine) as db: p = db.scalar(m.select(m.Product).where(m.Product.title == "GoodImg"))
    r = C().get(f"/img/{p.image}"); assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert C().get("/img/../../etc/passwd").status_code == 404 and f"/img/{p.image}" in C().get(f"/p/{p.slug}").text
    with m.Session(m.engine) as db: assert not db.scalar(m.select(m.Product.id).where(m.Product.title.in_(["BadFile", "BadImg"])))

def test_admin_edits_site_content():
    a = login("admin"); assert a.form("/admin/settings", hero_title="Brand New Headline", offer_on="1", offer_text="Sale", offer_pct="50").status_code == 303
    h = C().get("/").text; assert "Brand New Headline" in h and "Sale: 50% off" in h
    pid, slug = product(); assert "$14.50" in C().get(f"/p/{slug}").text  # 50% off $29 displayed
    a.form("/admin/settings", offer_on="0", hero_title="Software you buy once and actually own.")
    a.form("/admin/page", slug="privacy", title="Privacy", body="<p>hello</p><script>x</script>"); t = C().get("/pages/privacy").text; assert "hello" in t and "<script>x" not in t

def test_webhook_signature_and_card_purchase():
    b = login("buyer"); pid, _ = product(); code = order(b.uid, pid)
    assert hook(C(), "order_created", {"status": "paid", "total": 2900}, code, sig="bad").status_code == 401
    assert get_order(code).status == "pending" and b.get(f"/download/{code}").status_code == 404
    for _ in range(2): assert hook(C(), "order_created", {"status": "paid", "total": 2500}, code, id="77").status_code == 200  # replay is idempotent
    o = get_order(code); assert o.status == "paid" and o.license.startswith("TS-") and o.amount_cents == 2500 and payments(code) == 1
    assert b.get(f"/download/{code}").headers["location"] == "https://example.com/dl"
    assert login("buyer").get(f"/download/{code}").status_code == 404 and C().get(f"/download/{code}").status_code == 303
    hook(C(), "order_refunded", {}, code); assert b.get(f"/download/{code}").status_code == 404

def test_subscription_lifecycle():
    b = login("buyer"); pid, _ = product(per="month"); code = order(b.uid, pid)
    hook(C(), "order_created", {"status": "paid", "total": 900}, code, id="5")
    hook(C(), "subscription_created", {"status": "active", "renews_at": iso(30), "ends_at": None, "urls": {"customer_portal": "https://x.lemonsqueezy.com/billing"}}, code, id="S1")
    o = get_order(code); assert o.ls_sub_id == "S1" and o.sub_status == "active" and o.portal_url.endswith("/billing") and b.get(f"/download/{code}").status_code == 303
    assert "Manage billing" in b.get("/account").text
    hook(C(), "subscription_payment_success", {"subscription_id": 1, "total": 900}, "", id="INV1"); assert payments(code) == 1  # unknown sub id: ignored
    hook(C(), "subscription_payment_success", {"subscription_id": "S1", "total": 900}, "", id="INV2"); hook(C(), "subscription_payment_success", {"subscription_id": "S1", "total": 900}, "", id="INV2")
    assert payments(code) == 2  # renewal counted once
    hook(C(), "subscription_payment_failed", {"subscription_id": "S1"}, ""); assert get_order(code).sub_status == "past_due" and b.get(f"/download/{code}").status_code == 303
    hook(C(), "subscription_cancelled", {"status": "cancelled", "ends_at": iso(10)}, "", id="S1"); assert b.get(f"/download/{code}").status_code == 303  # paid period still runs
    hook(C(), "subscription_cancelled", {"status": "cancelled", "ends_at": iso(-1)}, "", id="S1"); assert b.get(f"/download/{code}").status_code == 404
    hook(C(), "subscription_expired", {"status": "expired", "ends_at": iso(-1)}, "", id="S1"); assert b.get(f"/download/{code}").status_code == 404
    hook(C(), "subscription_payment_success", {"subscription_id": "S1", "total": 900}, "", id="INV3"); assert b.get(f"/download/{code}").status_code == 303  # resubscribed

def test_manual_bkash_flow():
    pid, _ = product(); bd, other, a = login("buyer", country="Bangladesh"), login("buyer", country="Germany"), login("admin")
    assert other.form("/buy/%d" % pid, provider="manual").status_code == 403
    r = bd.form("/buy/%d" % pid, provider="manual"); code = r.headers["location"].split("/")[-1]; assert bd.get(f"/order/{code}").status_code == 200 and bd.get(f"/download/{code}").status_code == 404
    assert other.get(f"/order/{code}").status_code == 404
    oid = get_order(code).id
    assert bd.form(f"/admin/order/{oid}", action="paid").status_code == 403
    for _ in range(2): a.form(f"/admin/order/{oid}", action="paid")
    assert get_order(code).license and payments(code) == 1 and bd.get(f"/download/{code}").status_code == 303

def test_password_reset():
    uid, email = user(); c = C()
    assert c.form("/forgot", email="nobody@t.com").status_code == 303 and c.form("/forgot", email=email).status_code == 303
    with m.Session(m.engine) as db: tail = db.get(m.User, uid).pw[-12:]
    tok = m.rser.dumps([uid, tail]); assert c.get(f"/reset/{tok}").status_code == 200
    assert c.form(f"/reset/{tok}", password="short").headers["location"] == f"/reset/{tok}"
    assert c.form(f"/reset/{tok}", password="brandnewpassword").headers["location"] == "/login"
    assert c.get(f"/reset/{tok}").status_code == 400  # single use
    assert C().form("/login", email=email, password="brandnewpassword").status_code == 303 and C().get("/reset/junk").status_code == 400

class FakeHttpx:
    info = {"email": "g@t.com", "email_verified": True, "name": "G"}
    class R:
        def __init__(s, d): s.d = d
        def json(s): return s.d
    @classmethod
    def post(cls, *a, **k): return cls.R({"access_token": "tok"})
    @classmethod
    def get(cls, *a, **k): return cls.R(cls.info)

def test_google_login(monkeypatch):
    assert C().get("/auth/google").status_code == 404
    monkeypatch.setattr(m, "G_ID", "id"); monkeypatch.setattr(m, "G_SECRET", "sec"); monkeypatch.setattr(m, "httpx", FakeHttpx)
    c = C(); r = c.get("/auth/google"); assert r.headers["location"].startswith("https://accounts.google.com/") and "g" in c.get("/login").text
    assert c.get("/auth/google/callback?code=x&state=forged").status_code == 400
    state = re.search(r"state=([^&]+)", c.get("/auth/google").headers["location"]).group(1)
    r = c.get(f"/auth/google/callback?code=x&state={state}"); assert r.headers["location"] == "/account" and c.get("/account").status_code == 200
    FakeHttpx.info = {"email": "g2@t.com", "email_verified": False}; c2 = C(); s2 = re.search(r"state=([^&]+)", c2.get("/auth/google").headers["location"]).group(1)
    assert c2.get(f"/auth/google/callback?code=x&state={s2}").status_code == 400
    uid, email = user(verified=False, pw="squatterpassword"); FakeHttpx.info = {"email": email, "email_verified": True}
    c3 = C(); s3 = re.search(r"state=([^&]+)", c3.get("/auth/google").headers["location"]).group(1); c3.get(f"/auth/google/callback?code=x&state={s3}")
    assert C().form("/login", email=email, password="squatterpassword").headers["location"] == "/login"  # squatter's password was wiped
