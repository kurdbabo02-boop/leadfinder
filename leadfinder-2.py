#!/usr/bin/env python3
"""
LeadFinder - Vind bedrijven zonder website via Google Maps
Gebruik: python3 leadfinder.py --stad "Amsterdam" --type "kapper" --max 20
"""

import argparse
import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from rich.console import Console
from rich.table import Table

console = Console()

# Boekingsplatforms en social media tellen NIET als echte website
GEEN_WEBSITE = [
    # Boekingsplatforms
    "treatwell", "mytreatwell", "fresha", "booksy", "planity", "salonkee",
    "salonized", "simplybook", "reservio", "acuityscheduling", "calendly",
    "setmore", "square.site", "booking.com", "wahanda",
    # Bezorgplatforms
    "thuisbezorgd", "takeaway", "deliveroo", "ubereats", "just-eat",
    # Reviews/gidsen
    "tripadvisor", "yelp.", "zomato", "foursquare",
    # Social media
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "tiktok.com",
    # Google
    "google.com", "goo.gl", "/maps", "maps.app",
]

TYPE_SCORES = {
    "restaurant": 9, "cafe": 8, "kapper": 8, "kapsalon": 8,
    "schoonheidssalon": 8, "nagelsalon": 8, "tandarts": 9,
    "fysiotherapeut": 9, "dokter": 9, "advocaat": 9, "accountant": 9,
    "notaris": 9, "aannemer": 7, "loodgieter": 7, "elektricien": 7,
    "schilder": 7, "bakker": 8, "bloemenwinkel": 8, "dierenarts": 9,
    "garage": 7, "autorijschool": 8, "sportschool": 9, "yoga": 8,
    "pizzeria": 8, "hotel": 9, "fotograaf": 9, "makelaar": 9,
    "barbershop": 8, "barber": 8, "hair": 7,
}


def is_echte_website(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    url_lower = url.lower()
    return not any(p in url_lower for p in GEEN_WEBSITE)


def bereken_score(bedrijf: dict) -> dict:
    score = 0
    redenen = []

    if bedrijf.get("telefoon"):
        score += 25
        redenen.append(f"Telefoonnummer: {bedrijf['telefoon']}")

    reviews = bedrijf.get("reviews", 0)
    if reviews >= 50:
        score += 30
        redenen.append(f"{reviews} reviews - populair")
    elif reviews >= 20:
        score += 20
        redenen.append(f"{reviews} reviews - actief")
    elif reviews >= 5:
        score += 10
        redenen.append(f"{reviews} reviews")
    elif reviews > 0:
        score += 5

    rating = bedrijf.get("rating", 0.0)
    if rating >= 4.5:
        score += 20
        redenen.append(f"{rating}/5 ster - uitstekend")
    elif rating >= 4.0:
        score += 15
        redenen.append(f"{rating}/5 ster - goed")
    elif rating >= 3.0:
        score += 8
        redenen.append(f"{rating}/5 ster")

    if bedrijf.get("adres"):
        score += 5
        redenen.append("Fysiek adres bekend")

    btype = bedrijf.get("type", "").lower()
    for t, s in TYPE_SCORES.items():
        if t in btype or btype in t:
            score += s * 2
            redenen.append(f"Sector '{bedrijf.get('type','?')}' = hoog potentieel")
            break

    return {"score": min(score, 100), "redenen": redenen}


async def verzamel_urls(page, zoekterm: str, max_items: int) -> list:
    """Stap 1: verzamel bedrijfsnaam + URL door door de lijst te scrollen."""
    lijst_url = f"https://www.google.com/maps/search/{zoekterm.replace(' ', '+')}"
    print(f"[*] Lijst laden: {lijst_url}")
    await page.goto(lijst_url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)

    # Cookies accepteren
    for sel in ['button:has-text("Alles accepteren")', 'button:has-text("Accept all")']:
        try:
            btn = page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1500)
                break
        except Exception:
            pass

    bedrijven = {}  # naam -> href
    feed = page.locator('div[role="feed"]')

    for scroll_i in range(10):
        items = await page.locator('a[href*="/maps/place/"]').all()
        for item in items:
            try:
                href = (await item.get_attribute("href", timeout=1000)) or ""
                naam = (await item.get_attribute("aria-label", timeout=1000)) or ""
                if naam and href and naam not in bedrijven:
                    bedrijven[naam] = href
            except Exception:
                continue

        if len(bedrijven) >= max_items * 2:
            break

        try:
            if await feed.count() > 0:
                await feed.first.evaluate("el => el.scrollBy(0, 2000)")
            await page.wait_for_timeout(2000)
        except Exception:
            break

    result = [(naam, href) for naam, href in bedrijven.items()]
    print(f"[*] {len(result)} bedrijven gevonden in lijst")
    return result


