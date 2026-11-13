import re, time
from datetime import datetime, timedelta
from helpers import *

def test_totp_matches_rfc6238():
    assert m.totp_code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 1) == "287082"

def test_seller_payouts_and_refund_clawback():
    sid, _ = user("seller"); pid, _ = product(owner=sid); buyer = login("buyer"); a = login("admin")
    code = order(buyer.uid, pid); mark_paid(code, 10000)
    with m.Session(m.engine) as db: b = m.balance(db, sid, 80)
    assert b == {"gross": 10000, "owed": 8000, "paid": 0, "due": 8000}
    assert a.form("/admin/payout", seller_id=sid, amount_usd="0").status_code == 303 and a.form("/admin/payout", seller_id=sid, amount_usd="30", note="bKash").status_code == 303
    with m.Session(m.engine) as db: assert m.balance(db, sid, 80)["due"] == 5000
    assert "Seller payouts" in a.get("/admin").text and login("buyer").form("/admin/payout", seller_id=sid, amount_usd="5").status_code == 403
    a.form(f"/admin/order/{get_order(code).id}", action="refunded")
    with m.Session(m.engine) as db: assert m.balance(db, sid, 80)["due"] == -3000

def test_emails_sent_once(monkeypatch):
    sent = []; monkeypatch.setattr(m, "mail", lambda to, sub, body: sent.append((to, sub, body)))
    b, a = login("buyer"), login("admin"); pid, _ = product(); code = order(b.uid, pid); oid = get_order(code).id
    for _ in range(2): a.form(f"/admin/order/{oid}", action="paid")
    paid = [x for x in sent if x[0] == b.email]; assert len(paid) == 1 and get_order(code).license in paid[0][2]
    b.form(f"/order/{code}/claim"); assert b.form(f"/order/{get_order(order(b.uid, pid)).code}/claim").status_code == 303 and any("Payment to confirm" in x[1] for x in sent)

def test_resend_verification(monkeypatch):
    sent = []; monkeypatch.setattr(m, "mail", lambda to, sub, body: sent.append((to, body)))
    _, pending = user(verified=False); _, ok = user(); c = C()
    for e in (pending, ok, "ghost@t.com"): assert c.form("/resend", email=e).headers["location"] == "/login"
    assert [x[0] for x in sent] == [pending] and "/verify/" in sent[0][1]

def test_monthly_subscription_paid_until_and_renewal():
    pid, _ = product(per="month"); bd, a = login("buyer"), login("admin"); code = bd.form(f"/buy/{pid}", provider="payoneer").headers["location"].split("/")[-1]; oid = get_order(code).id
    a.form(f"/admin/order/{oid}", action="paid"); o = get_order(code); assert timedelta(days=30) < o.paid_until - datetime.utcnow() < timedelta(days=32) and bd.get(f"/download/{code}").status_code == 303
    with m.Session(m.engine) as db: db.get(m.Order, oid).paid_until = datetime.utcnow() - timedelta(days=1); db.commit()
    assert bd.get(f"/download/{code}").status_code == 404  # lapsed
    with m.Session(m.engine) as db: db.get(m.Order, oid).paid_until = datetime.utcnow() + timedelta(days=3); db.commit()
    assert code in a.get("/admin").text  # shows on the expiring list
    a.form(f"/admin/order/{oid}", action="renew"); assert get_order(code).paid_until - datetime.utcnow() > timedelta(days=30) and payments(code) == 2

def test_audit_log_and_seller_application():
    a = login("admin"); a.form("/admin/settings", hero_title="Software you buy once and actually own."); assert "Edited site content" in a.get("/admin").text
    b = login("buyer"); assert b.form("/account/apply").status_code == 303 and b.get("/studio").status_code == 403
    assert "wants to sell" in a.get("/admin").text; a.form(f"/admin/user/{b.uid}", role="seller"); assert b.get("/studio").status_code == 200

