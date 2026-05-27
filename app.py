import streamlit as st
import asyncio
import csv
import re
import io
import random
import uuid
from datetime import datetime
from urllib.parse import quote_plus
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── Configuratie ─────────────────────────────────────────────────────────────

GEEN_WEBSITE = [
    "treatwell", "mytreatwell", "fresha", "booksy", "planity", "salonkee",
    "salonized", "simplybook", "reservio", "acuityscheduling", "calendly",
    "setmore", "square.site", "booking.com", "wahanda",
    "thuisbezorgd", "takeaway", "deliveroo", "ubereats", "just-eat",
    "tripadvisor", "yelp.", "zomato", "foursquare",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "tiktok.com",
    "google.com", "goo.gl", "/maps", "maps.app",
]

TYPE_SCORES = {
    "restaurant": 9, "cafe": 8, "kapper": 8, "kapsalon": 8, "hair": 7,
    "schoonheidssalon": 8, "nagelsalon": 8, "tandarts": 9, "fysiotherapeut": 9,
    "dokter": 9, "advocaat": 9, "accountant": 9, "notaris": 9,
    "aannemer": 7, "loodgieter": 7, "elektricien": 7, "schilder": 7,
    "bakker": 8, "slager": 7, "bloemenwinkel": 8, "dierenarts": 9,
    "garage": 7, "autorijschool": 8, "sportschool": 9, "yoga": 8,
    "pizzeria": 8, "hotel": 9, "fotograaf": 9, "makelaar": 9, "barbershop": 8,
}

ALLE_CATEGORIEEN = [
    "kapper", "restaurant", "nagelsalon", "schoonheidssalon",
    "tandarts", "fysiotherapeut", "loodgieter", "elektricien",
    "schilder", "aannemer", "bakker", "dierenarts",
    "autorijschool", "sportschool", "fotograaf", "makelaar",
]

# Populaire steden en wijken. Staat jouw locatie er niet tussen, kies dan zelf typen.
ALLE_STEDEN = [
    "Amsterdam", "Rotterdam", "Den Haag", "Utrecht", "Eindhoven",
    "Tilburg", "Groningen", "Almere", "Breda", "Nijmegen",
    "Enschede", "Apeldoorn", "Haarlem", "Arnhem", "Amersfoort",
    "Zwolle", "Leiden", "Dordrecht", "Maastricht", "Emmen",
    "Delft", "Venlo", "Deventer", "Helmond", "Alkmaar",
    "Leeuwarden", "Zaandam", "Purmerend", "Hoorn", "Gouda",
]

POPULAIRE_WIJKEN = [
    "Amsterdam Centrum", "Amsterdam De Pijp", "Amsterdam Jordaan", "Amsterdam Noord",
    "Amsterdam Oud-West", "Amsterdam Oost", "Amsterdam West", "Amsterdam Zuid",
    "Rotterdam Centrum", "Rotterdam Noord", "Rotterdam Kralingen", "Rotterdam Delfshaven",
    "Rotterdam Feijenoord", "Rotterdam Charlois", "Den Haag Centrum", "Den Haag Scheveningen",
    "Den Haag Laak", "Den Haag Escamp", "Den Haag Segbroek", "Utrecht Centrum",
    "Utrecht Lombok", "Utrecht Leidsche Rijn", "Utrecht Overvecht", "Utrecht Kanaleneiland",
    "Eindhoven Centrum", "Eindhoven Strijp", "Eindhoven Woensel", "Tilburg Centrum",
    "Groningen Centrum", "Groningen Helpman", "Almere Stad", "Breda Centrum",
    "Nijmegen Centrum", "Haarlem Centrum", "Arnhem Centrum", "Leiden Centrum",
]

BELGIE_STEDEN = [
    "Brussel, België", "Antwerpen, België", "Gent, België", "Charleroi, België",
    "Luik, België", "Brugge, België", "Namen, België", "Leuven, België",
    "Mechelen, België", "Aalst, België", "La Louvière, België", "Kortrijk, België",
    "Hasselt, België", "Sint-Niklaas, België", "Oostende, België", "Genk, België",
    "Seraing, België", "Roeselare, België", "Moeskroen, België", "Beveren, België",
    "Dendermonde, België", "Beringen, België", "Turnhout, België", "Vilvoorde, België",
    "Lokeren, België",
]

