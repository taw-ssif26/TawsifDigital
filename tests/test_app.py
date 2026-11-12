import io, re
from PIL import Image
from helpers import *

def test_public_pages_and_seo():
    pid, slug = product(); c = C()
    for u in ("/", "/products", f"/p/{slug}", "/pages/about", "/login", "/register"): assert c.get(u).status_code == 200
    assert f"/p/{slug}" in c.get("/sitemap.xml").text and "Sitemap:" in c.get("/robots.txt").text and slug in c.get("/llms.txt").text
    assert '"Product"' in c.get(f"/p/{slug}").text and "frame-ancestors 'none'" in c.get("/").headers["content-security-policy"]
    assert "lemonsqueezy" not in c.get("/").headers["content-security-policy"] and C().post("/webhooks/lemonsqueezy").status_code == 404

def test_new_design_elements_render():
    pid, slug = product(); h = C().get("/").text
    for needle in ('id="fxc"', 'class="pcard', 'class="band"', 'data-t="fx"', "How it works"): assert needle in h
    assert 'class="cover c' in C().get(f"/p/{slug}").text

def test_register_verify_login():
    c = C(); assert c.form("/register", email="new@t.com", name="N", password="longpassword1", country="Bangladesh").status_code == 303
    assert c.form("/login", email="new@t.com", password="longpassword1").status_code == 303 and c.get("/account").status_code == 303
    with m.Session(m.engine) as db: uid = db.scalar(m.select(m.User.id).where(m.User.email == "new@t.com"))
    assert c.get(f"/verify/{m.ser.dumps(uid)}").status_code == 303
    c.form("/login", email="new@t.com", password="longpassword1"); assert c.get("/account").status_code == 200 and C().get("/verify/garbage").status_code == 400

def test_csrf_and_rate_limit():
    c = C(); assert c.post("/login", data={"email": "a@b.com", "password": "x"}).status_code == 403
    assert 429 in [c.form("/register", email=f"x{i}@t.com", name="N", password="short", country="Other").status_code for i in range(10)]

def test_role_guards():
    assert C().get("/admin").headers["location"] == "/login"
    for role in ("buyer", "seller"): assert login(role).get("/admin").status_code == 403
    assert login("buyer").get("/studio").status_code == 403 and login("admin").get("/admin").status_code == 200

def test_seller_scope_approval_xss_and_payment_links():
    s1, s2, a = login("seller"), login("seller"), login("admin")
    form = dict(title="Seller Thing", summary="x", body='<p>ok</p><script>alert(1)</script><img src=x onerror=alert(2)>', kind="Template", price_usd="10", status="live", pay_link="https://evil.example/steal")
    assert s1.files("/studio/edit", {}, **form).status_code == 303
    with m.Session(m.engine) as db: p = db.scalar(m.select(m.Product).where(m.Product.title == "Seller Thing"))
    assert p.status == "pending" and "<script" not in p.body and "onerror" not in p.body and p.pay_link == ""  # seller can't self-approve, inject HTML, or set where money goes
    assert C().get(f"/p/{p.slug}").status_code == 404 and p.slug not in C().get("/sitemap.xml").text
    assert s2.get(f"/studio/edit?id={p.id}").status_code == 404 and s2.files("/studio/edit", {}, id=p.id, title="hijack").status_code == 404
    assert a.files("/studio/edit", {}, id=p.id, title="Seller Thing", status="live", body=p.body, pay_link="http://insecure").headers["location"].startswith("/studio/edit")
    a.files("/studio/edit", {}, id=p.id, title="Seller Thing", status="live", body=p.body, pay_link="https://pay.example.com/abc"); assert C().get(f"/p/{p.slug}").status_code == 200
    s1.files("/studio/edit", {}, id=p.id, title="Seller Thing v2", pay_link="https://evil.example")
    with m.Session(m.engine) as db: p2 = db.get(m.Product, p.id)
    assert p2.status == "pending" and p2.pay_link == "https://pay.example.com/abc"