def test_two_factor_login():
    c = login("admin"); assert "Turn on two-factor" in c.get("/admin").text
    c.form("/account/2fa/start"); sec = re.search(r'class="k2"[^>]*>([A-Z2-7]+)<', c.get("/account").text).group(1); now = int(time.time() // 30)
    assert c.form("/account/2fa/confirm", code="000000").headers["location"] == "/account"
    c.form("/account/2fa/confirm", code=m.totp_code(sec, now - 1)); assert "Turn on two-factor" not in c.get("/admin").text
    d = C(); r = d.form("/login", email=c.email, password="longpassword1"); assert r.headers["location"] == "/login/2fa" and d.get("/admin").status_code == 303  # password alone is not enough
    assert d.form("/login/2fa", code="123456").headers["location"] == "/login/2fa" and d.form("/login/2fa", code=m.totp_code(sec, now - 1)).headers["location"] == "/login/2fa"  # confirm code is spent
    assert d.form("/login/2fa", code=m.totp_code(sec, now)).headers["location"] == "/admin" and d.get("/admin").status_code == 200
    e = C(); e.form("/login", email=c.email, password="longpassword1"); assert e.form("/login/2fa", code=m.totp_code(sec, now)).headers["location"] == "/login/2fa"  # same code can't be replayed
    assert e.form("/login/2fa", code=m.totp_code(sec, now + 1)).headers["location"] == "/admin"

def test_legal_pages_exist():
    c = C(); assert all(c.get(f"/pages/{s}").status_code == 200 for s in ("terms", "refunds", "privacy"))

def test_external_product_sends_buyers_to_its_own_site():
    pid, slug = product(external_url="https://shop.example.com/landing", pay_link=""); b, a, s = login("buyer", country="Bangladesh"), login("admin"), login("seller")
    for c in (C(), b):
        h = c.get(f"/p/{slug}").text; assert 'href="https://shop.example.com/landing"' in h and 'rel="noopener"' in h and "Buy on shop.example.com" in h
        assert "/buy/" not in h and "bKash" not in h and "Pay with Payoneer" not in h
    assert b.form(f"/buy/{pid}", provider="payoneer").status_code == 400 and b.form(f"/buy/{pid}", provider="manual").status_code == 400
    a.form("/admin/settings", offer_on="1", offer_pct="50"); assert "$14.50" not in C().get(f"/p/{slug}").text; a.form("/admin/settings", offer_on="0")  # our offers don't apply to their price
    assert "sold on its own website" in C().get("/llms.txt").text and slug in C().get("/sitemap.xml").text
    f = dict(title="Ext", summary="x", kind="App", price_usd="0", status="live", external_url="https://other.example.com")
    s.files("/studio/edit", {}, **f); a.files("/studio/edit", {}, **{**f, "title": "Ext2", "external_url": "http://insecure.example.com"})
    with m.Session(m.engine) as db:
        assert db.scalar(m.select(m.Product.external_url).where(m.Product.title == "Ext")) == ""  # seller can't route buyers off-site
        assert db.scalar(m.select(m.Product.id).where(m.Product.title == "Ext2")) is None  # non-https rejected
    a.files("/studio/edit", {}, **{**f, "title": "Ext3"}); page = C().get("/p/" + [x for x in re.findall(r'/p/(ext3[^"]*)', C().get("/products").text)][0]).text
    assert "https://other.example.com" in page and "$0" not in page

def test_free_product_goes_straight_to_library():
    pid, slug = product(price_cents=0, pay_link="", per="month"); b = login("buyer", country="Germany")
    anon = C().get(f"/p/{slug}").text; assert "Create a free account" in anon and "Free" in anon and "/get/" not in anon and "Payoneer" not in anon
    h = b.get(f"/p/{slug}").text; assert "Get it free" in h and "Pay with Payoneer" not in h
    assert b.form(f"/buy/{pid}", provider="payoneer").status_code == 400 and C().form(f"/get/{pid}").headers["location"] == "/login"
    for _ in range(2): assert b.form(f"/get/{pid}").headers["location"] == "/account"  # twice: still one order
    with m.Session(m.engine) as db: orders = db.scalars(m.select(m.Order).where(m.Order.user_id == b.uid, m.Order.product_id == pid)).all()
    assert len(orders) == 1 and orders[0].status == "paid" and orders[0].amount_cents == 0 and orders[0].provider == "free" and orders[0].license == ""
    assert b.get(f"/download/{orders[0].code}").headers["location"] == "https://example.com/dl" and "Free" in b.get("/account").text  # monthly flag ignored for free items
    assert payments(orders[0].code) == 0 and "In your library" in b.get(f"/p/{slug}").text
    ext, _ = product(price_cents=0, external_url="https://x.example.com", pay_link=""); pend, _ = product(price_cents=0, status="pending")
    assert b.form(f"/get/{ext}").status_code == 404 and b.form(f"/get/{pend}").status_code == 404  # external or unapproved items can't be claimed

def test_mail_goes_through_brevo(monkeypatch):
    calls = []; monkeypatch.setenv("BREVO_API_KEY", "k1"); monkeypatch.setenv("MAIL_FROM", "Shop <hi@x.com>")
    class R: status_code = 201; text = ""
    class H:
        @staticmethod
        def post(url, **k): calls.append((url, k)); return R()
    monkeypatch.setattr(m, "httpx", H); m.mail("a@b.com", "Subj", "<p>x</p>")
    url, k = calls[0]; assert url == "https://api.brevo.com/v3/smtp/email" and k["headers"]["api-key"] == "k1"
    assert k["json"] == {"sender": {"name": "Shop", "email": "hi@x.com"}, "to": [{"email": "a@b.com"}], "subject": "Subj", "htmlContent": "<p>x</p>"}
    class Boom:
        @staticmethod
        def post(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr(m, "httpx", Boom); m.mail("a@b.com", "S", "b")  # an outage must not raise
    monkeypatch.setenv("MAIL_FROM", ""); m.mail("a@b.com", "S", "b")
