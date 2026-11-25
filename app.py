"""Bansuri Studio website.

Flask + SQLite. Public pages read their content from the database, and the
admin panel at /admin edits that content and shows saved enquiries.
"""
import csv
import io
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

BASE = Path(__file__).resolve().parent
INSTANCE = Path(os.environ.get("INSTANCE_DIR", BASE / "instance"))
INSTANCE.mkdir(parents=True, exist_ok=True)
DB_PATH = INSTANCE / "data.db"
UPLOADS = BASE / "static" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def _secret_key():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    f = INSTANCE / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


app.config.update(
    SECRET_KEY=_secret_key(),
    MAX_CONTENT_LENGTH=80 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("HTTPS") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)
if os.environ.get("BEHIND_PROXY") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# --------------------------------------------------------------------------
# Content constants
# --------------------------------------------------------------------------
SERVICES = [
    "Reels and videos", "Promotional videos", "Product photography",
    "Social media management", "Digital marketing", "Website development",
]
WORK_CATS = ["Reels", "Promotions", "Photography", "Websites"]
STATUSES = [("new", "New"), ("contacted", "Contacted"), ("closed", "Closed")]

SETTING_DEFAULTS = {
    "whatsapp": "",
    "phone_display": "",
    "email": "",
    "instagram_url": "https://www.instagram.com/bansuri.studio/",
    "instagram_handle": "@bansuri.studio",
    "address": "Pilibhit, Uttar Pradesh",
    "reel_note": "Introductory launch prices for our first clients.",
    "web_note": ("Introductory launch prices for our first clients. Meta Ads "
                 "management is optional: ₹2,000 to ₹5,000 per month, plus the "
                 "ad spend, which is paid by the client."),
}

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS work(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'Reels', video TEXT NOT NULL DEFAULT '',
  thumb TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#2f6b52',
  is_sample INTEGER NOT NULL DEFAULT 0, published INTEGER NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL, stars INTEGER NOT NULL DEFAULT 5,
  is_sample INTEGER NOT NULL DEFAULT 0, published INTEGER NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS packages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL DEFAULT 'reel',
  name TEXT NOT NULL, price TEXT NOT NULL, unit TEXT NOT NULL DEFAULT '',
  features TEXT NOT NULL DEFAULT '', highlight INTEGER NOT NULL DEFAULT 0,
  wa_message TEXT NOT NULL DEFAULT '', published INTEGER NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
  thumb TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#2f6b52',
  is_sample INTEGER NOT NULL DEFAULT 0, published INTEGER NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS faqs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, answer TEXT NOT NULL,
  published INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS enquiries(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT NOT NULL,
  service TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL);
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def q(sql, args=(), one=False):
    rows = db().execute(sql, args).fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def ex(sql, args=()):
    cur = db().execute(sql, args)
    db().commit()
    return cur.lastrowid


def get_settings():
    if "settings" not in g:
        s = dict(SETTING_DEFAULTS)
        for r in q("SELECT key, value FROM settings"):
            if r["key"] in SETTING_DEFAULTS:
                s[r["key"]] = r["value"]
        g.settings = s
    return g.settings


def set_setting(key, value):
    ex("INSERT INTO settings(key,value) VALUES(?,?) "
       "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    g.pop("settings", None)


def seed():
    """First run only: fill the database with the content from the old single-page site."""
    if q("SELECT 1 FROM settings WHERE key='seeded'", one=True):
        return
    conn = db()
    work = [
        ("Bike Transition Edit", "Reels", "bike-transition-edit.mp4", "bike-transition-edit.jpg", "#8a6d2b", 0),
        ("Video Edit", "Reels", "video-edit.mp4", "video-edit.jpg", "#4d6b8a", 0),
        ("Featured reel", "Reels", "", "", "#2f6b52", 1),
        ("Product shoot", "Photography", "", "", "#7a4f5f", 1),
        ("Website walkthrough", "Websites", "", "", "#516458", 1),
    ]
    for i, w in enumerate(work, 1):
        conn.execute("INSERT INTO work(title,category,video,thumb,color,is_sample,sort) VALUES(?,?,?,?,?,?,?)",
                     (*w[:5], w[5], i))
    reviews = [
        ("Rahul S.", "Sweet shop owner", "Our Diwali reel brought more people to the shop than any poster we have ever printed."),
        ("Neha M.", "Salon owner", "They understood our salon right away. The reels look professional and bookings went up."),
        ("Amit K.", "Coaching centre director", "Our new website gets admission enquiries on WhatsApp every day. Setup was quick and simple."),
    ]
    for i, r in enumerate(reviews, 1):
        conn.execute("INSERT INTO reviews(name,role,text,stars,is_sample,sort) VALUES(?,?,?,5,1,?)", (*r, i))
    pk = [
        ("reel", "Edit Only", "₹249", "/ reel", "For clips you’ve already recorded\nCuts, music and captions\n1 round of changes", 0,
         "I’m interested in the Edit Only package. I already have recorded clips."),
        ("reel", "Starter", "₹1,799", "", "2 edited reels\nMusic and captions\n1 round of changes", 0,
         "I’m interested in the Starter reel package."),
        ("reel", "Growth", "₹6,999", "", "6 reels with shoot day\nProduct photos\nPosters for offers\n2 rounds of changes", 1,
         "I’m interested in the Growth reel package."),
        ("reel", "Monthly", "₹14,999", "/ month", "12 reels each month\nContent plan\nPosting on your page\nFestival specials", 0,
         "I’m interested in the Monthly reel package."),
        ("website", "Basic site", "₹1,500", "", "One-page website\nAddress, timings and Google Maps\nWhatsApp and call buttons\nOptional Meta Ads (ad spend paid by client)", 0,
         "I’m interested in the Basic website package."),
        ("website", "Business site", "₹5,999", "", "Up to 5 pages\nPhoto and reel gallery\nEnquiry form\nDomain setup help\nOptional Meta Ads (ad spend paid by client)", 1,
         "I’m interested in the Business website package."),
        ("website", "Catalogue site", "₹11,999", "", "Product or menu gallery with prices\nOrder through WhatsApp\nEasy to update\nOptional Meta Ads (ad spend paid by client)", 0,
         "I’m interested in the Catalogue website package."),
    ]
    for i, p in enumerate(pk, 1):
        conn.execute("INSERT INTO packages(kind,name,price,unit,features,highlight,wa_message,sort) VALUES(?,?,?,?,?,?,?,?)", (*p, i))
    projects = [("Your first website project", "#2f6b52"), ("Your second website project", "#4d6b8a")]
    for i, (t, c) in enumerate(projects, 1):
        conn.execute("INSERT INTO projects(title,description,color,is_sample,sort) VALUES(?,?,?,1,?)",
                     (t, "Project description goes here.", c, i))
    faqs = [
        ("What services does Bansuri Studio offer?", "Reel and video editing, promotional videos, product photography, social media management, digital marketing and website development."),
        ("Do you create Instagram Reels?", "Yes. Reels are our main focus, from planning to the final edit."),
        ("Do you provide video shooting and editing?", "Yes. We can shoot at your location, or edit footage you already have."),
        ("Can you manage our social media pages?", "Yes. We plan, create and post content so your pages stay active."),
        ("Do you build business websites?", "Yes. We build mobile-friendly websites with WhatsApp and enquiry forms."),
        ("Do you run Meta Ads?", "Yes. We can set up Meta Ads on Instagram and Facebook. The cost of the ads themselves is paid by the client."),
        ("How much do your packages cost?", "Reel editing starts at ₹249 per reel and websites start at ₹1,500. See the packages page, or message us for a quote that fits your business."),
        ("How can I get started?", "Fill in the short form on this page, or message us on WhatsApp."),
        ("How can I contact Bansuri Studio?", "Reach us on WhatsApp or Instagram (@bansuri.studio)."),
    ]
    for i, f in enumerate(faqs, 1):
        conn.execute("INSERT INTO faqs(question,answer,sort) VALUES(?,?,?)", (*f, i))
    conn.execute("INSERT INTO settings(key,value) VALUES('seeded','1')")
    conn.commit()


def init_db():
    with app.app_context():
        db().executescript(SCHEMA)
        db().commit()
        seed()
        pw = os.environ.get("ADMIN_PASSWORD")
        if pw and not q("SELECT 1 FROM settings WHERE key='admin_hash'", one=True):
            ex("INSERT INTO settings(key,value) VALUES('admin_hash',?)", (generate_password_hash(pw),))


# --------------------------------------------------------------------------
# Helpers and template globals
# --------------------------------------------------------------------------
IST = timezone(timedelta(hours=5, minutes=30))


def digits(s):
    return re.sub(r"\D", "", s or "")


def asset(path):
    f = BASE / "static" / path
    v = int(f.stat().st_mtime) if f.exists() else 0
    return url_for("static", filename=path, v=v)


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


def wa_url(text=""):
    n = digits(get_settings()["whatsapp"])
    if not n:
        return url_for("contact")
    return "https://wa.me/%s?text=%s" % (n, quote("Hello Bansuri Studio, " + text))


@app.context_processor
def inject():
    s = get_settings()
    return dict(S=s, wa=wa_url, wa_on=bool(digits(s["whatsapp"])), csrf_token=csrf_token,
                asset=asset, SERVICES=SERVICES, is_admin=bool(session.get("admin")),
                now_year=datetime.now(IST).year)


@app.template_filter("lines")
def f_lines(s):
    return [x.strip() for x in (s or "").splitlines() if x.strip()]


@app.template_filter("digits")
def f_digits(s):
    return digits(s)


@app.template_filter("upl")
def f_upl(name):
    return url_for("static", filename="uploads/" + name) if name else ""


@app.template_filter("ist")
def f_ist(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(IST).strftime("%d %b %Y, %I:%M %p")
    except (TypeError, ValueError):
        return iso or ""


@app.template_filter("ago")
def f_ago(iso):
    try:
        secs = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return ""
    for n, label in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if secs >= n:
            c = int(secs // n)
            return "%d %s%s ago" % (c, label, "" if c == 1 else "s")
    return "just now"


@app.template_filter("clip")
def f_clip(s, n=80):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def customer_wa(phone, name):
    n = digits(phone)
    if len(n) == 10:
        n = "91" + n
    return "https://wa.me/%s?text=%s" % (n, quote("Hello %s, this is Bansuri Studio. Thanks for your enquiry." % name))


app.jinja_env.globals["customer_wa"] = customer_wa


# --------------------------------------------------------------------------
# Security: CSRF, headers, rate limits
# --------------------------------------------------------------------------
@app.before_request
def csrf_protect():
    if request.method == "POST":
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400)


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; script-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.path.startswith("/admin"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


_hits = {}


def rate_limited(bucket, limit, window):
    """True if this client already used `limit` attempts within `window` seconds."""
    key = (bucket, request.remote_addr)
    now = time.time()
    recent = [t for t in _hits.get(key, []) if now - t < window]
    _hits[key] = recent
    if len(recent) >= limit:
        return True
    return False


def note_hit(bucket):
    _hits.setdefault((bucket, request.remote_addr), []).append(time.time())


# --------------------------------------------------------------------------
# Public pages
# --------------------------------------------------------------------------
def live(table, where="", args=(), order="sort, id", limit=""):
    return q("SELECT * FROM %s WHERE published=1 %s ORDER BY %s %s" % (table, where, order, limit), args)


@app.route("/")
def home():
    return render_template(
        "home.html", active="home",
        work=live("work", order="is_sample, sort, id", limit="LIMIT 3"),
        reviews=live("reviews"))


@app.route("/work")
def work():
    items = live("work")
    cats = [c for c in WORK_CATS if any(i["category"] == c for i in items)]
    return render_template("work.html", active="work", items=items, cats=cats)


@app.route("/packages")
def packages():
    return render_template("packages.html", active="packages", pkgs=live("packages", "AND kind='reel'"))


@app.route("/websites")
def websites():
    return render_template("websites.html", active="websites",
                           pkgs=live("packages", "AND kind='website'"), projects=live("projects"))


@app.route("/about")
def about():
    return render_template("about.html", active="about")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        sent = session.pop("sent", None)
        service = request.args.get("service", "")
        return render_template(
            "contact.html", active="contact", faqs=live("faqs"), sent=sent,
            form=dict(name="", phone="", message=(request.args.get("msg") or "")[:300],
                      service=service if service in SERVICES else SERVICES[0]), errors={})

    wants_json = request.headers.get("X-Requested-With") == "fetch"
    form = {k: (request.form.get(k) or "").strip() for k in ("name", "phone", "service", "message")}
    errors = {}
    if len(form["name"]) < 2:
        errors["name"] = "Please enter your name."
    elif len(form["name"]) > 80:
        errors["name"] = "Please keep your name under 80 characters."
    if not re.fullmatch(r"\+?[0-9\s-]{10,15}", form["phone"]):
        errors["phone"] = "Enter a valid phone number (10 to 15 digits)."
    if form["service"] not in SERVICES:
        errors["service"] = "Choose what you need."
    if len(form["message"]) < 10:
        errors["message"] = "Please tell us a little about your project (at least 10 characters)."
    elif len(form["message"]) > 1000:
        errors["message"] = "Please keep your message under 1000 characters."

    if not errors and request.form.get("company"):
        # Honeypot field filled in: a bot. Pretend it worked, store nothing.
        return _contact_done(wants_json, form, saved=False)
    if not errors and rate_limited("contact", 5, 600):
        errors["message"] = "Too many messages from this device. Please wait a few minutes or use WhatsApp."
    if errors:
        if wants_json:
            return jsonify(ok=False, errors=errors), 422
        return render_template("contact.html", active="contact", faqs=live("faqs"), sent=None,
                               form=form, errors=errors), 422
    note_hit("contact")
    ex("INSERT INTO enquiries(name,phone,service,message,created_at) VALUES(?,?,?,?,?)",
       (form["name"], form["phone"], form["service"], form["message"],
        datetime.now(timezone.utc).isoformat(timespec="seconds")))
    return _contact_done(wants_json, form, saved=True)


def _contact_done(wants_json, form, saved):
    text = "I’m %s (%s). I need: %s. %s" % (form["name"], form["phone"], form["service"], form["message"])
    link = wa_url(text[:700])
    if wants_json:
        return jsonify(ok=True, wa=link, name=form["name"], whatsapp=link.startswith("https://wa.me/"))
    session["sent"] = dict(name=form["name"], wa=link, whatsapp=link.startswith("https://wa.me/"))
    return redirect(url_for("contact"))


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /admin\n", mimetype="text/plain")


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html", active=""), 404


@app.errorhandler(400)
def bad_request(_e):
    return Response("The page expired. Go back, refresh it and try again.", 400)


@app.errorhandler(413)
def too_large(_e):
    flash("That file is too large. Videos can be up to 60 MB and images up to 8 MB.", "error")
    return redirect(request.referrer or url_for("admin_home"))


# --------------------------------------------------------------------------
# Admin: authentication
# --------------------------------------------------------------------------
def has_password():
    return bool(q("SELECT 1 FROM settings WHERE key='admin_hash'", one=True))


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrapper


@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    if has_password():
        abort(404)
    err = ""
    if request.method == "POST":
        pw, pw2 = request.form.get("password", ""), request.form.get("password2", "")
        if len(pw) < 8:
            err = "Use at least 8 characters."
        elif pw != pw2:
            err = "The two passwords don’t match."
        else:
            ex("INSERT INTO settings(key,value) VALUES('admin_hash',?)", (generate_password_hash(pw),))
            session.clear()
            session["admin"] = True
            session.permanent = True
            flash("Admin password saved. Welcome to your dashboard.", "ok")
            return redirect(url_for("admin_home"))
    return render_template("admin/auth.html", mode="setup", err=err)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not has_password():
        return redirect(url_for("admin_setup"))
    if session.get("admin"):
        return redirect(url_for("admin_home"))
    err = ""
    if request.method == "POST":
        if rate_limited("login", 5, 300):
            err = "Too many tries. Wait 5 minutes and try again."
        else:
            row = q("SELECT value FROM settings WHERE key='admin_hash'", one=True)
            if row and check_password_hash(row["value"], request.form.get("password", "")):
                session.clear()
                session["admin"] = True
                session.permanent = True
                return redirect(url_for("admin_home"))
            note_hit("login")
            err = "That password isn’t right."
    return render_template("admin/auth.html", mode="login", err=err)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin/password", methods=["GET", "POST"])
@login_required
def admin_password():
    err = ""
    if request.method == "POST":
        row = q("SELECT value FROM settings WHERE key='admin_hash'", one=True)
        cur, pw, pw2 = (request.form.get(k, "") for k in ("current", "password", "password2"))
        if not check_password_hash(row["value"], cur):
            err = "Your current password isn’t right."
        elif len(pw) < 8:
            err = "Use at least 8 characters."
        elif pw != pw2:
            err = "The two new passwords don’t match."
        else:
            set_setting("admin_hash", generate_password_hash(pw))
            flash("Password changed.", "ok")
            return redirect(url_for("admin_home"))
    return render_template("admin/password.html", err=err, nav="password")


# --------------------------------------------------------------------------
# Admin: dashboard and enquiries
# --------------------------------------------------------------------------
@app.route("/admin")
@login_required
def admin_home():
    counts = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) n FROM enquiries GROUP BY status")}
    samples = sum(q("SELECT COUNT(*) n FROM %s WHERE is_sample=1" % t, one=True)["n"]
                  for t in ("work", "reviews", "projects"))
    return render_template(
        "admin/dashboard.html", nav="home", counts=counts, total=sum(counts.values()),
        recent=q("SELECT * FROM enquiries ORDER BY id DESC LIMIT 6"), samples=samples,
        no_wa=not digits(get_settings()["whatsapp"]),
        sizes={k: q("SELECT COUNT(*) n FROM %s" % t, one=True)["n"] for k, t in
               (("Work items", "work"), ("Reviews", "reviews"), ("Packages", "packages"),
                ("Website projects", "projects"), ("FAQs", "faqs"))})


@app.route("/admin/enquiries")
@login_required
def admin_enquiries():
    status = request.args.get("status", "all")
    if status in dict(STATUSES):
        rows = q("SELECT * FROM enquiries WHERE status=? ORDER BY id DESC", (status,))
    else:
        status, rows = "all", q("SELECT * FROM enquiries ORDER BY id DESC")
    return render_template("admin/enquiries.html", nav="enquiries", rows=rows, status=status,
                           statuses=STATUSES)


@app.route("/admin/enquiries/<int:eid>/status", methods=["POST"])
@login_required
def admin_enquiry_status(eid):
    st = request.form.get("status")
    if st in dict(STATUSES):
        ex("UPDATE enquiries SET status=? WHERE id=?", (st, eid))
    return redirect(request.referrer or url_for("admin_enquiries"))


@app.route("/admin/enquiries/<int:eid>/delete", methods=["POST"])
@login_required
def admin_enquiry_delete(eid):
    ex("DELETE FROM enquiries WHERE id=?", (eid,))
    flash("Enquiry deleted.", "ok")
    return redirect(request.referrer or url_for("admin_enquiries"))


def _csv_safe(v):
    v = str(v or "")
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@app.route("/admin/enquiries.csv")
@login_required
def admin_enquiries_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date (IST)", "Name", "Phone", "Service", "Message", "Status"])
    for r in q("SELECT * FROM enquiries ORDER BY id DESC"):
        w.writerow([f_ist(r["created_at"]), _csv_safe(r["name"]), _csv_safe(r["phone"]),
                    r["service"], _csv_safe(r["message"]), r["status"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=bansuri-enquiries.csv"})


# --------------------------------------------------------------------------
# Admin: generic content editor (work, reviews, packages, projects, FAQs)
# --------------------------------------------------------------------------
def F(name, label, type="text", **kw):
    return dict(name=name, label=label, type=type, **kw)


STARS = [(str(n), "%d star%s" % (n, "" if n == 1 else "s")) for n in (5, 4, 3, 2, 1)]
PUBLISH = F("published", "Show on website", "bool", default=1)

ENTITIES = {
    "work": dict(
        table="work", label="Work", singular="work item", thumb=True,
        intro="Reels, promotions, photos and website walkthroughs. The first items show first on the Work page.",
        cols=[("title", "Title"), ("category", "Category")],
        fields=[
            F("title", "Title", required=True, max=80),
            F("category", "Category", "select", choices=[(c, c) for c in WORK_CATS]),
            F("video", "Video", "video", hint="MP4 or WebM, up to 60 MB. A vertical 9:16 reel works best."),
            F("thumb", "Cover image", "image", hint="JPG, PNG or WebP, up to 8 MB. Shown before the video plays."),
            F("color", "Background colour", "color", default="#2f6b52",
              hint="Shown behind the cover image, or on its own if there is no image."),
            F("is_sample", "This is a placeholder", "bool", hint="Shows a ‘Sample slot’ label. Untick it for real work."),
            PUBLISH]),
    "reviews": dict(
        table="reviews", label="Reviews", singular="review",
        intro="Only add reviews from real clients, with their permission.",
        cols=[("name", "Client"), ("text", "Review")],
        fields=[
            F("name", "Client name", required=True, max=60),
            F("role", "Business or role", max=80, hint="For example: Salon owner"),
            F("text", "Review", "textarea", required=True, max=400),
            F("stars", "Rating", "select", choices=STARS, default="5"),
            F("is_sample", "This is a sample review", "bool", hint="Shows a ‘Sample reviews’ note on the site. Untick it for real reviews."),
            PUBLISH]),
    "packages": dict(
        table="packages", label="Packages", singular="package",
        intro="Reel packages show on the Packages page. Website packages show on the Websites page.",
        cols=[("name", "Package"), ("kind", "Type"), ("price", "Price")],
        fields=[
            F("kind", "Type", "select", choices=[("reel", "Reel and video package"), ("website", "Website package")]),
            F("name", "Name", required=True, max=60),
            F("price", "Price", required=True, max=30, hint="Type it as it should appear, for example ₹1,799"),
            F("unit", "Price note", max=30, hint="Optional. For example: / reel or / month"),
            F("features", "What’s included", "textarea", required=True, max=800, rows=6, hint="One point per line."),
            F("highlight", "Highlight as the best choice", "bool"),
            F("wa_message", "Message to pre-fill", "textarea", max=300, rows=3,
              hint="Appears in the enquiry form when someone chooses this package."),
            PUBLISH]),
    "projects": dict(
        table="projects", label="Website projects", singular="website project", thumb=True,
        intro="Websites you have built. They show on the Websites page.",
        cols=[("title", "Project"), ("url", "Link")],
        fields=[
            F("title", "Project name", required=True, max=80),
            F("description", "Short description", "textarea", max=300, rows=3),
            F("url", "Website link", "url", hint="Leave empty to show ‘Link coming soon’."),
            F("thumb", "Screenshot", "image", hint="Optional. JPG, PNG or WebP, up to 8 MB."),
            F("color", "Background colour", "color", default="#2f6b52"),
            F("is_sample", "This is a placeholder", "bool", hint="Shows a ‘Sample slot’ label. Untick it for real projects."),
            PUBLISH]),
    "faqs": dict(
        table="faqs", label="FAQs", singular="question",
        intro="Questions and answers shown on the Contact page.",
        cols=[("question", "Question"), ("answer", "Answer")],
        fields=[
            F("question", "Question", required=True, max=160),
            F("answer", "Answer", "textarea", required=True, max=600, rows=4),
            PUBLISH]),
}

SETTINGS_FIELDS = [
    F("whatsapp", "WhatsApp number", "phone", hint="With country code, for example 919876543210. All WhatsApp buttons use this."),
    F("phone_display", "Phone number to display", max=40, hint="For example: +91 98765 43210"),
    F("email", "Email", "email", max=120),
    F("instagram_url", "Instagram link", "url"),
    F("instagram_handle", "Instagram name", max=40),
    F("address", "Location", max=120),
    F("reel_note", "Note under reel packages", "textarea", max=400, rows=2),
    F("web_note", "Note under website packages", "textarea", max=500, rows=3),
]

FILE_RULES = {
    "video": dict(ext={"mp4", "webm", "m4v"}, max=60 * 1024 * 1024, label="MP4 or WebM video"),
    "image": dict(ext={"jpg", "jpeg", "png", "webp"}, max=8 * 1024 * 1024, label="JPG, PNG or WebP image"),
}


def _sniff(kind, head):
    if kind == "image":
        return (head[:3] == b"\xff\xd8\xff" or head[:8] == b"\x89PNG\r\n\x1a\n"
                or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))
    return head[4:8] == b"ftyp" or head[:4] == b"\x1a\x45\xdf\xa3"


def save_upload(file, kind):
    rule = FILE_RULES[kind]
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in rule["ext"]:
        return None, "Use a %s." % rule["label"]
    head = file.stream.read(16)
    file.stream.seek(0)
    if not _sniff(kind, head):
        return None, "This doesn’t look like a valid %s." % rule["label"]
    name = secrets.token_hex(8) + "." + ext
    file.save(UPLOADS / name)
    if (UPLOADS / name).stat().st_size > rule["max"]:
        (UPLOADS / name).unlink(missing_ok=True)
        return None, "This file is too large (limit %d MB)." % (rule["max"] // 1048576)
    return name, None


def remove_upload(name):
    if name and re.fullmatch(r"[A-Za-z0-9._-]+", name):
        (UPLOADS / name).unlink(missing_ok=True)


def clean_value(f, raw):
    """Validate one non-file field. Returns (value, error)."""
    t = f["type"]
    v = (raw or "").strip()
    if f.get("required") and not v:
        return v, "This field is required."
    limit = f.get("max", 1000 if t == "textarea" else 200)
    if len(v) > limit:
        return v, "Keep this under %d characters." % limit
    if t == "select" and v not in [c[0] for c in f["choices"]]:
        return v, "Choose one of the options."
    if t == "color" and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
        return v, "Pick a colour."
    if t == "url" and v:
        if not re.match(r"https?://", v, re.I):
            v = "https://" + v
        if re.search(r"\s", v) or "." not in v:
            return v, "Enter a full web address, for example https://example.com."
    if t == "email" and v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
        return v, "Enter a valid email address."
    if t == "phone" and v:
        n = digits(v)
        if len(n) == 10:
            n = "91" + n
        if not 11 <= len(n) <= 15:
            return v, "Enter the number with country code, for example 919876543210."
        v = n
    return v, None


def entity(ent):
    E = ENTITIES.get(ent)
    if not E:
        abort(404)
    return E


def next_sort(table):
    return (q("SELECT COALESCE(MAX(sort),0)+1 n FROM %s" % table, one=True)["n"])


@app.route("/admin/<ent>")
@login_required
def admin_list(ent):
    E = entity(ent)
    rows = q("SELECT * FROM %s ORDER BY sort, id" % E["table"])
    choices = {f["name"]: dict(f["choices"]) for f in E["fields"] if f["type"] == "select"}
    return render_template("admin/list.html", nav=ent, ent=ent, E=E, rows=rows, choices=choices)


@app.route("/admin/<ent>/new", methods=["GET", "POST"])
@app.route("/admin/<ent>/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit(ent, item_id=None):
    E = entity(ent)
    row = None
    if item_id:
        row = q("SELECT * FROM %s WHERE id=?" % E["table"], (item_id,), one=True)
        if not row:
            abort(404)
    values = {f["name"]: (row[f["name"]] if row else f.get("default", "")) for f in E["fields"]}
    errors = {}
    if request.method == "POST":
        data, new_files, old_files = {}, [], []
        for f in E["fields"]:
            n, t = f["name"], f["type"]
            if t == "bool":
                data[n] = 1 if request.form.get(n) else 0
            elif t in ("video", "image"):
                cur = row[n] if row else ""
                data[n] = cur
                if request.form.get("remove_" + n):
                    data[n] = ""
                    old_files.append(cur)
                up = request.files.get(n)
                if up and up.filename:
                    name, err = save_upload(up, t)
                    if err:
                        errors[n] = err
                    else:
                        new_files.append(name)
                        if cur:
                            old_files.append(cur)
                        data[n] = name
            else:
                data[n], err = clean_value(f, request.form.get(n))
                if err:
                    errors[n] = err
        if errors:
            for fn in new_files:
                remove_upload(fn)
            values.update(data)
            for f in E["fields"]:
                if f["type"] in ("video", "image"):
                    values[f["name"]] = row[f["name"]] if row else ""
            flash("Some fields need your attention.", "error")
        else:
            cols = [f["name"] for f in E["fields"]]
            if row:
                ex("UPDATE %s SET %s WHERE id=?" % (E["table"], ",".join(c + "=?" for c in cols)),
                   [data[c] for c in cols] + [item_id])
            else:
                ex("INSERT INTO %s(%s,sort) VALUES(%s)" % (E["table"], ",".join(cols), ",".join("?" * (len(cols) + 1))),
                   [data[c] for c in cols] + [next_sort(E["table"])])
            for fn in set(old_files):
                if fn and fn != data.get("video") and fn != data.get("thumb"):
                    remove_upload(fn)
            flash("Saved.", "ok")
            return redirect(url_for("admin_list", ent=ent))
    return render_template("admin/form.html", nav=ent, ent=ent, E=E, row=row, values=values, errors=errors)


@app.route("/admin/<ent>/<int:item_id>/delete", methods=["POST"])
@login_required
def admin_delete(ent, item_id):
    E = entity(ent)
    row = q("SELECT * FROM %s WHERE id=?" % E["table"], (item_id,), one=True)
    if row:
        for f in E["fields"]:
            if f["type"] in ("video", "image"):
                remove_upload(row[f["name"]])
        ex("DELETE FROM %s WHERE id=?" % E["table"], (item_id,))
        flash("Deleted.", "ok")
    return redirect(url_for("admin_list", ent=ent))


@app.route("/admin/<ent>/<int:item_id>/toggle", methods=["POST"])
@login_required
def admin_toggle(ent, item_id):
    E = entity(ent)
    ex("UPDATE %s SET published = 1 - published WHERE id=?" % E["table"], (item_id,))
    return redirect(url_for("admin_list", ent=ent))


@app.route("/admin/<ent>/<int:item_id>/move", methods=["POST"])
@login_required
def admin_move(ent, item_id):
    E = entity(ent)
    ids = [r["id"] for r in q("SELECT id FROM %s ORDER BY sort, id" % E["table"])]
    if item_id in ids:
        i = ids.index(item_id)
        j = i - 1 if request.form.get("dir") == "up" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
        for pos, rid in enumerate(ids, 1):
            db().execute("UPDATE %s SET sort=? WHERE id=?" % E["table"], (pos, rid))
        db().commit()
    return redirect(url_for("admin_list", ent=ent))


@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
def admin_settings():
    values = dict(get_settings())
    errors = {}
    if request.method == "POST":
        clean = {}
        for f in SETTINGS_FIELDS:
            clean[f["name"]], err = clean_value(f, request.form.get(f["name"]))
            if err:
                errors[f["name"]] = err
        if errors:
            values.update(clean)
            flash("Some fields need your attention.", "error")
        else:
            for k, v in clean.items():
                set_setting(k, v)
            flash("Settings saved.", "ok")
            return redirect(url_for("admin_settings"))
    return render_template("admin/settings.html", nav="settings", fields=SETTINGS_FIELDS,
                           values=values, errors=errors)


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
