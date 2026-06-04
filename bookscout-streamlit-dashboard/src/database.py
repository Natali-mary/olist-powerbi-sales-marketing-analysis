# =============================================================================
# database.py – Datenbankverbindung konfigurieren
# =============================================================================
# Diese Datei richtet die Verbindung zur SQLite-Datenbank ein.
# SQLite ist eine einfache Datenbank, die als einzelne Datei gespeichert wird
# (hier: bookscout.db). Sie braucht keinen eigenen Server.
#
# SQLAlchemy ist eine Python-Bibliothek, die SQL-Datenbanken mit Python-Objekten
# verbindet – wir müssen kein rohes SQL schreiben.
# =============================================================================

from pathlib import Path                              # Pfade betriebssystemunabhängig verwalten
from sqlalchemy import create_engine                  # Datenbankverbindung erstellen
from sqlalchemy.ext.declarative import declarative_base  # Basis für Datenbankmodelle
from sqlalchemy.orm import sessionmaker               # Sitzungen (Sessions) für DB-Zugriffe

# -----------------------------------------------------------------------------
# Datenbankpfad berechnen
# -----------------------------------------------------------------------------

# __file__ ist der Pfad dieser Datei (database.py)
# .resolve().parent gibt den Ordner zurück, in dem sie liegt
BASE_DIR = Path(__file__).resolve().parent.parent

# Die Datenbankdatei liegt im gleichen Ordner wie database.py
DB_PATH = BASE_DIR / "data" / "bookscout.db"

# SQLAlchemy erwartet eine URL im Format: "sqlite:///pfad/zur/datei.db"
# as_posix() wandelt Windows-Backslashes in Forward-Slashes um (für SQLAlchemy nötig)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# -----------------------------------------------------------------------------
# Engine erstellen
# -----------------------------------------------------------------------------
# Der "Engine" ist die eigentliche Verbindung zur Datenbank.
# check_same_thread=False erlaubt, die Verbindung aus mehreren Threads zu nutzen
# (notwendig, weil Streamlit mehrere Anfragen gleichzeitig verarbeiten kann).
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# -----------------------------------------------------------------------------
# SessionLocal: Fabrik für Datenbanksitzungen
# -----------------------------------------------------------------------------
# Eine "Session" ist wie eine Arbeitsverbindung zur Datenbank.
# Mit sessionmaker erstellen wir eine Vorlage (Fabrik), aus der wir bei Bedarf
# neue Sessions erzeugen können (db = SessionLocal()).
# autocommit=False: Änderungen müssen explizit mit db.commit() gespeichert werden
# autoflush=False:  SQL wird erst bei Bedarf gesendet, nicht sofort
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# -----------------------------------------------------------------------------
# Base: Basis für alle Datenbankmodelle
# -----------------------------------------------------------------------------
# Alle Klassen, die eine Datenbanktabelle repräsentieren (z. B. Book),
# erben von dieser Base-Klasse. SQLAlchemy erkennt sie dadurch automatisch.
Base = declarative_base()