LOCATIE_KEUZES = [
    "Kies een stad of wijk...",
    "🇳🇱 Heel Nederland",
    "🇧🇪 Heel België",
    "🇳🇱🇧🇪 Heel Nederland + België",
    "✏️ Zelf typen...",
] + ALLE_STEDEN + POPULAIRE_WIJKEN + BELGIE_STEDEN

BEDRIJFSTYPEN = [
    "🔀 Alle categorieën (automatisch)",
    "kapper / kapsalon", "restaurant", "café / bar", "pizzeria",
    "nagelsalon", "schoonheidssalon", "tandarts", "fysiotherapeut",
    "dokter / huisarts", "advocaat", "accountant", "notaris",
    "aannemer / bouwbedrijf", "loodgieter", "elektricien", "schilder",
    "bakker", "slager", "bloemenwinkel", "dierenarts",
    "garage / autorijschool", "sportschool / fitness", "yoga / pilates",
    "hotel / B&B", "fotograaf", "makelaar",
    "✏️ Zelf invullen...",
]

ZOEK_MODI = [
    "Bedrijven zonder website",
    "Bedrijven met verouderde website",
    "Allebei",
]

# ── Hulpfuncties ──────────────────────────────────────────────────────────────

def is_echte_website(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    return not any(p in url.lower() for p in GEEN_WEBSITE)


def bereken_score(bedrijf: dict) -> tuple:
    score = 0
    redenen = []
    if bedrijf.get("telefoon"):
        score += 25
        redenen.append(f"📞 {bedrijf['telefoon']}")
    reviews = bedrijf.get("reviews", 0)
    if reviews >= 50:
        score += 30; redenen.append(f"🔥 {reviews} reviews")
    elif reviews >= 20:
        score += 20; redenen.append(f"👍 {reviews} reviews")
    elif reviews >= 5:
        score += 10; redenen.append(f"📊 {reviews} reviews")
    elif reviews > 0:
        score += 5
    rating = bedrijf.get("rating", 0.0)
    if rating >= 4.5:
        score += 20; redenen.append(f"⭐ {rating}/5 uitstekend")
    elif rating >= 4.0:
        score += 15; redenen.append(f"⭐ {rating}/5 goed")
    elif rating >= 3.0:
        score += 8; redenen.append(f"⭐ {rating}/5")
    if bedrijf.get("adres"):
        score += 5; redenen.append("📍 Fysiek adres")
    btype = bedrijf.get("type", "").lower()
    for t, s in TYPE_SCORES.items():
        if t in btype or btype in t:
            score += s * 2; redenen.append("🏢 Hoog-potentieel sector"); break
    return min(score, 100), redenen


async def analyseer_verouderde_website(page, website_url: str) -> tuple:
    redenen = []
    score = 0
    if website_url.startswith("http://"):
        score += 25
        redenen.append("Geen HTTPS")

    try:
        await page.goto(website_url, wait_until="domcontentloaded", timeout=10000)
        await page.wait_for_timeout(1200)
        analyse = await page.evaluate("""
            () => {
                const html = document.documentElement.outerHTML.toLowerCase();
                const text = document.body ? document.body.innerText : "";
                const viewport = document.querySelector('meta[name="viewport"]');
                const tables = document.querySelectorAll('table').length;
                const frames = document.querySelectorAll('frame, frameset').length;
                const scripts = Array.from(document.querySelectorAll('script[src]')).map(s => s.src.toLowerCase());
                const copyright = Array.from(text.matchAll(/(?:©|copyright)\\s*(?:\\d{4}\\s*[-–]\\s*)?(20\\d{2}|19\\d{2})/gi)).map(m => Number(m[1]));
                return {
                    hasViewport: !!viewport,
                    tables,
                    frames,
                    textLength: text.length,
                    oldCopyright: copyright.length ? Math.max(...copyright) : 0,
                    hasFlash: html.includes('.swf') || html.includes('flash player'),
                    hasOldJquery: scripts.some(src => /jquery[-.]1\\.|jquery[-.]2\\./.test(src)),
                    hasUnderConstruction: /under construction|binnenkort online|website in aanbouw|coming soon/i.test(text),
                    hasOldCms: /joomla! 1\\.|joomla! 2\\.|wordpress 3\\.|wordpress 4\\./i.test(html),
                };
            }
        """)
        huidig_jaar = datetime.now().year
        if not analyse.get("hasViewport"):
            score += 20
            redenen.append("Geen mobiele viewport")
        if analyse.get("frames"):
            score += 25
            redenen.append("Gebruikt frames")
        if analyse.get("tables", 0) >= 4:
            score += 15
            redenen.append("Veel layout-tabellen")
        if analyse.get("hasFlash"):
            score += 30
            redenen.append("Flash/SWF gevonden")
        if analyse.get("hasOldJquery"):
            score += 15
            redenen.append("Oude jQuery")
        if analyse.get("hasOldCms"):
            score += 20
            redenen.append("Oude CMS-signalen")
        if analyse.get("hasUnderConstruction"):
            score += 25
            redenen.append("In aanbouw/coming soon")
        copyright_jaar = analyse.get("oldCopyright", 0)
        if copyright_jaar and copyright_jaar <= huidig_jaar - 4:
            score += 20
            redenen.append(f"Copyright uit {copyright_jaar}")
        if analyse.get("textLength", 0) < 250:
            score += 10
            redenen.append("Weinig inhoud")
    except Exception:
        score += 10
        redenen.append("Website traag of lastig te laden")

    return min(score, 100), redenen


# ── Scraping ──────────────────────────────────────────────────────────────────

async def verzamel_urls(page, zoekterm: str, max_te_scannen: int, scan_id: str) -> list:
    url = f"https://www.google.com/maps/search/{quote_plus(zoekterm)}?hl=nl&leadfinder_scan={scan_id}"
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(2500)

    for sel in ['button:has-text("Alles accepteren")', 'button:has-text("Accept all")']:
        try:
            btn = page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1000)
                break
        except Exception:
            pass

    bedrijven = {}
    feed = page.locator('div[role="feed"]')

    for _ in range(10):
        items = await page.locator('a[href*="/maps/place/"]').all()
        for item in items:
            try:
                href = (await item.get_attribute("href", timeout=800)) or ""
                naam = (await item.get_attribute("aria-label", timeout=800)) or ""
                if naam and href and naam not in bedrijven:
                    rating_hint = 0.0
                    reviews_hint = 0
                    try:
                        parent_txt = await item.evaluate(
                            "el => el.closest('[jsaction]') ? el.closest('[jsaction]').innerText : ''"
                        )
                        rm = re.search(r'(\d[.,]\d)', parent_txt)
                        rv = re.search(r'\((\d[\d.]+)\)', parent_txt)
                        if rm:
                            rating_hint = float(rm.group(1).replace(",", "."))
                        if rv:
                            reviews_hint = int(rv.group(1).replace(".", ""))
                    except Exception:
                        pass
                    bedrijven[naam] = {"href": href, "rating_hint": rating_hint, "reviews_hint": reviews_hint}
            except Exception:
                continue

        if len(bedrijven) >= max_te_scannen * 2:
            break
        try:
            if await feed.count() > 0:
                await feed.first.evaluate("el => el.scrollBy(0, 2000)")
            await page.wait_for_timeout(1500)
        except Exception:
            break

    return list(bedrijven.items())


