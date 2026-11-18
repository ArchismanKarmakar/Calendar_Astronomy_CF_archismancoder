// Runs as `npm run build` on Cloudflare: makes sure the GNU FDL text is served with the site,
// so a calendar that uses a GFDL photo (e.g. Luc Viatour's Andromeda) can print the licence
// as its last page. Never fails the build: without the file, the site refuses GFDL photos.
import { existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";

const OUT = "site/data/licences/fdl-1.3.txt";
const URL_ = "https://www.gnu.org/licenses/fdl-1.3.txt";

if (existsSync(OUT) && statSync(OUT).size > 15000) {
  console.log(`${OUT} already present`);
} else {
  try {
    const r = await fetch(URL_, { headers: { "user-agent": "DeepSpaceExplorer2027-build/1.0" } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const t = await r.text();
    if (!t.includes("GNU Free Documentation License") || t.length < 15000) throw new Error("unexpected content");
    mkdirSync("site/data/licences", { recursive: true });
    writeFileSync(OUT, t);
    console.log(`saved ${OUT} (${t.length} chars)`);
  } catch (e) {
    console.warn(`!! could not fetch ${URL_} (${e.message}); GFDL photos will be refused by the site`);
  }
}
