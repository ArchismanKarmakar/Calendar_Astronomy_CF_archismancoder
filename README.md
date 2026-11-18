# The Deep Space Explorer 2027

A free 2027 astronomy calendar site. Visitors first see ready-made calendars to download
(six regional editions, wall and desk), then a maker: their city (63 cities and time
zones), public holidays for any of 245 countries or none, wall or desk format, paper size
and pictures — any ESO or ESA/Hubble image, or their own astrophoto. Their browser then
builds a print-ready PDF with the same Python code you use locally (through Pyodide), so
there is no server to run and nothing to pay for beyond Cloudflare's free plan.

The site never offers the Python kit. Keep this GitHub repository **private** —
Cloudflare Pages deploys private repos just the same. (The browser does need the
rendering code, so `site/py/kit.zip` is fetchable by anyone who looks for it; the data
tools, image fetchers and build scripts are not in it.)

```
site/        the website (static files, served as-is), incl. terms.html and downloads/
functions/   the two small API handlers (/api/img and /api/meta), wired up by src/index.js
src/         the Worker entry point (routes /api/*, serves the site)
lib/         code shared by the handlers
tools/       cf_geoblock.py: block countries on every domain, Worker and Pages project
kit/         the Python calendar kit (build PDFs locally; also generates site/ data)
```

## Publish on Cloudflare

1. **Refresh the site data with your real images** (the copy in this repo was made
   from preview images):

   ```bash
   cd kit
   pip install -r requirements.txt
   python fetch_images.py        # skip if photos/options already has the images
   python make_site.py           # site data, thumbnails, holidays, ready-made PDFs, previews
   python dev_server.py          # optional: check http://localhost:8027
   ```

2. **Fill in `site/config.js`**: the donation methods you use (UPI ID, Ko-fi, Buy Me a
   Coffee, PayPal, GitHub Sponsors) and, if you like, a contact e-mail for the Terms
   page. Empty entries stay hidden. Have someone qualified review `site/terms.html`
   before launch; it is a sensible starting point, not legal advice.

3. **Push to GitHub** (the `.gitignore` keeps photos, fonts and build output out):

   ```bash
   git init && git add . && git commit -m "Deep Space Explorer 2027 site"
   git branch -M main
   git remote add origin https://github.com/<you>/deep-space-explorer-2027.git
   git push -u origin main
   ```

4. **Cloudflare dashboard → Workers & Pages → Create → Import a repository**, pick the
   repo, then:
   - Build command: **`npm run build`** (or leave it empty). It only downloads the GNU FDL
     text into `site/data/licences/`, which the calendar needs when a GFDL photo such as
     Luc Viatour's Andromeda is used. Without that file the site leaves GFDL photos out.
   - Deploy command: **`npx wrangler deploy`** (the default; `wrangler.toml` already points
     at `site/` for the pages and `src/index.js` for `/api/img` and `/api/meta`)
   - Root directory: *(leave empty — the repo root)*

   Cloudflare deploys again on every push.

5. **Custom domain**: open the project → Settings → Domains & Routes → Add → Custom
   domain → `calendar.archismancoder.com` (or `astro.archismancoder.com`). Because
   archismancoder.com is already on Cloudflare DNS, the record and certificate are created
   for you.

## Block countries on every site

The Worker only answers on `calendar.archismancoder.com` (`workers_dev = false`,
`preview_urls = false` in `wrangler.toml`), so your zone's WAF rules always apply to it, and
its API routes also refuse the countries in `BLOCKED_COUNTRIES`.

Don't use Cloudflare Access for this: Access is a login gate, and a policy built on
countries denies everyone who doesn't match an Allow rule, so the whole site goes dark.
Use a WAF custom rule (Security → Security rules → Custom rules, action Block):

    (ip.src.country in {"PK" "TR" "CN" "BD" "AZ" "KP"})

A zone rule covers every hostname on that domain, including Pages and Workers custom
domains. It does not cover `*.workers.dev` or `*.pages.dev`, and the free plan has no
account-wide WAF, so each domain needs its own rule. `tools/cf_geoblock.py` does all of
it in one go, a dry run first:

    export CF_API_TOKEN=...    # permissions are listed at the top of the script
    python3 tools/cf_geoblock.py --countries PK,TR,CN,BD,AZ,KP
    python3 tools/cf_geoblock.py --countries PK,TR,CN,BD,AZ,KP --apply --pages-redirect

