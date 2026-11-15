from helpers import *

def pay_of(code):
    with m.Session(m.engine) as db: p = db.scalar(m.select(m.Payment).join(m.Order).where(m.Order.code == code)); db.expunge(p); return p
def setup(**kw):
    pid, slug = product(title="Invoiced Item", **kw); b, a = login("buyer", country="Germany"), login("admin"); code = order(b.uid, pid); oid = get_order(code).id; return pid, b, a, code, oid

def test_invoice_numbers_email_attachment_and_portal(monkeypatch):
    sent = []; monkeypatch.setattr(m, "mail", lambda to, sub, body, att=None: sent.append((to, sub, body, att)))
    pid, b, a, code, oid = setup(); a.form(f"/admin/order/{oid}", action="paid"); pay = pay_of(code); assert pay.inv_no and pay.amount_cents == 2900
    mail = [x for x in sent if x[0] == b.email][0]; name, data = mail[3][0]; assert name == f"INV-{pay.created.year}-{pay.inv_no:05d}.pdf" and data[:5] == b"%PDF-" and f"/invoice/{pay.id}" in mail[2] and "PDF copy is attached" in mail[2]
    pid2, b2, a2, code2, oid2 = setup(); a.form(f"/admin/order/{oid2}", action="paid"); assert pay_of(code2).inv_no == pay.inv_no + 1  # sequential, never reused
    acc = b.get("/account").text; assert "Invoices" in acc and f"/invoice/{pay.id}" in acc and f"/invoice/{pay.id}/pdf" in acc and f"INV-{pay.created.year}-{pay.inv_no:05d}" in acc
    n = len(sent); a.form(f"/admin/order/{oid}", action="resend"); assert len(sent) == n + 1 and sent[-1][3] and payments(code) == 1  # resend: same invoice, no new payment

def test_invoice_page_pdf_and_access_control():
    pid, b, a, code, oid = setup(); a.form("/admin/settings", biz_name="Acme Digital Ltd", biz_address="12 Example Road\nChattogram", biz_tax="REG-123", invoice_note="Pay within 7 days"); a.form(f"/admin/order/{oid}", action="paid"); pay = pay_of(code)
    h = b.get(f"/invoice/{pay.id}").text; assert all(x in h for x in ("Acme Digital Ltd", "12 Example Road", "REG-123", "Pay within 7 days", "Invoiced Item", "$29.00", code, "Paid", "data-print", f"INV-{pay.created.year}")) and 'content="noindex"' in h
    r = b.get(f"/invoice/{pay.id}/pdf"); assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:5] == b"%PDF-" and "attachment" in r.headers["content-disposition"] and "no-store" in r.headers["cache-control"]
    other = login("buyer"); assert other.get(f"/invoice/{pay.id}").status_code == 404 and other.get(f"/invoice/{pay.id}/pdf").status_code == 404 and C().get(f"/invoice/{pay.id}").headers["location"] == "/login"
    assert a.get(f"/invoice/{pay.id}").status_code == 200 and b.get("/invoice/999999").status_code == 404
    a.form("/admin/settings", biz_name="Tawsif Digital", biz_address="", biz_tax="", invoice_note="Thank you for your purchase.")

def test_refunded_status_free_orders_and_monthly_renewals():
    pid, b, a, code, oid = setup(per="month"); a.form(f"/admin/order/{oid}", action="paid"); a.form(f"/admin/order/{oid}", action="renew")
    with m.Session(m.engine) as db: pays = db.scalars(m.select(m.Payment).where(m.Payment.order_id == oid).order_by(m.Payment.id)).all()
    assert len(pays) == 2 and pays[1].inv_no == pays[0].inv_no + 1 and "Access until" in b.get(f"/invoice/{pays[1].id}").text  # each renewal is its own invoice
    a.form(f"/admin/order/{oid}", action="refunded"); assert "Refunded" in b.get(f"/invoice/{pays[0].id}").text
    fp, _ = product(price_cents=0, pay_link=""); b.form(f"/get/{fp}"); assert b.get("/account").text.count("/pdf") == 2  # free items produce no invoice

def test_legacy_payment_gets_a_number_and_non_latin_names_do_not_break_pdf():
    pid, b, a, code, oid = setup()
    with m.Session(m.engine) as db:
        db.get(m.User, b.uid).name = "আয়েশা রহমান"; o = db.get(m.Order, oid); m.fulfil(o); db.add(m.Payment(order_id=oid, ref="legacy-" + code, amount_cents=2900, inv_no=None)); db.commit()
    pay = pay_of(code); assert pay.inv_no is None; assert "INV-" in b.get("/account").text and pay_of(code).inv_no
    r = b.get(f"/invoice/{pay.id}/pdf"); assert r.status_code == 200 and r.content[:5] == b"%PDF-" and "আয়েশা" in b.get(f"/invoice/{pay.id}").text  # web invoice shows the real name

def test_brevo_attachment_encoding(monkeypatch):
    calls = []; monkeypatch.setenv("BREVO_API_KEY", "k"); monkeypatch.setenv("MAIL_FROM", "Shop <hi@x.com>")
    class R: status_code = 201; text = ""
    class H:
        @staticmethod
        def post(url, **k): calls.append(k); return R()
    monkeypatch.setattr(m, "httpx", H); m.mail("a@b.com", "S", "<p>x</p>", [("INV-1.pdf", b"%PDF-test")])
    import base64; assert calls[0]["json"]["attachment"] == [{"name": "INV-1.pdf", "content": base64.b64encode(b"%PDF-test").decode()}]
    m.mail("a@b.com", "S", "<p>x</p>"); assert "attachment" not in calls[1]["json"]