def test_uploads_validated():
    a = login("admin")
    assert a.files("/studio/edit", {"file": ("x.php", b"<?php", "text/plain")}, title="BadFile").headers["location"].startswith("/studio/edit")
    assert a.files("/studio/edit", {"image": ("x.png", b"not an image", "image/png")}, title="BadImg").headers["location"].startswith("/studio/edit")
    buf = io.BytesIO(); Image.new("RGB", (40, 30), "red").save(buf, "PNG")
    assert a.files("/studio/edit", {"image": ("x.png", buf.getvalue(), "image/png")}, title="GoodImg", status="live").headers["location"] == "/studio"
    with m.Session(m.engine) as db: p = db.scalar(m.select(m.Product).where(m.Product.title == "GoodImg"))
    r = C().get(f"/img/{p.image}"); assert r.status_code == 200 and r.headers["content-type"] == "image/webp" and C().get("/img/../../etc/passwd").status_code == 404
    with m.Session(m.engine) as db: assert not db.scalar(m.select(m.Product.id).where(m.Product.title.in_(["BadFile", "BadImg"])))

def test_admin_edits_site_content():
    a = login("admin"); assert a.form("/admin/settings", hero_title="Brand New Headline", offer_on="1", offer_text="Sale", offer_pct="50", cta_title="Closing words").status_code == 303
    h = C().get("/").text; assert "Brand New Headline" in h and "Sale" in h and "50% off" in h and "Closing words" in h
    pid, slug = product(); assert "$14.50" in C().get(f"/p/{slug}").text
    a.form("/admin/settings", offer_on="0", hero_title="Software you buy once and actually own.", cta_title="Ready when you are.")
    a.form("/admin/page", slug="privacy", title="Privacy", body="<p>hello</p><script>x</script>"); t = C().get("/pages/privacy").text; assert "hello" in t and "<script>x" not in t

def test_payoneer_purchase_flow():
    b, a, other = login("buyer", country="Germany"), login("admin"), login("buyer"); pid, slug = product()
    assert "Pay with Payoneer" in b.get(f"/p/{slug}").text and "bKash" not in b.get(f"/p/{slug}").text
    r = b.form(f"/buy/{pid}", provider="payoneer"); code = r.headers["location"].split("/")[-1]
    assert b.form(f"/buy/{pid}", provider="payoneer").headers["location"].endswith(code)  # reuses the pending order
    page = b.get(f"/order/{code}").text; assert "https://pay.example.com/req/1" in page and 'rel="noopener noreferrer"' in page and "$29" in page
    assert b.get(f"/download/{code}").status_code == 404 and other.get(f"/order/{code}").status_code == 404 and other.form(f"/order/{code}/claim", note="x").status_code == 404
    assert b.form(f"/order/{code}/claim", note="TXN-123").status_code == 303 and "TXN-123" in a.get("/admin").text and "says paid" in a.get("/admin").text
    oid = get_order(code).id; assert b.form(f"/admin/order/{oid}", action="paid").status_code == 403
    for _ in range(2): a.form(f"/admin/order/{oid}", action="paid")
    o = get_order(code); assert o.status == "paid" and o.license.startswith("TS-") and payments(code) == 1
    assert b.get(f"/download/{code}").headers["location"] == "https://example.com/dl" and other.get(f"/download/{code}").status_code == 404 and C().get(f"/download/{code}").status_code == 303
    assert b.form(f"/order/{code}/claim").status_code == 404  # already paid
    a.form(f"/admin/order/{oid}", action="refunded"); assert b.get(f"/download/{code}").status_code == 404

def test_no_payoneer_link_blocks_checkout_and_manual_is_bd_only():
    b = login("buyer", country="Germany"); pid, _ = product(pay_link=""); assert b.form(f"/buy/{pid}", provider="payoneer").status_code == 503
    assert b.form(f"/buy/{pid}", provider="manual").status_code == 403 and b.form(f"/buy/{pid}", provider="paypal").status_code == 400
    a = login("admin"); a.form("/admin/settings", pay_default="https://pay.example.com/default"); assert b.form(f"/buy/{pid}", provider="payoneer").status_code == 303
    a.form("/admin/settings", pay_default="")