## Picture previews

The picker loads each preview, in this order, from `site/thumbs/` (written by
`make_site.py` from your downloaded images), then straight from the observatory's own CDN
(cdn.eso.org, cdn.esahubble.org, cdn.esawebb.org, noirlab.edu), then through `/api/img`.
So previews show even if the site's API is down. The full-size images for a PDF still come
through `/api/img`, because the browser needs to read their pixels and those CDNs don't
allow cross-site reads. If building fails, open
`https://calendar.archismancoder.com/api/img?src=eso&id=eso2320a&r=thumb300y`, which
shows the error.

## Wikimedia Commons photos (Luc Viatour's Andromeda and Triangulum)

`wm-hamois-m31` (Andromeda, default for November) and `wm-hamois-m33` (Triangulum) are
amateur photographs on Wikimedia Commons by Luc Viatour (https://Lucnix.be). Their licence
is checked in two places: by `fetch_images.py` on your machine, and live in each visitor's
browser through the Commons API (Commons allows that), so they appear on the site even if
you don't run the kit. Accepted: public domain, CC0, CC BY, CC BY-SA and the GNU FDL.
Refused: ND and NC.

Luc Viatour's photos are under the GNU Free Documentation License, which asks for the full
licence text to go with every copy. So when one is used, the calendar's "How to read" page
names the photo and its licence, and the PDF ends with a page carrying the whole GFDL 1.3
text. `fetch_images.py` downloads that text for the kit, and `npm run build` fetches it for
the site. Check each file's Commons page yourself before you publish.

## Ready-made calendars

`make_site.py` builds the six regional editions (`--ready IN US-ET US-PT UK CET JP`
by default) at 200 dpi into `site/downloads/` — about 15 MB per wall and 5 MB per desk
calendar, roughly 120 MB in total. Each file must stay under Cloudflare Pages' 25 MB
limit; the script warns if one doesn't (lower `--ready-dpi` or `--ready-quality`).
Editions use their country's public holidays, except Central Europe, which has none.

## How it works

- **Events** are computed by the kit (PyEphem, NASA eclipse tables, IMO meteor data, BAA
  comet forecasts) for each city and saved as `site/data/editions/<CODE>.json`.
- **Generating** happens in a Web Worker (`site/worker.js`): Pyodide loads numpy,
  Pillow, SciPy and ReportLab (~40 MB the first time, then cached by the browser), unpacks
  `py/kit.zip`, and runs `webgen.generate()`, which calls the kit's `build_pdf`.
- **Images**: the observatories' CDNs (ESO, ESA/Hubble, ESA/Webb, NOIRLab) don't allow pages on other sites to read their
  pixels, so `functions/api/img.js` streams them through your domain (only those two
  hosts, only from your own pages, cached at Cloudflare's edge). The browser picks the
  ~4000 px "publication" JPEG when there is one.
- **Other images**: `functions/api/meta.js` reads an image's page for its title, credit,
  object, size and position (the same rules as `kit/imgmeta.py`). The visitor checks
  the credit before using it.
- **Own photos** are read in the browser and never uploaded.
- **Licence**: ESO and ESA/Hubble images are CC BY 4.0. Every page prints the full,
  unshortened credit, and the site and PDFs state that no endorsement is implied.

## Limits worth knowing

- A 300 dpi wall calendar needs about 2 GB of browser memory. It works in desktop
  Chrome, Edge and Firefox; phones should use "Good" (200 dpi) or "Home printer".
- Pyodide loads from jsDelivr by default. To self-host it, copy a Pyodide 0.27.7 "full"
  release into `site/pyodide/` and set `pyodide: "/pyodide/"` in `config.js` (scipy is
  13 MB, under Pages' 25 MB file limit).
- Free Cloudflare Pages allows 100,000 function requests a day. Each calendar uses
  about 13 image requests, and browsers cache them. Ready-made PDFs are static files
  and don't count.
- Holiday data comes from the open-source `holidays` package at the time you run
  `make_site.py`; re-run it occasionally to pick up official changes.
