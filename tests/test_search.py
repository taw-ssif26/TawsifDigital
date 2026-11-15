from helpers import *

def api(c, q): r = c.get("/api/search", params={"q": q}); assert r.status_code == 200; return r.json()
def titles(d): return [r["title"] for r in d["results"]]

def test_live_only_case_insensitive_substring_and_ranking():
    product(title="Quasarflux Builder", summary="x", kind="Tool"); product(title="Other Thing", summary="a quasarflux helper inside", kind="Tool")
    product(status="hidden", title="Quasarflux Secret"); product(status="pending", title="Quasarflux Draft")
    c = C(); assert titles(api(c, "quasarflux")) == ["Quasarflux Builder", "Other Thing"]  # title match outranks summary match; hidden and pending never leak
    assert titles(api(c, "QUASARFLUX BUILDER")) == ["Quasarflux Builder"] and titles(api(c, "uasarflu"))[0] == "Quasarflux Builder"  # every word must match; substrings work
    assert api(c, "quasarflux")["total"] == 2

def test_searches_text_not_markup():
    product(title="Plain Item", body="<div class='wrapper'><p>nebulacore engine</p></div>"); c = C()
    assert titles(api(c, "nebulacore")) == ["Plain Item"] and api(c, "wrapper")["results"] == [] and api(c, "div")["results"] == []

def test_edge_cases_are_safe():
    c = C(); assert api(c, "")["results"] == [] and api(c, "a")["results"] == []
    for q in ("%", "_", "'; DROP TABLE products;--", "<script>alert(1)</script>", "x" * 500, "\\"): assert api(c, q)["results"] == []
    assert C().get("/").status_code == 200  # nothing broke

def test_labels_and_offer_price():
    product(title="Labeltest Paid", price_cents=2000, kind="Zlabel"); product(title="Labeltest Free", price_cents=0, pay_link="", kind="Zlabel"); product(title="Labeltest Ext", price_cents=0, external_url="https://x.example.com", kind="Zlabel")
    d = {r["title"]: r for r in api(C(), "labeltest")["results"]}; assert d["Labeltest Paid"]["price"] == "$20" and d["Labeltest Free"]["price"] == "Free" and d["Labeltest Ext"]["price"] == ""
    assert d["Labeltest Paid"]["url"].startswith("/p/") and d["Labeltest Paid"]["art"] in (0, 1, 2, 3)
    a = login("admin"); a.form("/admin/settings", offer_on="1", offer_pct="50"); assert {r["title"]: r for r in api(C(), "labeltest")["results"]}["Labeltest Paid"]["price"] == "$10"; a.form("/admin/settings", offer_on="0")

def test_search_page_sort_filter_noindex_and_escaping():
    product(title="Vortexone", price_cents=1000, kind="Alpha"); product(title="Vortextwo", price_cents=3000, kind="Beta"); product(title="Vortexthree", price_cents=2000, kind="Alpha"); c = C()
    h = c.get("/search?q=vortex&sort=price_asc").text; assert 'content="noindex,follow"' in h and h.index("Vortexone") < h.index("Vortexthree") < h.index("Vortextwo")
    h = c.get("/search?q=vortex&sort=price_desc").text; assert h.index("Vortextwo") < h.index("Vortexthree") < h.index("Vortexone")
    h = c.get("/search?q=vortex&kind=Alpha").text; assert "Vortexone" in h and "Vortextwo" not in h and "3 results" in c.get("/search?q=vortex").text
    h = c.get("/search?q=%3Cscript%3Ealert(1)%3C/script%3E").text; assert "<script>alert(1)" not in h and "Nothing matched" in h and "/request" in h
    assert "Latest" in c.get("/search").text and c.get("/search?q=vortex&sort=evil").status_code == 200

def test_typo_rescue():
    product(title="Zorbulator Autopilot", kind="Automation"); c = C(); d = api(c, "zorbulatr"); assert d["results"] == [] and d["suggest"] == "zorbulator"
    h = c.get("/search?q=zorbulatr").text; assert "Showing results for" in h and "Zorbulator Autopilot" in h

def test_search_ui_and_seo_hooks():
    h = C().get("/").text; assert 'id="sx"' in h and "data-search" in h and "SearchAction" in h and 'role="listbox"' in h
    assert 'action="/search"' in C().get("/products").text and "/api/search" in C().get("/static/app.js").text and "Disallow: /api/" in C().get("/robots.txt").text

def test_api_is_rate_limited():
    c = C(); codes = [c.get("/api/search?q=ab").status_code for _ in range(91)]; assert codes[0] == 200 and codes[-1] == 429

def test_typo_rescue_matches_word_starts():
    product(title="Zentrawave Studio", kind="Template"); d = api(C(), "zentrwav"); assert d["results"] == [] and d["suggest"] == "zentrawave"
    assert "Zentrawave Studio" in C().get("/search?q=zentrwav").text
