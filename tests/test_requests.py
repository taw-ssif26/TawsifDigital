from helpers import *

GOOD = dict(title="Inventory tracker", kind="Software or app", details="I run a small shop and need a simple system to track stock, suppliers and low-stock alerts.", budget="$500")
def make(c, **kw):
    r = c.form("/request", **{**GOOD, **kw}); assert r.status_code == 303; return r.headers["location"]

def test_anonymous_sees_prompt_not_form_and_cannot_post():
    h = C().get("/request").text; assert "Create a free account" in h and 'name="details"' not in h and "Custom work" in C().get("/").text
    assert C().form("/request", **GOOD).headers["location"] == "/login"

def test_submit_notifies_admin_and_validates(monkeypatch):
    sent = []; monkeypatch.setattr(m, "mail", lambda to, sub, body, att=None: sent.append((to, sub, body)))
    b = login("buyer"); url = make(b); assert url.startswith("/request/") and sent[0][0] == "admin@test.com" and "Inventory tracker" in sent[0][2]
    assert b.get(url).status_code == 200 and "Inventory tracker" in b.get("/account").text
    assert b.form("/request", **{**GOOD, "details": "too short"}).headers["location"] == "/request"
    n = len(sent); assert b.form("/request", **{**GOOD, "website": "spam.example"}).headers["location"] == "/" and len(sent) == n  # honeypot
    with m.Session(m.engine) as db: assert db.scalar(m.select(m.func.count(m.CustomRequest.id)).where(m.CustomRequest.user_id == b.uid)) == 1
    for _ in range(4): b.form("/request", **GOOD)
    assert b.form("/request", **GOOD).status_code == 429

def test_privacy_between_customers_and_admin_dashboard():
    b, o, a = login("buyer"), login("buyer"), login("admin"); url = make(b); rid = url.split("/")[-1]
    assert o.get(url).status_code == 404 and C().get(url).status_code == 303 and a.get(url).status_code == 200
    assert o.form(f"/request/{rid}/msg", body="hi").status_code == 404 and o.form(f"/admin/request/{rid}", status="quoted").status_code == 403
    d = a.get("/admin").text; assert "Inventory tracker" in d and "new custom requests" in d and b.get("/admin").status_code == 403

def test_conversation_quote_accept_and_pay_link(monkeypatch):
    sent = []; monkeypatch.setattr(m, "mail", lambda to, sub, body, att=None: sent.append((to, sub, body)))
    b, a = login("buyer"), login("admin"); url = make(b); rid = url.split("/")[-1]; sent.clear()
    a.form(f"/request/{rid}/msg", body="Can you share your supplier list?"); assert sent[-1][0] == b.email and "supplier list" in sent[-1][2]
    b.form(f"/request/{rid}/msg", body="Yes, sending it."); assert sent[-1][0] == "admin@test.com" and "Yes, sending it." in b.get(url).text
    assert a.form(f"/admin/request/{rid}", status="quoted", quote_usd="650", pay_link="http://nope", admin_note="x").headers["location"] == url and get_req(rid).status == "new"  # insecure link rejected
    sent.clear(); a.form(f"/admin/request/{rid}", status="quoted", quote_usd="650", pay_link="https://pay.example.com/q1", admin_note="They seem serious, offer a discount")
    assert sent[0][0] == b.email and "$650" in sent[0][2]; page = b.get(url).text
    assert "$650" in page and "Accept quote" in page and "pay.example.com" not in page and "offer a discount" not in page  # link hidden until accepted, note stays private
    assert b.form(f"/request/{rid}/respond", action="cancel").status_code == 303  # quoted can be cancelled too; reopen to test accept
    a.form(f"/admin/request/{rid}", status="quoted", quote_usd="650", pay_link="https://pay.example.com/q1", admin_note="They seem serious, offer a discount")
    assert b.form(f"/request/{rid}/respond", action="accept").status_code == 303 and get_req(rid).status == "accepted"
    page = b.get(url).text; assert "https://pay.example.com/q1" in page and 'rel="noopener noreferrer"' in page and "Accept quote" not in page
    assert b.form(f"/request/{rid}/respond", action="accept").status_code == 400 and login("buyer").form(f"/request/{rid}/respond", action="accept").status_code == 404
    assert "offer a discount" in a.get(url).text

def test_decline_and_closed_setting_and_escaping():
    b, a = login("buyer"), login("admin"); url = make(b, details="<script>alert(1)</script> " + "x" * 40); rid = url.split("/")[-1]
    assert "<script>alert(1)</script>" not in b.get(url).text and "&lt;script&gt;" in b.get(url).text
    a.form(f"/admin/request/{rid}", status="quoted", quote_usd="100"); b.form(f"/request/{rid}/respond", action="decline"); assert get_req(rid).status == "declined"
    a.form("/admin/settings", request_open="0"); assert "not taking custom requests" in b.get("/request").text and b.form("/request", **GOOD).status_code == 403
    a.form("/admin/settings", request_open="1")

def get_req(rid):
    with m.Session(m.engine) as db: r = db.get(m.CustomRequest, int(rid)); db.expunge(r); return r