async def check_bedrijf(page, naam: str, info: dict, check_verouderd: bool = False) -> dict:
    href = info["href"]
    data = {
        "naam": naam, "website": None, "telefoon": None, "adres": None,
        "rating": info.get("rating_hint", 0.0), "reviews": info.get("reviews_hint", 0),
        "verouderd_score": 0, "verouderd_redenen": [],
        "type": "", "maps_url": href,
    }
    try:
        await page.goto(href, wait_until="domcontentloaded", timeout=12000)
        await page.wait_for_timeout(600)

        # Rating verfijnen
        if not data["rating"]:
            try:
                els = await page.locator('span[aria-hidden="true"]').all()
                for el in els:
                    txt = (await el.inner_text(timeout=800)).strip()
                    if re.match(r'^\d[.,]\d$', txt):
                        data["rating"] = float(txt.replace(",", "."))
                        break
            except Exception:
                pass

        # Reviews verfijnen
        if not data["reviews"]:
            try:
                el = page.locator('span[aria-label*="recensie"], span[aria-label*="review"]').first
                label = (await el.get_attribute("aria-label", timeout=1500)) or ""
                nums = re.findall(r'[\d.]+', label.replace(",", ""))
                if nums:
                    data["reviews"] = int(float(nums[0]))
            except Exception:
                pass

        # Website — de kern van de check
        try:
            w_el = page.locator('a[data-item-id="authority"]')
            if await w_el.count() > 0:
                href_val = (await w_el.first.get_attribute("href", timeout=1500)) or ""
                if is_echte_website(href_val):
                    data["website"] = href_val
        except Exception:
            pass

        if data["website"] and check_verouderd:
            oud_score, oud_redenen = await analyseer_verouderde_website(page, data["website"])
            data["verouderd_score"] = oud_score
            data["verouderd_redenen"] = oud_redenen

        # Stop meteen als website gevonden en we niet op verouderde websites controleren.
        if data["website"] and not check_verouderd:
            return data

        # Telefoon
        try:
            tel_el = page.locator('[data-item-id*="phone"] .rogA2c').first
            tel_txt = (await tel_el.inner_text(timeout=1500)).strip()
            if re.search(r'[\d\+]', tel_txt):
                data["telefoon"] = tel_txt
        except Exception:
            pass

        # Adres
        try:
            adr_el = page.locator('[data-item-id="address"] .rogA2c').first
            data["adres"] = (await adr_el.inner_text(timeout=1500)).strip()
        except Exception:
            pass

        # Type
        try:
            type_el = page.locator('button[jsaction*="category"] span, span.DkEaL').first
            data["type"] = (await type_el.inner_text(timeout=1500)).strip()
        except Exception:
            pass

    except Exception:
        pass

    return data


