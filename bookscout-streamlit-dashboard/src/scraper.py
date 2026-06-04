# =============================================================================
# scraper.py – Bücher von books.toscrape.com herunterladen
# =============================================================================
# Web Scraping bedeutet: eine Website automatisch besuchen und Daten aus dem
# HTML-Quellcode extrahieren. Wir nutzen dafür zwei Bibliotheken:
#
#   requests    – HTTP-Anfragen stellen (Website herunterladen)
#   BeautifulSoup – HTML parsen (Struktur lesen und gezielt Daten herauslesen)
#
# Die Ziel-Website: https://books.toscrape.com/
# Das ist eine legale Übungsseite, die extra zum Üben von Web Scraping gebaut wurde.
# =============================================================================

import time                         # Pausen zwischen Anfragen einbauen
from urllib.parse import urljoin    # Relative URLs in absolute URLs umwandeln

import requests                     # HTTP-Anfragen (GET, POST …)
from bs4 import BeautifulSoup       # HTML-Parser


class BookScraper:
    """Scrapt alle Bücher von books.toscrape.com.

    Geht Seite für Seite durch den Katalog und liest für jedes Buch:
    - Titel, Preis, Bewertung, Verfügbarkeit (aus der Übersichtsliste)
    - Kategorie, UPC, Beschreibung, Cover-URL (von der Detailseite)
    """

    def __init__(self, base_url="https://books.toscrape.com/"):
        """Initialisiert den Scraper mit der Basis-URL der Website."""
        self.base_url = base_url

        # requests.Session() ist effizienter als einzelne requests.get()-Aufrufe,
        # weil sie die TCP-Verbindung wiederverwenden kann (weniger Overhead).
        self.session = requests.Session()

        # User-Agent: Wer "klopft" an den Server? Ein ehrlicher User-Agent ist gute Praxis.
        self.session.headers.update({"User-Agent": "BookScout/1.0 (Educational Project)"})

    # -------------------------------------------------------------------------
    # Private Hilfsmethoden (mit _ beginnen → "intern", nicht von außen aufrufen)
    # -------------------------------------------------------------------------

    def _get_soup(self, url: str) -> BeautifulSoup:
        """Lädt eine Seite herunter und gibt sie als BeautifulSoup-Objekt zurück.

        BeautifulSoup ermöglicht es, im HTML nach Tags, Klassen usw. zu suchen.
        timeout=15: Wenn der Server 15 Sekunden nicht antwortet, Fehler werfen.
        """
        r = self.session.get(url, timeout=15)
        r.raise_for_status()   # Fehler werfen, wenn HTTP-Statuscode >= 400 (z. B. 404)
        return BeautifulSoup(r.text, "html.parser")

    def _rating_to_int(self, rating_class: str) -> int:
        """Wandelt einen Text-Bewertungsklassennamen in eine Zahl um.

        Die Website speichert Bewertungen als CSS-Klassen wie 'Three' statt '3'.
        Beispiel: 'Four' → 4
        """
        return {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}.get(rating_class, 0)

    @staticmethod
    def _parse_price(text: str) -> float | None:
        """Extrahiert eine Dezimalzahl aus einem Preistext.

        Beispiel: '£12.99' → 12.99
        Methode: Alle Zeichen außer Ziffern und Punkt entfernen, dann in float umwandeln.
        """
        cleaned = "".join(ch for ch in (text or "") if (ch.isdigit() or ch == "."))
        return float(cleaned) if cleaned else None

    # -------------------------------------------------------------------------
    # Hauptmethode: Alle Bücher scrapen
    # -------------------------------------------------------------------------

    def scrape_all_books(self, sleep_sec=0.0) -> list:
        """Scrapt alle Bücher auf allen Seiten des Katalogs.

        Die Website hat ~50 Seiten mit je 20 Büchern. Diese Methode geht
        automatisch durch alle Seiten, bis es keine "Weiter"-Seite mehr gibt.

        sleep_sec: Pause in Sekunden zwischen zwei Seitenaufrufen (0 = keine Pause)
        Gibt eine Liste von Dictionaries zurück (ein Dict pro Buch).
        """
        books = []
        next_url = self.base_url + "catalogue/page-1.html"   # Startseite
        page_count = 0

        # Schleife läuft solange, bis kein "Weiter"-Link mehr gefunden wird
        while True:
            page_count += 1
            print(f"[Scraper] Seite {page_count}: {next_url}")

            # HTML der aktuellen Seite laden und parsen
            soup = self._get_soup(next_url)

            # Alle Buch-Artikel auf der Seite finden (<article class="product_pod">)
            items = soup.select("article.product_pod")
            print(f"[Scraper]   Bücher auf Seite: {len(items)}")

            for item in items:
                # --- Titel aus dem <a title="...">-Attribut ---
                title = item.h3.a.get("title", "").strip()

                # --- Preis: Text aus .price_color extrahieren und parsen ---
                price_tag = item.select_one(".price_color")
                price_text = price_tag.text.strip() if price_tag else ""
                price = self._parse_price(price_text)
                if price is None:
                    print(f"[Scraper]   ⚠️ Preis nicht parsebar: {repr(price_text)} | Titel: {title}")
                    continue   # Buch überspringen, wenn Preis fehlt

                # --- Bewertung: CSS-Klasse 'star-rating Three' → 3 ---
                rating_tag = item.select_one("p.star-rating")
                rating_classes = rating_tag.get("class", []) if rating_tag else []
                # "star-rating" ist immer dabei – wir wollen die ANDERE Klasse (z. B. "Three")
                rating_word = next((c for c in rating_classes if c != "star-rating"), "")
                rating = self._rating_to_int(rating_word)

                # --- Verfügbarkeit: Text aus .availability ---
                availability_tag = item.select_one(".availability")
                availability = availability_tag.text.strip() if availability_tag else ""

                # --- Link zur Detailseite (relativer Pfad) ---
                detail_rel = item.h3.a.get("href", "")
                if not detail_rel:
                    print(f"[Scraper]   ⚠️ Kein Detail-Link gefunden | Titel: {title}")
                    continue

                # Relativen Link in absoluten Link umwandeln
                detail_url = self._to_absolute(detail_rel)

                # --- Detailseite scrapen (Kategorie, UPC, Beschreibung, Cover) ---
                try:
                    detail_data = self.scrape_book_detail(detail_url)
                except Exception as e:
                    print(f"[Scraper]   ❌ Fehler bei Detailseite: {detail_url} | {e}")
                    continue

                # Alle Daten in ein Dictionary packen und zur Liste hinzufügen
                books.append(
                    {
                        "title": title,
                        "price": price,
                        "rating": rating,
                        "availability": availability,
                        "category": detail_data.get("category", ""),
                        "upc": detail_data.get("upc", ""),
                        "description": detail_data.get("description", ""),
                        "cover_url": detail_data.get("cover_url", None),
                    }
                )

                # Fortschritt alle 50 Bücher ausgeben
                if len(books) % 50 == 0:
                    print(f"[Scraper]   Fortschritt: {len(books)} Bücher gescraped")

                # Optionale Pause, um den Server nicht zu überlasten
                if sleep_sec > 0:
                    time.sleep(sleep_sec)

            # --- Nächste Seite finden ---
            # <li class="next"><a href="page-2.html"> – falls vorhanden
            next_link = soup.select_one("li.next a")
            if not next_link:
                # Kein "Weiter"-Link → letzte Seite erreicht
                print(f"[Scraper] Fertig. Gesamt: {len(books)} Bücher")
                break

            next_rel = next_link.get("href", "")
            next_url = self._next_page_url(current_page_url=next_url, next_rel=next_rel)

        return books

    # -------------------------------------------------------------------------
    # Detailseite eines einzelnen Buches scrapen
    # -------------------------------------------------------------------------

    def scrape_book_detail(self, detail_url: str) -> dict:
        """Scrapt die Detailseite eines Buches und gibt Kategorie, UPC, Beschreibung und Cover zurück."""
        soup = self._get_soup(detail_url)

        # --- Kategorie aus der Breadcrumb-Navigation ---
        # Breadcrumb: Home > Bücher > Mystery > Buchtitel
        # Index 2 (3. Element) = Kategorie
        breadcrumb = soup.select("ul.breadcrumb li a")
        category = breadcrumb[2].text.strip() if len(breadcrumb) >= 3 else ""

        # --- Beschreibung: Absatz nach der Überschrift #product_description ---
        desc = ""
        desc_header = soup.select_one("#product_description")
        if desc_header:
            p = desc_header.find_next("p")   # Das <p>-Tag direkt nach der Überschrift
            if p:
                desc = p.text.strip()

        # --- UPC aus der Produktinformationstabelle ---
        # Die Tabelle hat Zeilen <tr><th>UPC</th><td>abc123</td></tr>
        upc = ""
        for row in soup.select("table.table.table-striped tr"):
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td and th.text.strip() == "UPC":
                upc = td.text.strip()
                break   # Gefunden – Schleife beenden

        # --- Cover-URL: Bild aus der Detailansicht ---
        # Das aktive Bild hat die Klasse "item active"
        cover_url = None
        img = soup.select_one("div.item.active img")
        if img and img.get("src"):
            # urljoin wandelt den relativen Pfad ("../../media/...") in eine absolute URL um
            cover_url = urljoin(detail_url, img["src"])

        return {"category": category, "description": desc, "upc": upc, "cover_url": cover_url}

    # -------------------------------------------------------------------------
    # URL-Hilfsmethoden
    # -------------------------------------------------------------------------

    def _to_absolute(self, href: str) -> str:
        """Wandelt einen relativen Buch-Link in eine absolute URL um.

        Beispiel: '../../a-light-in-the-attic.../index.html'
                → 'https://books.toscrape.com/catalogue/a-light-in-the-attic.../index.html'
        """
        if href.startswith("http"):
            return href   # Schon absolut → unverändert zurückgeben
        href = href.replace("../../../", "")   # Relative Pfad-Präfixe entfernen
        return self.base_url + "catalogue/" + href

    def _next_page_url(self, current_page_url: str, next_rel: str) -> str:
        """Berechnet die absolute URL der nächsten Seite.

        Der "Weiter"-Link ist relativ zur aktuellen Seite, z. B. 'page-2.html'.
        Wir müssen ihn in eine absolute URL umrechnen.
        """
        if "catalogue/" in current_page_url:
            prefix = current_page_url.split("catalogue/")[0] + "catalogue/"
            return prefix + next_rel
        return self.base_url + next_rel
