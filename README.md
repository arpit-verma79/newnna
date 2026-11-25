# Bansuri Studio website

A dynamic version of your single `index.html`. It has six real pages, an admin panel
for your work, reviews, prices and FAQs, and a dashboard that saves every enquiry.
Built with Python (Flask) and SQLite. There is no build step.

## Run it on your computer

```
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 for the website and http://127.0.0.1:5000/admin for the admin panel.

**First visit to /admin:** you will be asked to create your admin password.
Do this straight away after putting the site online, before anyone else can.
(Alternatively set the `ADMIN_PASSWORD` environment variable before the first run.)

## Day-to-day use (no code needed)

| Task | Where in /admin |
|---|---|
| Add a reel or photo to the Work page | Work → Add work item (upload video + cover image) |
| Change a price or what a package includes | Packages → Edit |
| Add a real client review | Reviews → Add review |
| Add a website you built | Website projects |
| Change WhatsApp number, Instagram, email | Settings |
| See and reply to enquiries | Enquiries (Reply on WhatsApp button, CSV download) |

Do this first:
1. **Settings:** add your WhatsApp number (with 91, for example `919876543210`). Until then,
   WhatsApp buttons send visitors to the Contact page.
2. **Replace the placeholders.** The dashboard counts them. Items marked "Sample slot" and the
   three "Sample reviews" come from your old page. Untick *placeholder* on real items,
   and hide or delete the rest. Only publish reviews from real clients.

## Putting it online

You need a host that runs Python and keeps files on a **persistent disk**, because the
database and your uploaded videos are stored as files. (Hosts with temporary disks will
delete your content on restart.) Any small Python host or VPS works. Common choices are
PythonAnywhere or a VPS with gunicorn and nginx.

- Entry point: `wsgi.py` (the object is called `application`), or `gunicorn app:app`.
- Run over HTTPS and set these environment variables:
  - `HTTPS=1` makes the login cookie secure-only.
  - `SECRET_KEY` is optional. A random one is created in `instance/secret.key` if not set.
  - `BEHIND_PROXY=1` if you use nginx or a similar proxy in front.
  - `ADMIN_PASSWORD` is optional (see above).
- If you use nginx, allow uploads of at least 80 MB (`client_max_body_size 80m;`).

## Backups (important)

Everything you edit lives in two places. Copy both regularly:
- `instance/data.db` (content and enquiries)
- `static/uploads/` (your videos and images)

## Files

```
app.py            all the server code (pages, admin, enquiries)
templates/        page layouts (templates/admin = admin panel)
static/css        style.css (website), admin.css
static/js         main.js (animations, form, filters), admin.js
static/img        logo, flute, hero photo
static/uploads    your videos and cover images
instance/         created on first run: database and secret key
```

## Security notes

Passwords are hashed, login is rate-limited, every form has CSRF protection, uploads are
checked by type and content, and a strict Content-Security-Policy is set. Change the password
from Admin → Password at any time.
