# =============================================================================
# api_client.py – OpenLibrary API-Client
# =============================================================================
# Diese Datei enthält die Klasse OpenLibraryClient, die Buchdaten von der
# kostenlosen OpenLibrary-API abruft: https://openlibrary.org
#
# Was ist eine API?
#   Eine API (Application Programming Interface) ist eine Schnittstelle, über
#   die Programme miteinander kommunizieren können. Wir schicken eine HTTP-
#   Anfrage (wie im Browser), bekommen aber JSON-Daten zurück – kein HTML.
#
# Ziel: Für jeden gescrapten Buchtitel Autor, Erscheinungsjahr und Cover-URL
#       von OpenLibrary ergänzen ("anreichern").
# =============================================================================

import re      # Reguläre Ausdrücke: Muster in Texten suchen (z. B. Jahreszahl)
import time    # Pausen zwischen Anfragen einbauen
import requests  # HTTP-Anfragen stellen


class OpenLibraryClient:
    """Client für die OpenLibrary-API.

    Unterstützt zwei Suchmethoden:
    1. ISBN/UPC-Suche  – zuverlässiger, wenn eine echte ISBN vorhanden ist
    2. Titel-Suche     – Fallback, wenn keine ISBN vorliegt
    """

    def __init__(self, sleep_sec: float = 0.3, debug: bool = False):
        """
        sleep_sec: Wartezeit in Sekunden zwischen API-Anfragen
                   (OpenLibrary empfiehlt max. 1–3 Anfragen/Sekunde)
        debug:     Wenn True, werden Fehlermeldungen/Infos ausgegeben
        """
        self.base = "https://openlibrary.org"   # Basis-URL der API
        self.sleep_sec = sleep_sec
        self.debug = debug

        # Session für HTTP-Verbindungen (effizienter als einzelne requests.get()-Aufrufe)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BookScout/1.0 (Educational Project)"})

    # =========================================================================
    # Private Hilfsmethoden
    # =========================================================================

    def _sleep(self):
        """Wartet sleep_sec Sekunden, um die API nicht zu überlasten."""
        if self.sleep_sec and self.sleep_sec > 0:
            time.sleep(self.sleep_sec)

    def _get_json(self, url: str, *, params: dict, err_ctx: str) -> dict:
        """Schickt eine GET-Anfrage an die API und gibt das JSON-Ergebnis zurück.

        params:   Query-Parameter für die URL (z. B. {"title": "Clean Code"})
        err_ctx:  Text für die Fehlermeldung, falls etwas schiefgeht
        Gibt {} zurück, wenn ein Fehler auftritt.
        """
        try:
            r = self.session.get(url, params=params, timeout=15)
            r.raise_for_status()   # Fehler bei HTTP-Statuscodes >= 400
            return r.json()        # JSON-Antwort als Python-Dictionary zurückgeben
        except Exception as e:
            if self.debug:
                print(f"[OpenLibrary] {err_ctx} | {e}")
            return {}
        finally:
            # _sleep() wird IMMER aufgerufen – auch bei Fehlern
            self._sleep()

    def _normalize_title(self, title: str) -> str:
        """Bereinigt einen Buchtitel für die Suche, um mehr Treffer zu erzielen.

        Entfernt Klammern-Inhalte und Untertitel nach ':'.
        Beispiel: 'Clean Code: A Handbook (1st Edition)' → 'Clean Code'
        """
        t = (title or "").strip()
        if not t:
            return ""

        # Alles in runden Klammern entfernen: "(1st Edition)" → ""
        t = re.sub(r"\([^)]*\)", "", t)

        # Untertitel nach Doppelpunkt entfernen: "Clean Code: A Handbook" → "Clean Code"
        if ":" in t:
            t = t.split(":", 1)[0]

        # Mehrere Leerzeichen zu einem zusammenfassen
        return re.sub(r"\s+", " ", t).strip()

    def _safe_int_year(self, s) -> int | None:
        """Wandelt einen Wert in eine ganze Zahl um (für das Erscheinungsjahr).
        Gibt None zurück, wenn die Umwandlung nicht möglich ist."""
        if s is None:
            return None
        try:
            return int(s)
        except Exception:
            return None

    # =========================================================================
    # Methode 1: ISBN-Suche (/api/books)
    # =========================================================================

    def enrich_by_isbn(self, isbn: str) -> dict:
        """Sucht Buchdaten über ISBN via /api/books.

        Zuverlässiger als Titel-Suche, da ISBN eindeutig ist.
        Hinweis: Auf books.toscrape.com ist 'upc' nicht immer eine echte ISBN,
        deshalb ist ein Fallback auf Titel-Suche nötig.

        Gibt ein Dictionary mit 'author', 'publish_year', 'cover_url' zurück
        (oder {}, wenn nichts gefunden wurde).
        """
        isbn = (isbn or "").strip()
        if not isbn:
            return {}

        # API-Anfrage: https://openlibrary.org/api/books?bibkeys=ISBN:xxx&format=json&jscmd=data
        data = self._get_json(
            f"{self.base}/api/books",
            params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
            err_ctx=f"ISBN request error | isbn={isbn}",
        )

        # Die Antwort ist ein Dict mit dem ISBN-Key als Schlüssel
        key = f"ISBN:{isbn}"
        if key not in data:
            if self.debug:
                print(f"[OpenLibrary] ISBN not found | isbn={isbn}")
            return {}

        book = data[key]

        # --- Autor: erstes Element der "authors"-Liste ---
        author = None
        authors = book.get("authors") or []
        if authors:
            author = authors[0].get("name")

        # --- Erscheinungsjahr: aus "publish_date" mit Regex extrahieren ---
        # publish_date kann z. B. "June 2008" oder "2008" sein
        publish_year = None
        publish_date = book.get("publish_date")
        if publish_date:
            m = re.search(r"(\d{4})", str(publish_date))   # 4-stellige Zahl suchen
            if m:
                publish_year = self._safe_int_year(m.group(1))

        # --- Cover-URL: bevorzugt "medium", dann "large", dann "small" ---
        cover = book.get("cover") or {}
        cover_url = cover.get("medium") or cover.get("large") or cover.get("small")

        return {"author": author, "publish_year": publish_year, "cover_url": cover_url}

    # =========================================================================
    # Methode 2: Titel-Suche (/search.json)
    # =========================================================================

    def enrich_by_title(self, title: str, limit: int = 5) -> dict:
        """Sucht Buchdaten über den Titel via /search.json.

        Nimmt bevorzugt ein Ergebnis, das ein Cover-Bild hat (cover_i vorhanden).
        limit: Wie viele Ergebnisse die API maximal zurückgeben soll.
        """
        q_raw = (title or "").strip()
        q = self._normalize_title(q_raw)   # Titel bereinigen
        if not q:
            return {}

        # API-Anfrage: https://openlibrary.org/search.json?title=xxx&limit=5
        data = self._get_json(
            f"{self.base}/search.json",
            params={"title": q, "limit": limit},
            err_ctx=f"Title request error | title={q_raw!r} | q={q!r}",
        )

        # "docs" enthält die Liste der gefundenen Bücher
        docs = data.get("docs", [])
        if not docs:
            if self.debug:
                print(f"[OpenLibrary] No docs | title={q_raw!r} | q={q!r}")
            return {}

        # Bestes Ergebnis wählen: bevorzugt eines mit cover_i (Cover-ID)
        # next(..., None) gibt das erste Element zurück, das die Bedingung erfüllt,
        # oder None wenn keines gefunden wird
        best = next((d for d in docs if d.get("cover_i")), None)
        if best is None:
            best = docs[0]   # Kein Cover → einfach das erste Ergebnis nehmen
            if self.debug:
                print(f"[OpenLibrary] Docs but no cover_i | title={q_raw!r} | q={q!r}")

        # --- Autor: erster Eintrag in "author_name" ---
        author = None
        if best.get("author_name"):
            author = best["author_name"][0]

        # --- Erscheinungsjahr: "first_publish_year" ---
        publish_year = None
        if best.get("first_publish_year"):
            publish_year = self._safe_int_year(best.get("first_publish_year"))

        # --- Cover-URL aus Cover-ID bauen ---
        # OpenLibrary Cover-API: https://covers.openlibrary.org/b/id/{id}-M.jpg
        cover_url = None
        cover_i = best.get("cover_i")
        if cover_i:
            cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"

        return {"author": author, "publish_year": publish_year, "cover_url": cover_url}

    # =========================================================================
    # Kombinierte Methode: ISBN → Titel-Fallback
    # =========================================================================

    def enrich(self, title: str, isbn_or_upc: str | None = None) -> dict:
        """Kombinierte Anreicherungsstrategie:

        1) Erst ISBN/UPC über /api/books probieren
        2) Wenn nichts Nützliches gefunden → Titel-Suche als Fallback

        Gibt dict mit 'author', 'publish_year', 'cover_url' zurück (oder {}).
        """
        if isbn_or_upc:
            extra = self.enrich_by_isbn(isbn_or_upc)
            # Wenn wir mindestens ein nützliches Feld haben, ist es gut genug
            if extra.get("cover_url") or extra.get("author") or extra.get("publish_year"):
                return extra

        # ISBN hat nicht gereicht → Titel-Suche als Fallback
        return self.enrich_by_title(title)