async def scan_combinatie(stad: str, categorie: str, max_per_cat: int,
                           al_gezien: set, scan_id: str, zoek_modus: str, log_fn) -> list:
    leads = []
    zoekterm = f"{categorie} {stad}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        ctx = await browser.new_context(
            locale="nl-NL",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        log_fn(f"🔍 **{categorie}** in **{stad}**... scan `{scan_id}`")
        try:
            bedrijven = await verzamel_urls(page, zoekterm, max_per_cat, scan_id)
        except Exception as e:
            log_fn(f"  ⚠️ Kon lijst niet laden: {e}")
            await browser.close()
            return leads

        random.SystemRandom().shuffle(bedrijven)
        log_fn(f"  → {len(bedrijven)} gevonden in lijst")

        for naam, info in bedrijven:
            if len(leads) >= max_per_cat:
                break
            if naam in al_gezien:
                continue
            al_gezien.add(naam)
            try:
                check_verouderd = zoek_modus in ("Bedrijven met verouderde website", "Allebei")
                details = await check_bedrijf(page, naam, info, check_verouderd)
                is_zonder_website = details and not details["website"]
                is_verouderd = details and details["website"] and details.get("verouderd_score", 0) >= 35

                if zoek_modus == "Bedrijven zonder website":
                    lead_match = is_zonder_website
                elif zoek_modus == "Bedrijven met verouderde website":
                    lead_match = is_verouderd
                else:
                    lead_match = is_zonder_website or is_verouderd

                if lead_match:
                    score, redenen = bereken_score(details)
                    if is_verouderd:
                        score = min(100, score + min(details.get("verouderd_score", 0), 40))
                        redenen = redenen + [f"🕰️ Verouderde website ({details['verouderd_score']}/100)"] + details.get("verouderd_redenen", [])
                    details.update({"score": score, "redenen": redenen,
                                    "categorie": categorie, "stad": stad})
                    leads.append(details)
                    log_fn(f"  ✅ **{naam}** — score {score}")
                elif is_verouderd:
                    log_fn(f"  ⬜ {naam[:36]} verouderd, maar buiten filter")
                elif details and details["website"]:
                    log_fn(f"  ⬜ {naam[:36]} heeft website")
                else:
                    log_fn(f"  ⬜ {naam[:36]} past niet binnen filter")
            except Exception:
                log_fn(f"  ⚠️ Fout bij {naam[:30]}")
                continue

        await browser.close()
    return leads


