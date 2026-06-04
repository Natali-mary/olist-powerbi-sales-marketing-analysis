# =============================================================================
# models.py – Datenbankmodelle (Tabellenstruktur)
# =============================================================================
# Hier definieren wir, wie die Tabellen in der SQLite-Datenbank aussehen.
# Jede Python-Klasse entspricht einer Tabelle, jedes Attribut einer Spalte.
#
# SQLAlchemy übersetzt diese Klassen automatisch in SQL-CREATE-TABLE-Befehle.
# =============================================================================

from datetime import datetime   # Für den Zeitstempel in PriceHistory

# Column-Typen: bestimmen den Datentyp der Spalte in SQL
from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from database import Base   # Alle Modelle erben von Base (aus database.py)


# =============================================================================
# Tabelle: books
# =============================================================================

class Book(Base):
    """Repräsentiert einen Bucheintrag in der Datenbank.

    Entspricht der SQL-Tabelle 'books'.
    Jede Instanz dieser Klasse = eine Zeile in der Tabelle.
    """
    __tablename__ = "books"   # Name der Tabelle in der SQLite-Datei

    # Primärschlüssel: eindeutige ID, wird von der Datenbank automatisch vergeben
    id = Column(Integer, primary_key=True, index=True)

    # --- Daten von der Bücherlisten-Seite (scraper.py, Übersichtsseite) ---
    title = Column(String, index=True)    # Buchtitel (index=True = schnellere Suche)
    category = Column(String, index=True) # Kategorie, z. B. "Mystery"
    price = Column(Float)                 # Preis in £ (Dezimalzahl)
    rating = Column(Integer)              # Bewertung 1–5 (ganze Zahl)
    availability = Column(String)         # z. B. "In stock"

    # --- Daten von der Buch-Detailseite ---
    upc = Column(String, index=True)      # Universal Product Code – eindeutiger Buchcode
    description = Column(Text)            # Längere Buchbeschreibung (Text statt String)

    # --- Daten aus der OpenLibrary-API (api_client.py) ---
    # nullable=True: Diese Felder dürfen leer sein (nicht alle Bücher haben Infos)
    author = Column(String, nullable=True)       # Autorenname
    publish_year = Column(Integer, nullable=True) # Erscheinungsjahr
    cover_url = Column(String, nullable=True)     # URL zum Cover-Bild


# =============================================================================
# Tabelle: price_history
# =============================================================================

class PriceHistory(Base):
    """Speichert den Preisverlauf eines Buches über die Zeit.

    Jedes Mal, wenn der Scraper läuft, wird für jedes Buch ein neuer
    PriceHistory-Eintrag angelegt. So kann man Preisänderungen nachverfolgen.
    """
    __tablename__ = "price_history"

    # Primärschlüssel
    id = Column(Integer, primary_key=True)

    # Verweis auf das Buch (nicht als Foreign Key, sondern als einfacher String-Wert)
    upc = Column(String, index=True)

    # Preis zum Zeitpunkt des Scrapings
    price = Column(Float)

    # Zeitstempel: wird automatisch auf "jetzt" gesetzt, wenn der Eintrag erstellt wird
    # datetime.utcnow: aktuelle Zeit in UTC (koordinierte Weltzeit)
    scraped_at = Column(DateTime, default=datetime.utcnow)
