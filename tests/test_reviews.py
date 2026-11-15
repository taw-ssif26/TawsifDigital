from helpers import *

GOOD = dict(rating="5", title="Saved me hours", body="Works exactly as described and the support was quick.")
def buyer_with(pid, name="Ayesha Rahman"):
    b = login("buyer"); 
    with m.Session(m.engine) as db: db.get(m.User, b.uid).name = name; db.commit()
    mark_paid(order(b.uid, pid)); return b
def rev(rid):
    with m.Session(m.engine) as db: r = db.get(m.Review, rid); db.expunge(r); return r
def last_review(uid, pid=None):
    with m.Session(m.engine) as db: return db.scalar(m.select(m.Review).where(m.Review.user_id == uid, m.Review.product_id == pid))
def prod(pid):
    with m.Session(m.engine) as db: p = db.get(m.Product, pid); db.expunge(p); return p

def test_only_buyers_can_review_a_product():
    pid, slug = product(title="Reviewable Alpha"); ext, _ = product(external_url="https://x.example.com"); hid, _ = product(status="hidden"); other = login("buyer")
    assert other.form("/review", product_id=pid, **GOOD).status_code == 403 and C().form("/review", product_id=pid, **GOOD).headers["location"] == "/login"
    b = buyer_with(pid); assert b.form("/review", product_id=pid, **GOOD).status_code == 303
    assert b.form("/review", product_id=ext, **GOOD).status_code == 404 and b.form("/review", product_id=hid, **GOOD).status_code == 404
    assert "Only people who got this product" in other.get(f"/p/{slug}").text and 'name="rating"' in b.get(f"/p/{slug}").text and 'name="rating"' not in other.get(f"/p/{slug}").text

def test_free_product_owners_can_review_too():
    pid, slug = product(price_cents=0, pay_link=""); b = login("buyer"); b.form(f"/get/{pid}"); assert b.form("/review", product_id=pid, **GOOD).status_code == 303

def test_validation_and_honeypot():
    pid, _ = product(); b = buyer_with(pid); before = last_review(b.uid, pid)
    for bad in ({**GOOD, "rating": "0"}, {**GOOD, "rating": "6"}, {**GOOD, "body": "short"}): assert b.form("/review", product_id=pid, **bad).status_code == 303
    assert last_review(b.uid, pid) is None and b.form("/review", product_id=pid, website="spam", **GOOD).headers["location"] == "/" and last_review(b.uid, pid) is None

def test_moderation_publishes_and_updates_aggregates(monkeypatch):
    sent = []; monkeypatch.setattr(m, "mail", lambda to, sub, body, att=None: sent.append((to, sub, body)))
    pid, slug = product(title="Moderated Beta"); b, a = buyer_with(pid), login("admin"); b.form("/review", product_id=pid, **GOOD); r = last_review(b.uid, pid)
    assert r.status == "pending" and any(x[1] == "Review to approve" for x in sent) and "Saved me hours" not in C().get(f"/p/{slug}").text
    assert "Saved me hours" not in C().get("/api/search?q=moderated").text and prod(pid).rating_count == 0 and b.form(f"/admin/review/{r.id}", action="approve").status_code == 403
    d = a.get("/admin").text; assert "Saved me hours" in d and "reviews to approve" in d
    a.form(f"/admin/review/{r.id}", action="approve", reply="Thank you, glad it helped!")
    page = C().get(f"/p/{slug}").text; assert "Saved me hours" in page and "Verified purchase" in page and "Thank you, glad it helped!" in page and "Ayesha R." in page and "@" not in page.split('id="reviews"')[1].split("</section>")[0]
    p = prod(pid); assert p.rating_count == 1 and p.rating_avg == 5.0 and '"aggregateRating"' in page and '"ratingValue": "5.0"' in page or '"ratingValue":"5.0"' in page
    assert "5.0 (1)" in C().get("/products").text.replace("\n", "")
    a.form(f"/admin/review/{r.id}", action="reject"); assert "Saved me hours" not in C().get(f"/p/{slug}").text and prod(pid).rating_count == 0 and "aggregateRating" not in C().get(f"/p/{slug}").text

def test_editing_sends_back_for_approval_one_per_buyer_and_delete():
    pid, slug = product(title="Editable Gamma"); b, a, o = buyer_with(pid), login("admin"), login("buyer"); b.form("/review", product_id=pid, **GOOD); r = last_review(b.uid, pid); a.form(f"/admin/review/{r.id}", action="approve")
    assert prod(pid).rating_avg == 5.0; b.form("/review", product_id=pid, rating="2", title="Changed my mind", body="It stopped working after the update, disappointing."); r2 = last_review(b.uid, pid)
    assert r2.id == r.id and r2.status == "pending" and r2.reply == "" and prod(pid).rating_count == 0 and "Changed my mind" not in C().get(f"/p/{slug}").text
    with m.Session(m.engine) as db: assert db.scalar(m.select(m.func.count(m.Review.id)).where(m.Review.user_id == b.uid, m.Review.product_id == pid)) == 1
    assert o.form(f"/review/{r.id}/delete").status_code == 404 and b.form(f"/review/{r.id}/delete").status_code == 303 and last_review(b.uid, pid) is None

def test_average_distribution_and_xss():
    pid, slug = product(title="Stats Delta"); a = login("admin"); users = [buyer_with(pid) for _ in range(3)]
    for c, rt in zip(users, ("5", "4", "3")): c.form("/review", product_id=pid, rating=rt, title="<b>x</b>", body="<script>alert(1)</script> solid enough product here")
    for c in users: a.form(f"/admin/review/{last_review(c.uid, pid).id}", action="approve")
    p = prod(pid); assert p.rating_count == 3 and p.rating_avg == 4.0; page = C().get(f"/p/{slug}").text
    assert "<script>alert(1)</script>" not in page.split('id="reviews"')[1] and "&lt;script&gt;" in page and "3 reviews" in page

def test_platform_reviews_home_and_reviews_page():
    a, u = login("admin"), login("buyer"); assert C().form("/review", **GOOD).headers["location"] == "/login"
    u.form("/review", **{**GOOD, "title": "Great storefront platform"}); r = last_review(u.uid); assert r.product_id is None and r.status == "pending"
    assert "Great storefront platform" not in C().get("/reviews").text and "What people say" not in C().get("/").text
    a.form(f"/admin/review/{r.id}", action="approve"); assert "Great storefront platform" in C().get("/reviews").text
    h = C().get("/").text; assert "What people say" in h and "Great storefront platform" in h and "from " in h and "/reviews" in h
    u.form("/review", **{**GOOD, "rating": "4"}); assert last_review(u.uid).status == "pending" and "Great storefront platform" not in C().get("/reviews").text

def test_top_rated_sort_and_card_stars():
    p1, s1 = product(title="Ranksort One", kind="Zrank"); p2, s2 = product(title="Ranksort Two", kind="Zrank"); a = login("admin")
    for pid, rt in ((p1, "3"), (p2, "5")):
        c = buyer_with(pid); c.form("/review", product_id=pid, **{**GOOD, "rating": rt}); a.form(f"/admin/review/{last_review(c.uid, pid).id}", action="approve")
    h = C().get("/search?q=ranksort&sort=rating").text; assert h.index("Ranksort Two") < h.index("Ranksort One") and 'class="stars"' in h and "Top rated" in h