async def run_scraper(steden: list, categorieen: list, max_per_cat: int, scan_id: str, zoek_modus: str, log_fn, progress_fn):
    al_gezien = set()
    alle_leads = []
    totaal_combinaties = len(steden) * len(categorieen)
    gedaan = 0

    for stad in steden:
        for cat in categorieen:
            leads = await scan_combinatie(stad, cat, max_per_cat, al_gezien, scan_id, zoek_modus, log_fn)
            alle_leads.extend(leads)
            gedaan += 1
            progress_fn(gedaan, totaal_combinaties, len(alle_leads))
            log_fn(f"📦 Totaal tot nu: **{len(alle_leads)} leads**")

    alle_leads.sort(key=lambda x: x["score"], reverse=True)
    return alle_leads


def naar_csv(leads: list) -> str:
    output = io.StringIO()
    velden = [
        "score", "naam", "categorie", "stad", "type", "telefoon", "adres",
        "rating", "reviews", "website", "verouderd_score", "verouderd_redenen", "maps_url"
    ]
    w = csv.DictWriter(output, fieldnames=velden, extrasaction="ignore")
    w.writeheader()
    for l in leads:
        row = {k: l.get(k, "") for k in velden}
        if isinstance(row.get("verouderd_redenen"), list):
            row["verouderd_redenen"] = " | ".join(row["verouderd_redenen"])
        w.writerow(row)
    return output.getvalue()


# ── Streamlit UI ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="LeadFinder 🎯", page_icon="🎯", layout="wide")

st.markdown("""
<style>
.score-high { background:#16a34a;color:white;padding:3px 12px;border-radius:20px;font-weight:bold; }
.score-mid  { background:#ca8a04;color:white;padding:3px 12px;border-radius:20px;font-weight:bold; }
.score-low  { background:#dc2626;color:white;padding:3px 12px;border-radius:20px;font-weight:bold; }
</style>
""", unsafe_allow_html=True)

st.title("🎯 LeadFinder")
st.caption("Bedrijven zonder website opsporen via Google Maps — automatisch gescoord op kansrijkheid")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Instellingen")

    locatie_keuze = st.selectbox("🏙️ Stad of wijk", LOCATIE_KEUZES)
    if locatie_keuze.startswith("✏️"):
        stad_input = st.text_input("Typ stad of wijk", placeholder="bijv. Amsterdam De Pijp")
    elif locatie_keuze.startswith("Kies"):
        stad_input = ""
    elif locatie_keuze.startswith("🇳🇱🇧🇪"):
        stad_input = "Heel Nederland + België"
    elif locatie_keuze.startswith("🇳🇱"):
        stad_input = "Heel Nederland"
    elif locatie_keuze.startswith("🇧🇪"):
        stad_input = "Heel België"
    else:
        stad_input = locatie_keuze

    type_keuze = st.selectbox("🏢 Type bedrijf", BEDRIJFSTYPEN)
    if type_keuze.startswith("✏️"):
        eigen = st.text_input("Typ bedrijfstype", placeholder="bijv. nagelstudio")
        categorieen_input = [eigen.strip()] if eigen.strip() else []
    elif type_keuze.startswith("🔀"):
        categorieen_input = ALLE_CATEGORIEEN
        st.info(f"Doorzoekt **{len(ALLE_CATEGORIEEN)} categorieën**")
    else:
        categorieen_input = [type_keuze.split(" /")[0].replace("✏️", "").strip()]

    max_per_cat = st.slider("🎯 Max leads per categorie", 5, 40, 15, 5)
    zoek_modus = st.selectbox("🎯 Wat wil je vinden?", ZOEK_MODI)

    if stad_input == "Heel Nederland":
        steden = ALLE_STEDEN
    elif stad_input == "Heel België":
        steden = BELGIE_STEDEN
    elif stad_input == "Heel Nederland + België":
        steden = ALLE_STEDEN + BELGIE_STEDEN
    else:
        steden = [stad_input.strip()] if stad_input.strip() else []

    # Schatting tonen
    n_combis = len(steden) * len(categorieen_input)
    seconden_per_combi = 45
    minuten = round((n_combis * seconden_per_combi) / 60)
    st.divider()
    st.markdown(f"**📊 Verwacht:**")
    st.markdown(f"- **{n_combis}** zoekopdrachten")
    st.markdown(f"- Max **{n_combis * max_per_cat}** leads totaal")
    st.markdown(f"- Geschatte tijd: **~{minuten} min**")

    st.divider()
    st.markdown("**💡 Tips:**")
    st.markdown("- Stad of wijk is verplicht")
    st.markdown("- Heel Nederland/België duurt veel langer")
    st.markdown("- Wijk werkt beter dan grote stad")
    st.markdown("- Kleine steden geven meer leads")

    zoek_knop = st.button("🚀 Starten", type="primary", use_container_width=True)

    if n_combis > 50:
        st.warning(f"⚠️ {n_combis} zoekopdrachten — dit kan lang duren. Overweeg een specifieke stad of minder categorieën.")

