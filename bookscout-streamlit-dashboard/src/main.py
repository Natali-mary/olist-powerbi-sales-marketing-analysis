# =============================================================================
# main.py – Hauptpipeline: Scraping → API-Anreicherung → Datenbank
# =============================================================================
# Diese Datei verbindet alle anderen Module und führt den vollständigen
# Datenpipeline-Prozess durch:
#
#   1. Scraping:        Bücher von books.toscrape.com herunterladen (scraper.py)
#   2. API-Anreicherung: Autor, Jahr, Cover von OpenLibrary ergänzen (api_client.py)
#   3. Datenbank:       Daten in SQLite speichern/aktualisieren (database.py, models.py)
#
# Diese Funktion wird von app.py aufgerufen, wenn der "Refresh"-Button geklickt wird.
# =============================================================================

from database import Base, SessionLocal, engine   # DB-Verbindung
from models import Book, PriceHistory             # Datenbankmodelle
from scraper import BookScraper                   # Web Scraper
from api_client import OpenLibraryClient          # API-Client


# Spalten, die beim Aktualisieren eines bestehenden Bucheintrags überschrieben werden
_BOOK_FIELDS = (
    "title",
    "category",
    "price",
    "rating",
    "availability",
    "description",
    "author",
    "publish_year",
    "cover_url",
)


# =============================================================================
# Upsert-Logik: Einfügen oder Aktualisieren
# =============================================================================

def upsert_books(db, book_dicts: list):
    """Speichert Bücher in der Datenbank – entweder als Update oder als Insert.

    "Upsert" = Update + Insert:
    - Wenn ein Buch mit diesem UPC bereits in der DB ist → Daten aktualisieren
    - Wenn es noch nicht existiert → neuen Eintrag erstellen

    So werden bei jedem Scraping-Lauf keine Duplikate angelegt.

    db:         Datenbank-Session
    book_dicts: Liste von Buch-Dictionaries (Ergebnis aus Scraping + Anreicherung)
    """
    for b in book_dicts:
        upc = b.get("upc")
        if not upc:
            continue   # Buch ohne UPC überspringen (kein eindeutiger Schlüssel)

        # Prüfen ob ein Buch mit diesem UPC bereits in der DB existiert
        existing = db.query(Book).filter(Book.upc == upc).first()

        if existing:
            # Buch existiert → alle Felder aktualisieren
            # setattr(obj, "feld", wert) ist wie: obj.feld = wert
            for f in _BOOK_FIELDS:
                setattr(existing, f, b.get(f))
        else:
            # Buch existiert noch nicht → neuen Eintrag anlegen
            # Book(**b) entpackt das Dictionary als Keyword-Argumente
            db.add(Book(**b))

    # Alle Änderungen auf einmal in die Datenbank schreiben
    db.commit()


# =============================================================================
# Hauptfunktion: Vollständige Pipeline
# =============================================================================

def run_scrape():
    """Führt die komplette Datenpipeline aus:
    Scraping → API-Anreicherung → Datenbank-Upsert → Preisverlauf speichern.

    Wird von app.py beim Klick auf "Refresh" aufgerufen.
    """
    # Sicherstellen, dass alle Tabellen in der DB existieren
    # (beim ersten Start werden sie automatisch erstellt)
    Base.metadata.create_all(bind=engine)

    # Scraper und API-Client initialisieren
    scraper = BookScraper()
    api = OpenLibraryClient(sleep_sec=0.3, debug=False)

    # --- Schritt 1: Scraping ---
    print("Starte Scraping...")
    books = scraper.scrape_all_books(sleep_sec=0.0)
    print(f"{len(books)} Bücher gescraped.")

    # --- Schritt 2: API-Anreicherung ---
    # Für jedes Buch: Autor, Jahr und Cover von OpenLibrary ergänzen
    enriched = []
    for i, b in enumerate(books, start=1):   # enumerate gibt Index + Wert zurück
        title = b.get("title", "")
        upc = b.get("upc", "")

        try:
            # OpenLibrary nach Metadaten fragen (ISBN-Suche, dann Titel-Suche)
            extra = api.enrich(title=title, isbn_or_upc=upc)

            # Cover-URL aus dem Scraping NICHT mit der API-Version überschreiben,
            # weil der Scraper schon das Originalbild der Website hat
            extra.pop("cover_url", None)

            # Buch-Dictionary mit den neuen Infos ergänzen
            b.update(extra)
        except Exception as e:
            print(f"[API Fehler] Titel={title!r} | {e}")

        enriched.append(b)

        # Fortschritt alle 50 Bücher ausgeben
        if i % 50 == 0:
            print(f"API-Anreicherung Fortschritt: {i}/{len(books)}")

    # --- Schritt 3: In die Datenbank speichern ---
    db = SessionLocal()   # Neue Datenbank-Session öffnen
    try:
        # Bücher einfügen oder aktualisieren
        upsert_books(db, enriched)

        # Preisverlauf: für jedes Buch einen neuen PriceHistory-Eintrag anlegen
        # So können wir später sehen, wie sich Preise über Zeit verändert haben
        for b in enriched:
            if b.get("upc") and b.get("price") is not None:
                db.add(PriceHistory(upc=b["upc"], price=b["price"]))
        db.commit()
    finally:
        db.close()   # Verbindung IMMER schließen

    print(f"Saved/updated {len(enriched)} books.")
    print("Scraping + Anreicherung abgeschlossen.")
