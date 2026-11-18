# The Deep Space Explorer 2027 — wall & desk calendar kit

Six time-zone editions × two formats, 15 pages each (cover, how-to-read, 12 months,
year at a glance). Text and icons are vector; photos are ESO and ESA/Hubble images only.

## Build the final PDFs — one command

```bash
pip install -r requirements.txt     # includes tzdata, which Windows needs for time zones
python build.py --fetch             # fonts, event data, all image options, then every PDF
```

Output: `out/<EDITION>/NightSky2027_<EDITION>_{Wall,Desk}_<paper>.pdf`.
First run downloads 28 images (mostly 2–30 MB each; a few Hubble originals are larger).
After that, `python build.py` rebuilds in about a minute. Quick proofs: `--dpi 150`.
Subsets: `--editions IN UK --formats wall`.

## Choosing images (2–3 options per page)

```bash
python choose_images.py                         # current picks + writes out/image_options.html
python build.py --compare 08                    # every August option laid out on the real page
python choose_images.py --set 05=heic2506a 08=eso1719a
python build.py
```

`out/image_options.html` shows every downloaded option with its credit and resolution;
each card has its `--set` command ready to copy. Picks are stored in `data/selection.json`.
Changing a month's image also changes that month's target box (object, distance, when
it's highest) — each option carries its own coordinates.

| Page | Default | Other options |
|---|---|---|
| Cover | eso1208a Carina Nebula (VLT) | heic0707a Carina (Hubble, very large file) · eso1237c Seagull Nebula · weic2205a Cosmic Cliffs (Webb) |
| Jan | eso1006a Orion Nebula (VISTA) | eso1701a Orion A cloud (VISTA panorama) · heic0601a Orion (Hubble, very large) |
| Feb | eso1238a Thor's Helmet | eso1237c Seagull Nebula · weic2205a Cosmic Cliffs (Webb) |
| Mar | eso1126a Leo Triplet (VST) | heic1006a M66 (Hubble) |
| Apr | heic0506a Whirlpool M51 | heic0602a Pinwheel M101 · noao1309a Whirlpool (WIYN/NOIRLab) |
| May | eso0007a Sombrero (VLT) | heic2506a Sombrero (Hubble 2025) · opo0328a Sombrero (Hubble 2003) |
| Jun | opo0840a M13 | potw1011a M13 core (3018 px) |
| Jul | eso1403a Lagoon (VST) | heic1808a Lagoon core (Hubble) |
| Aug | heic1501a Pillars of Creation | eso1719a Eagle + Omega nebulae (VST panorama) · weic2216b Pillars (Webb) |
| Sep | **noao-m31 Andromeda (NOIRLab, T.A. Rector & B.A. Wolpa)** — whole galaxy, auto-rotated | heic2501a, heic1502a (Hubble mosaics, jagged edges) |
| Oct | eso1424a Triangulum M33 (VST) | eso1025a Sculptor Galaxy (VISTA) · noao-m33_opt M33 (NOIRLab) |
| Nov | eso1205a Helix (VISTA) | eso0907a Helix (WFI) · noao0307a Helix (Hubble + KPNO) · weic2425a NGC 602 (Webb) |
| Dec | heic0515a Crab Nebula | heic2607a Crab (Hubble 2024) · weic2326a Crab (Webb) |

36 options from ESO, ESA/Hubble, ESA/Webb and NOIRLab, all CC BY 4.0. Only images of at least
~8000 px were added, so they print sharply. `"rotate": "auto"` turns an elongated galaxy to
lie along the photo area (the credit then says "rotated", as CC BY asks). Every one was checked on its source page for ID, exact credit,
pixel size and which download sizes exist. October changed from Hubble's heic1901a, which
offers no high-resolution download (only a ~1280 px JPEG), to ESO's eso1424a.

### Any image on any page

The table lists suggestions; any image in the library can go on any page
(`--set 03=eso1006a` puts the Orion Nebula on March).

**Other ESO or ESA/Hubble images.** Give an ID or a page link. The kit reads the title,
credit, object, size and position from its page, downloads it, and can place it at once:

```bash
python choose_images.py --add eso1733a --slot 05
python choose_images.py --add https://esahubble.org/images/heic1509a/ --slot 03
python choose_images.py --add potw1011a --source esahubble   # potw IDs exist on both sites
```

Read the printed credit against the image's page before printing: it must appear in
full. Fix anything with `--credit`, `--object`, `--ra`, `--dec` and so on.

**Wikimedia Commons.** Many astrophotographers publish under free licences. The kit reads
each file's licence, author and requested credit from Commons and refuses anything that
can't be printed and sold: non-commercial (NC), no-derivatives (ND), GFDL-only, or smaller
than 4000 px. CC BY-SA photos are accepted; the page that uses one is then CC BY-SA too.

```bash
python choose_images.py --add-commons "https://en.wikipedia.org/wiki/Andromeda_Galaxy#/media/File:M31-Andromede-16-09-2023-Hamois.jpg" --slot 09
python choose_images.py --check-commons     # checks data/commons_candidates.json
python choose_images.py --scan-commons "Category:Andromeda Galaxy" --slot 09
```

Usable finds appear in `out/image_options.html` with their thumbnails and add commands.
September prefers the Hamois Andromeda (`wm-hamois-m31`) whenever `fetch_images.py` finds its
licence acceptable, and falls back to NOIRLab's M31 otherwise.

**Photographers' images (AstroBackyard and others).** A credit alone isn't permission:
their photos are copyrighted, so a calendar you publish needs a licence or written permission.
`permission_request.txt` is a ready email. Once someone agrees, add the photo with `--share`
and record the permission; it then appears on the website's picture list too:

```bash
python choose_images.py --custom m31.jpg --share --credit "Photo: A. Photographer" \
    --license "Used with permission" --permission "Email, 20 Nov 2026" \
    --object "Andromeda Galaxy" --catalog M31 --ra 00:42:44 --dec 41:16:09 --rotate auto --slot 09
```

**Your own astrophotos.**

```bash
python choose_images.py --custom m42.jpg --object "Orion Nebula" --catalog M42 \
    --credit "Jane Doe" --ra 05:35:17 --dec -05:23:28 --slot 01
```

Added images are stored in `data/custom_images.json` (own photos are copied to
`photos/custom/`). With `--ra`/`--dec` the page says when the object is highest;
without them it says the position wasn't given.

If a download fails, `fetch_images.py` prints the page to save it from by hand; save the
JPEG as `photos/options/<id>.jpg`. Images saved by the first kit version
(`photos/cover.jpg` etc.) are moved into place automatically.

## Holidays and festivals

`--holidays auto|none|CC` adds public holidays (red); `--festivals auto|none|bengali` adds
regional festivals in marigold. The India editions show Bengali festivals by default:
Saraswati Puja (11 Feb), Bishwakarma Puja (17 Sep), Durga Puja Saptami–Navami (6–8 Oct),
Bijoya Dashami (9 Oct) and Kojagari Lakshmi Puja (14 Oct). India also gets Netaji Subhas
Chandra Bose's Birthday (23 Jan) and "Gandhi's Birthday" (2 Oct). Change or add sets in
`holidays_data.py` (`FESTIVALS`, `OVERRIDES`).

## Editions

The six editions below are built by default. Any of the website's 63 cities works too:
`python build.py --editions AU-E NZ IN-KOL --formats desk` (run `python build.py -h`
for the codes). South of the equator the full-moon names shift by six months and the
Harvest Moon is the one nearest the March equinox.

| Code | Edition | Time zone (DST-aware) | Reference city* | Week starts | Wall | Desk |
|---|---|---|---|---|---|---|
| US-PT | US Pacific | America/Los_Angeles | Los Angeles | Sunday | Tabloid 11×17 in | 8.5×5.5 in |
| US-ET | US Eastern | America/New_York | New York | Sunday | Tabloid 11×17 in | 8.5×5.5 in |
| UK | UK & Ireland | Europe/London | London | Monday | A3 | A5 landscape |
| CET | Central Europe | Europe/Berlin | Berlin | Monday | A3 | A5 landscape |
| IN | India | Asia/Kolkata | New Delhi | Sunday | A3 | A5 landscape |
| JP | Japan | Asia/Tokyo | Tokyo | Sunday | A3 | A5 landscape |

\*Used only for place-dependent items: eclipse visibility and coverage, which Moon–star
occultations are visible, and when each month's target is highest. Add an edition by adding
an entry to `EDITIONS` in `localize.py`. All editions are northern-hemisphere; a southern
edition needs its own target list.

**Why editions differ, concretely:** Saturn's opposition is 00:20 UTC on Oct 18 — that's
Oct 17 in Los Angeles and Oct 18 in London and Delhi. The Aug 2 total solar eclipse is a
52% partial from London, 45% from Berlin, 17% from New Delhi, and not visible from the US
or Tokyo — each edition says so on its own page.

## What's on each month

- Full-bleed photo that dissolves into a blurred, darkened copy of itself behind the grid.
- **Target of the month** (the photo's object): catalogue IDs, type, constellation, distance,
  the local time it's highest from the reference city, and that month's dark-sky nights.
- **Date boxes**: Moon phase with local time; Moon illumination at 21:00 local (≤25% tinted
  as a dark night); full-Moon names; up to four labelled events with icons.
- **This month**: every event with icon, local date/time and a one-line note.

## Data (175 events computed, ~150 per edition after local filtering)

| Source | What |
|---|---|
| PyEphem (VSOP87/ELP), computed here | Moon phases, equinoxes/solstices, oppositions, Mercury/Venus elongations, Moon–planet and planet–planet conjunctions, Moon–star occultations, supermoon/micromoon, perihelion/aphelion, local eclipse coverage, nightly illumination |
| [NASA GSFC, Eclipses During 2027](https://eclipse.gsfc.nasa.gov/OH/OH2027.html) | Eclipse times and magnitudes |
| [IMO Meteor Shower Calendar 2027](https://www.imo.net/files/data/calendar/cal2027.pdf) | Peak times, solar longitudes, ZHR, Leonid trail encounters |
| [BAA Comet Prospects for 2027](https://people.ast.cam.ac.uk/~jds/preds27.pdf), [Yoshida's catalogue](http://www.aerith.net/comet/future-n.html) | 12 comet entries (11 comets; Encke appears twice) |

**Corrections vs the previous version** (from the official IMO 2027 calendar): Lyrids are
Apr 23 (was 22), η-Aquariids May 6 (was 5), Perseids Aug 13 09h UT (was 12), Orionids Oct 22
(was 21), Leonids Nov 18 (was 17). Added Southern/Northern Taurids and two possible Leonid
outbursts. Meteor peaks are placed on the evening that starts the peak night; when the peak
falls in local daylight the note says so.

**Filters applied** (so nothing listed is unobservable): Moon–planet pairs within 5° and ≥15°
from the Sun; planet pairs within 5° and ≥20° from the Sun (this drops Venus–Jupiter on
Aug 26, 0.5° apart but only 4° from the Sun); occultations only where the Moon is >5° up in
darkness at the reference city.

**Not included on purpose:** asteroid close approaches (none bright in 2027; Apophis's
famous pass is 2029) and speculative "great comet" predictions. Comet magnitudes are BAA
forecasts and can be wrong in either direction — recheck COBS or the BAA pages before print.

## Images and licence

All options are ESO or ESA/Hubble, **CC BY 4.0** — commercial use allowed with credit
(`data/image_manifest.json` holds IDs, titles, credits, coordinates and source pages).
Rules from ESO's and ESA/Hubble's usage pages:

- The full credit must appear, unshortened, with the image. Each page prints it on the
  photo, and page 2 lists all 13 in use.
- No ESO/ESA logos, and nothing implying endorsement (page 2 says so).
- If you alter an image beyond resize/crop, add a note after the credit.

### Framing (v4)

- **Automatic subject framing.** With `"focus": null` (the default) each crop is placed where
  the picture holds the most light, so a narrow desk panel shows the galaxy or nebula rather
  than the dark sky beside it. Wide crops keep the image's own centre.
- **Mosaic edges.** Panoramas with black, saw-toothed tile gaps (Hubble's Andromeda,
  M13, the Crab) are detected automatically. Bands are trimmed to the strip that is solid
  picture across the page, and other crops dissolve their tile edges softly into the sky.
- **Override anything** per option in `data/image_manifest.json`:
  `"focus": [0.40, 0.55]` = crop centre as fractions of width/height;
  `"zoom": 1.6` (band images) = show the central 1/1.6 of the panorama's width.
  Check a change with `python build.py --compare 09 --editions IN --formats desk`.

## Print notes

- Bleed is 3 mm (ISO) / 0.125 in (US) on all sides, with TrimBox/BleedBox set in the PDF.
  Send as-is to a print shop; for home printing choose "fit to page".
- All fonts are embedded (checked with `pdffonts`); no text sits outside the trim box.
- Backgrounds are sRGB JPEG at 300 dpi; source images with embedded ICC profiles are
  converted to sRGB first. Most print-on-demand services accept RGB PDFs; ask yours whether
  they want CMYK.
- Desk pages are single-sided landscape sheets for a tent stand or wire binding.

## Customise

- `brand.json` — studio name, title, subtitle.
- `localize.py` — editions, reference cities, week start, paper family.
- `astro_engine.py` — thresholds, comet list, space-history dates.
- `render.py` — colours (`T`, `CAT`), typography (`FONTS`), layouts.

## Legibility checks built in (v4)

- Every line over a photo gets a soft dark halo; the cover title and highlights sit on a
  feathered backdrop; the target card is an opaque glass panel on both formats.
- Secondary text colours were raised (`text2` #DADDE5, `muted` #A9AEC0) for print contrast.
- Credits wrap onto as many lines as they need — never shortened — and lines are balanced.
- THIS MONTH notes wrap to two lines; if a month is too busy, the least important items are
  dropped from the list (they stay in their date boxes).
- The month subtitle sits below the title's descenders (the J of JANUARY), and the cover
  subtitle sits below the old-style 7 of 2027.
- Background cache keys include a hash of `backgrounds.py` and the image's framing, so
  edits never reuse stale backgrounds.

## The website

`make_site.py` writes everything the website needs into `../site` (city data for all
63 cities, the image library and thumbnails, fonts, this Python code as `py/kit.zip`,
and sample page previews). The site runs the same `render.py` in the browser, so its PDFs
match `build.py`. Run it after changing code, images or `brand.json`, then push.

```bash
python make_site.py          # needs the images in photos/options for thumbnails and samples
python dev_server.py         # preview at http://localhost:8027 before pushing
```

## Troubleshooting

- `UnicodeEncodeError ... charmap` (first kit version on Windows): fixed — all files are
  read and written as UTF-8, and JSON is written atomically so a crash can't leave a
  half-written file behind.
- `No time-zone database found`: `pip install tzdata`.
- `HTTP Error 404` on an image: that size doesn't exist for that image; the script now only
  tries the sizes each image's page lists, then falls back to the next.
- A page shows **PLACEHOLDER** in red: its selected image isn't in `photos/options/` yet.
- `note: <id> prints at ~N dpi`: that source is small for the page; consider another option.