# ── Hoofdpaneel ───────────────────────────────────────────────────────────────
if zoek_knop:
    if not steden:
        st.error("Kies of typ eerst een stad of wijk.")
        st.stop()

    if not categorieen_input:
        st.error("Vul een bedrijfstype in.")
        st.stop()

    col_log, col_res = st.columns([1, 2])

    with col_log:
        st.subheader("📡 Voortgang")
        log_box  = st.empty()
        prog_bar = st.progress(0, text="Bezig...")
        stat_box = st.empty()
        log_lines = []

        def log(msg):
            log_lines.append(msg)
            log_box.markdown("\n\n".join(log_lines[-14:]))

        def upd(gedaan, totaal, n_leads):
            pct = gedaan / max(totaal, 1)
            prog_bar.progress(pct, text=f"{gedaan}/{totaal} zoekopdrachten")
            stat_box.metric("Leads gevonden", n_leads)

    with col_res:
        st.subheader("🎯 Leads")
        res_placeholder = st.empty()

    scan_id = uuid.uuid4().hex[:8]
    leads = asyncio.run(run_scraper(steden, categorieen_input, max_per_cat, scan_id, zoek_modus, log, upd))
    prog_bar.progress(1.0, text="✅ Klaar!")

    if not leads:
        res_placeholder.warning("Geen leads gevonden. Probeer andere instellingen.")
    else:
        with res_placeholder.container():
            st.success(f"**{len(leads)} leads** gevonden")

            csv_data = naar_csv(leads)
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            label = stad_input.strip()
            st.download_button(
                "⬇️ Download alle leads als CSV",
                data=csv_data,
                file_name=f"leads_{label}_{ts}.csv",
                mime="text/csv",
            )

            st.divider()

            for i, l in enumerate(leads, 1):
                s = l["score"]
                cls = "score-high" if s >= 60 else "score-mid" if s >= 35 else "score-low"

                c1, c2 = st.columns([4, 1])
                with c1:
                    badges = ""
                    if l.get("categorie"):
                        badges += f"`{l['categorie']}`  "
                    if l.get("stad"):
                        badges += f"`{l['stad']}`"
                    st.markdown(f"**{i}. {l['naam']}**  {badges}")
                    if l.get("type"):
                        st.caption(l["type"])
                with c2:
                    st.markdown(f'<span class="{cls}">{s}/100</span>', unsafe_allow_html=True)

                m1, m2, m3 = st.columns(3)
                m1.metric("📞 Telefoon", l.get("telefoon") or "—")
                m2.metric("⭐ Rating", f"{l['rating']}/5" if l.get("rating") else "—")
                m3.metric("💬 Reviews", l.get("reviews", 0))

                if l.get("adres"):
                    st.caption(f"📍 {l['adres']}")
                if l.get("website"):
                    st.markdown(f"[🌐 Website]({l['website']})")
                if l.get("redenen"):
                    st.caption("  •  ".join(l["redenen"]))
                if l.get("maps_url"):
                    st.markdown(f"[📍 Open in Google Maps]({l['maps_url']})")

                st.divider()

else:
    st.info("👈 Kies instellingen links en klik op **Starten**")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**1. 🔍 Zoeken**\nGoogle Maps wordt doorzocht per gekozen stad of wijk + categorie.")
    with c2:
        st.markdown("**2. 🌐 Filteren**\nVind bedrijven zonder website of met duidelijke verouderingssignalen.")
    with c3:
        st.markdown("**3. 🎯 Scoren**\nElke lead scoort 0–100 op basis van reviews, rating en sector. Download als CSV.")
