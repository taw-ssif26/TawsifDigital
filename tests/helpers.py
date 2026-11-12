import re, json, hmac, hashlib, itertools
from fastapi.testclient import TestClient
from app import main as m
_n = itertools.count(1)

class C(TestClient):
    def __init__(self): super().__init__(m.app, follow_redirects=False)
    def form(self, path, **data):
        t = re.search(r'name="csrf_token" value="([^"]+)"', self.get("/login").text).group(1)
        return self.post(path, data={"csrf_token": t, **data})
    def files(self, path, files, **data):
        t = re.search(r'name="csrf_token" value="([^"]+)"', self.get("/login").text).group(1)
        return self.post(path, data={"csrf_token": t, **data}, files=files)

def user(role="buyer", country="Bangladesh", verified=True, pw="longpassword1"):
    with m.Session(m.engine) as db:
        u = m.User(email=f"u{next(_n)}@t.com", name="T", pw=m.ph.hash(pw), country=country, role=role, verified=verified); db.add(u); db.commit(); return u.id, u.email
def login(role="buyer", **kw):
    uid, email = user(role, **kw); c = C(); assert c.form("/login", email=email, password="longpassword1").status_code == 303; c.uid = uid; c.email = email; return c
def product(owner=None, status="live", **kw):
    with m.Session(m.engine) as db:
        k = next(_n); p = m.Product(slug=f"p{k}", title=f"Prod {k}", summary="s", body="<p>b</p>", price_cents=2900, status=status, owner_id=owner, link="https://example.com/dl", **{"pay_link": "https://pay.example.com/req/1", **kw}); db.add(p); db.commit(); return p.id, p.slug
def order(uid, pid, provider="payoneer", status="pending"):
    with m.Session(m.engine) as db:
        o = m.Order(code=f"O{next(_n):05d}", user_id=uid, product_id=pid, provider=provider, status=status, amount_cents=2900); db.add(o); db.commit(); return o.code
def get_order(code):
    with m.Session(m.engine) as db: o = db.scalar(m.select(m.Order).where(m.Order.code == code)); db.expunge(o); return o
def payments(code):
    with m.Session(m.engine) as db: return db.scalar(m.select(m.func.count(m.Payment.id)).join(m.Order, m.Order.id == m.Payment.order_id).where(m.Order.code == code))
def mark_paid(code, cents=None):
    with m.Session(m.engine) as db:
        o = db.scalar(m.select(m.Order).where(m.Order.code == code)); m.fulfil(o); db.flush(); m.record(db, o, "t-" + code, cents or o.amount_cents); db.commit()