async def haal_details(page, naam: str, href: str) -> dict:
    """Stap 2: bezoek detail-URL en extraheer gegevens."""
    data = {
        "naam": naam, "website": None, "telefoon": None,
        "adres": None, "rating": 0.0, "reviews": 0, "type": "",
        "maps_url": href,
    }

    await page.goto(href, wait_until="domcontentloaded", timeout=12000)
    await page.wait_for_timeout(800)

    # Rating
    try:
        els = await page.locator('span[aria-hidden="true"]').all()
        for el in els:
            txt = (await el.inner_text(timeout=1000)).strip()
            if re.match(r'^\d[.,]\d$', txt):
                data["rating"] = float(txt.replace(",", "."))
                break
    except Exception:
        pass

    # Reviews
    try:
        el = page.locator('span[aria-label*="recensie"], span[aria-label*="review"]').first
        label = (await el.get_attribute("aria-label", timeout=2000)) or ""
        nums = re.findall(r'[\d.]+', label.replace(",", ""))
        if nums:
            data["reviews"] = int(float(nums[0]))
    except Exception:
        pass

    # Website - gebruik Google Maps' eigen "website" knop
    # Booking platforms (treatwell, fresha etc.) tellen NIET als echte eigen website
    try:
        website_el = page.locator('a[data-item-id="authority"]')
        if await website_el.count() > 0:
            href_val = (await website_el.first.get_attribute("href", timeout=2000)) or ""
            if href_val and is_echte_website(href_val):
                data["website"] = href_val
    except Exception:
        pass

    # Telefoon
    try:
        tel_el = page.locator('[data-item-id*="phone"] .rogA2c').first
        tel_txt = (await tel_el.inner_text(timeout=2000)).strip()
        if re.search(r'[\d\+]', tel_txt):
            data["telefoon"] = tel_txt
    except Exception:
        pass

    # Adres
    try:
        adres_el = page.locator('[data-item-id="address"] .rogA2c').first
        data["adres"] = (await adres_el.inner_text(timeout=2000)).strip()
    except Exception:
        pass

    # Type
    try:
        type_el = page.locator('button[jsaction*="category"] span, span.DkEaL').first
        data["type"] = (await type_el.inner_text(timeout=2000)).strip()
    except Exception:
        pass

    return data


async def scrape(stad: str, bedrijfstype: str, max_leads: int) -> list:
    leads = []
    zoekterm = f"{bedrijfstype} {stad}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"]
        )
        ctx = await browser.new_context(
            locale="nl-NL",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()

        # Stap 1: verzamel alle bedrijven uit de lijst
        bedrijven = await verzamel_urls(page, zoekterm, max_leads)

        # Stap 2: bezoek elk bedrijf en check website
        gescand = 0
        print(f"[*] Scannen op website-aanwezigheid...")

        for naam, href in bedrijven:
            if len(leads) >= max_leads:
                break
            try:
                details = await haal_details(page, naam, href)
                gescand += 1

                if not details["website"]:
                    sd = bereken_score(details)
                    details["score"] = sd["score"]
                    details["redenen"] = sd["redenen"]
                    leads.append(details)
                    print(f"  [+] {naam[:44]:<44} score: {details['score']:>3}  ({len(leads)}/{max_leads})")
                else:
                    print(f"  [-] {naam[:44]:<44} heeft website")

            except Exception as e:
                print(f"  [!] Fout bij {naam[:40]}: {e}")
                continue

        print(f"\n[*] Klaar - {gescand} gescand, {len(leads)} leads")
        await browser.close()

    return leads


def sla_op(leads: list, stad: str, btype: str) -> str:
    if not leads:
        return ""
    Path("/workspace/leadfinder/resultaten").mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pad = f"/workspace/leadfinder/resultaten/leads_{stad}_{btype}_{ts}.csv"
    velden = ["score", "naam", "type", "telefoon", "adres", "rating", "reviews", "redenen", "maps_url"]
    with open(pad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=velden)
        w.writeheader()
        for l in sorted(leads, key=lambda x: x["score"], reverse=True):
            w.writerow({
                k: ("|".join(l[k]) if k == "redenen" and isinstance(l.get(k), list) else l.get(k, ""))
                for k in velden
            })
    return pad


def toon(leads: list):
    leads = sorted(leads, key=lambda x: x["score"], reverse=True)
    t = Table(
        title=f"[bold green]{len(leads)} leads zonder website - gerangschikt op kans[/bold green]",
        show_lines=True
    )
    t.add_column("#", width=3, style="dim")
    t.add_column("Score", width=7)
    t.add_column("Naam", width=32, style="bold white")
    t.add_column("Type", width=18, style="cyan")
    t.add_column("Reviews", width=9)
    t.add_column("Rating", width=7)
    t.add_column("Telefoon", width=17, style="green")
    for i, l in enumerate(leads, 1):
        s = l["score"]
        c = "green" if s >= 60 else "yellow" if s >= 35 else "red"
        t.add_row(
            str(i), f"[{c}]{s}[/{c}]", l["naam"][:31],
            l.get("type", "-")[:17], str(l.get("reviews", 0)),
            str(l.get("rating", "-")), (l.get("telefoon") or "-")[:16]
        )
    console.print(t)

    console.print("\n[bold magenta]=== TOP 5 BESTE LEADS ===[/bold magenta]")
    for l in leads[:5]:
        console.print(f"\n[bold white]{l['naam']}[/bold white] — score: [green]{l['score']}/100[/green]")
        for r in l.get("redenen", []):
            console.print(f"  • {r}")


async def main():
    ap = argparse.ArgumentParser(description="LeadFinder - bedrijven zonder website opsporen")
    ap.add_argument("--stad", required=True, help="Bijv. Amsterdam")
    ap.add_argument("--type", required=True, help="Bijv. kapper, restaurant, loodgieter")
    ap.add_argument("--max", type=int, default=15, help="Max leads (standaard 15)")
    args = ap.parse_args()

    leads = await scrape(args.stad, args.type, args.max)
    if not leads:
        console.print("[red]Geen leads gevonden.[/red]")
        return
    toon(leads)
    pad = sla_op(leads, args.stad, args.type)
    if pad:
        console.print(f"\n[bold green]CSV opgeslagen:[/bold green] {pad}")


if __name__ == "__main__":
    asyncio.run(main())
