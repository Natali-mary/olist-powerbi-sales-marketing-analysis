# =============================================================================
# app.py – Hauptdatei der BookScout-Webanwendung
# =============================================================================
# Diese Datei startet die Streamlit-App und enthält die gesamte
# Benutzeroberfläche (UI). Streamlit ist ein Python-Framework, das es
# ermöglicht, mit wenig Code interaktive Webanwendungen zu bauen.
#
# Starten der App:  streamlit run app.py
# =============================================================================

# --- Bibliotheken importieren -------------------------------------------------
# "import X" lädt eine externe Bibliothek, die wir dann im Code nutzen können.

import pandas as pd          # pandas: Tabellen/Daten einlesen und verarbeiten
import streamlit as st       # streamlit: Webanwendung bauen (Buttons, Charts …)
import altair as alt         # altair: interaktive Diagramme erstellen
from urllib.parse import quote_plus  # URL-Sonderzeichen korrekt kodieren (z. B. Leerzeichen → %20)

# Eigene Module aus dem Projekt importieren
from database import SessionLocal, Base, engine  # Datenbankverbindung
from models import Book                           # Datenbankmodell "Buch"
from data_processor import DataProcessor          # Hilfsfunktionen zum Filtern
from main import run_scrape                       # Scraper: Daten von der Website holen

# Analysefunktionen aus einer separaten Datei importieren
from analytics_features import (
    data_quality_metrics,   # Datenqualität prüfen (wie viele Felder fehlen?)
    author_analytics,       # Statistiken über Autoren
    segment_books,          # Bücher in Preis-/Bewertungsgruppen einteilen
    value_score,            # Preis-Leistungs-Punktzahl berechnen
)


# =============================================================================
# HILFSVARIABLEN: Spaltennamen
# =============================================================================
# Listen mit den Spaltennamen, die wir in der Datenbank/Tabellen brauchen.
# So müssen wir die Namen nicht überall einzeln eintippen.

BOOK_COLS = [
    "title", "category", "price", "rating", "availability",
    "upc", "description", "author", "publish_year", "cover_url"
]

# Spalten, die in den Buchkarten (Cards) angezeigt werden (ohne Beschreibung/Cover-URL)
CARD_COLS = [
    "title", "category", "price", "rating", "availability",
    "author", "publish_year", "upc"
]


def pick_cols(df, cols):
    """Gibt nur die Spalten zurück, die im DataFrame df tatsächlich vorhanden sind.
    So gibt es keinen Fehler, wenn eine Spalte fehlt."""
    return [c for c in cols if c in df.columns]


def safe_int_len(df):
    """Gibt die Anzahl der Zeilen zurück. Falls df None ist, wird 0 zurückgegeben."""
    return int(len(df)) if df is not None else 0


# =============================================================================
# DESIGN: Schriftgrößen anpassen (CSS)
# =============================================================================
# st.markdown() mit unsafe_allow_html=True erlaubt es, echtes HTML/CSS
# in die App einzufügen. Hier vergrößern wir die Standardschriftgrößen.

st.markdown(
    """
    <style>
      /* Basis-Schriftgröße für die gesamte Seite */
      html, body, [class*="css"]  { font-size: 18px !important; }

      /* Überschriften etwas größer als Standard */
      h1 { font-size: 2.2rem !important; }
      h2 { font-size: 1.75rem !important; }
      h3 { font-size: 1.35rem !important; }

      /* Schriftgröße in Tabellen (DataFrames) */
      .stDataFrame div, .stDataFrame span, .stDataFrame p {
        font-size: 17px !important;
      }

      /* KPI-Kacheln (Kennzahlen): Beschriftung und Wert */
      [data-testid="stMetricLabel"] { font-size: 1.05rem !important; }
      [data-testid="stMetricValue"] { font-size: 2.2rem !important; }

      /* Seitenleiste (Sidebar) leicht größer */
      section[data-testid="stSidebar"] * { font-size: 16px !important; }

      /* Placeholder-Text in Textfeldern ausblenden */
      .stTextInput input::placeholder { color: transparent !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# DESIGN: Altair-Theme (größere Diagrammbeschriftungen)
# =============================================================================
# Altair erlaubt eigene "Themes" – damit definieren wir einmalig Schriftgrößen
# für alle Diagramme der App.

def _bigger_altair_theme():
    """Gibt ein Altair-Theme-Dictionary zurück mit größeren Schriften."""
    return {
        "config": {
            "axis": {
                "labelFontSize": 16,   # Achsenbeschriftungen
                "titleFontSize": 17,   # Achsentitel
                "labelLimit": 300,     # Maximale Zeichenanzahl bei Achsenlabels
            },
            "legend": {
                "labelFontSize": 16,   # Legende: Beschriftungen
                "titleFontSize": 17,   # Legende: Titel
            },
            "title": {"fontSize": 18},           # Diagrammtitel
            "view": {"stroke": "transparent"},   # Kein Rahmen um das Diagramm
        }
    }


# Theme registrieren und aktivieren
alt.themes.register("bigger", _bigger_altair_theme)
alt.themes.enable("bigger")


# =============================================================================
# DATEN LADEN: Bücher aus der Datenbank holen
# =============================================================================

@st.cache_data(show_spinner=False)
# ↑ @st.cache_data bedeutet: Das Ergebnis dieser Funktion wird gespeichert.
#   Wenn die Funktion ein zweites Mal aufgerufen wird (z. B. beim Neuladen),
#   werden die Daten NICHT erneut aus der Datenbank geladen – das spart Zeit.
def load_books_df_cached() -> pd.DataFrame:
    """Lädt alle Bücher aus der SQLite-Datenbank und gibt sie als DataFrame zurück."""

    # Sicherstellen, dass alle Tabellen in der Datenbank existieren
    Base.metadata.create_all(bind=engine)

    # Datenbankverbindung öffnen
    db = SessionLocal()
    try:
        # Alle Einträge der Tabelle "Book" abfragen
        rows = db.query(Book).all()

        # Jede Zeile (Objekt) in ein Dictionary umwandeln, dann in einen DataFrame
        df = pd.DataFrame([
            {
                "title": r.title,
                "category": r.category,
                "price": r.price,
                "rating": r.rating,
                "availability": r.availability,
                "upc": r.upc,
                "description": r.description,
                "author": r.author,
                "publish_year": r.publish_year,
                "cover_url": r.cover_url,
            }
            for r in rows  # List Comprehension: für jedes Buch r in der Liste
        ])

        # publish_year als Ganzzahl speichern (pd.to_numeric wandelt Strings in Zahlen um,
        # errors="coerce" setzt fehlerhafte Werte auf NaN statt einen Fehler zu werfen)
        if "publish_year" in df.columns:
            df["publish_year"] = pd.to_numeric(df["publish_year"], errors="coerce").astype("Int64")

        return df
    finally:
        # Datenbankverbindung IMMER schließen – auch wenn ein Fehler aufgetreten ist
        db.close()


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def export_csv_bytes(df: pd.DataFrame) -> bytes:
    """Wandelt einen DataFrame in eine CSV-Datei um (als Bytes), zum Herunterladen."""
    # index=False: Keine Zeilennummern in der CSV
    # encode("utf-8"): Text in Bytes umwandeln (Streamlit braucht Bytes für Downloads)
    return df.to_csv(index=False).encode("utf-8")


def _format_rating_number_kpi(x: float) -> str:
    """Formatiert eine Bewertungszahl für die KPI-Anzeige (z. B. 3.75 → '3,75').
    Gibt '—' zurück, wenn kein Wert vorhanden ist."""
    if x is None or pd.isna(x):
        return "—"
    try:
        return f"{float(x):.2f}".replace(".", ",")  # Punkt durch Komma ersetzen (deutsches Format)
    except Exception:
        return "—"


def _stars_html_from_value(rating_value: float, font_px: int = 18) -> str:
    """
    Erzeugt HTML-Code für eine Sternanzeige (★★★☆☆).
    Gelbe Sterne = gefüllt, graue Sterne = leer. Immer 5 Sterne insgesamt.

    Beispiel: rating_value=3.7 → 4 gelbe + 1 grauer Stern
    """
    if rating_value is None or pd.isna(rating_value):
        return "<span style='color:#999;'>—</span>"
    try:
        r = float(rating_value)
        r = max(0.0, min(5.0, r))   # Wert auf 0–5 begrenzen
        r_stars = int(round(r))     # Auf ganze Zahl runden
    except Exception:
        return "<span style='color:#999;'>—</span>"

    filled = "★" * r_stars          # z. B. "★★★" für 3 Sterne
    empty = "★" * (5 - r_stars)     # z. B. "★★" für die restlichen 2

    # HTML zusammenbauen: gelbe Sterne + graue Sterne
    return (
        f"<span style='font-size:{font_px}px; line-height:1; white-space:nowrap;'>"
        f"<span style='color:#f5a623;'>{filled}</span>"   # gelb
        f"<span style='color:#d0d0d0;'>{empty}</span>"    # grau
        "</span>"
    )


def rating_inline_html_number_and_stars(rating) -> str:
    """
    Gibt HTML zurück, das die Bewertung als Zahl + Sterne anzeigt.
    Beispiel: "3 ★★★☆☆"
    Wird in Buchkarten und der Detailansicht verwendet.
    """
    if rating is None or pd.isna(rating):
        return "<span style='color:#999;'>—</span>"

    try:
        r_num = float(rating)
        r_num = max(0.0, min(5.0, r_num))
        r_int = int(round(r_num))
    except Exception:
        return "<span style='color:#999;'>—</span>"

    stars = _stars_html_from_value(r_int, font_px=18)
    return (
        "<span style='font-size:18px; line-height:1; white-space:nowrap;'>"
        f"<span style='color:#111; font-weight:600; margin-right:8px;'>{r_int}</span>"
        f"{stars}"
        "</span>"
    )


def amazon_search_url(title: str, author: str | None = None) -> str:
    """
    Baut eine Amazon-Suche-URL zusammen.
    Beispiel: title="Clean Code", author="Robert Martin"
    → https://www.amazon.com/s?k=Clean+Code+Robert+Martin
    """
    q = title.strip() if isinstance(title, str) else ""
    if author and isinstance(author, str) and author.strip():
        q = f"{q} {author.strip()}"
    # quote_plus kodiert Sonderzeichen für URLs (Leerzeichen → +, ä → %C3%A4 usw.)
    return "https://www.amazon.com/s?k=" + quote_plus(q)


# =============================================================================
# KPI-BLOCK: Kennzahlen anzeigen (Anzahl Bücher, Ø Preis, Ø Bewertung)
# =============================================================================

def kpi_block(df: pd.DataFrame):
    """
    Zeigt drei Kennzahlen (KPIs) nebeneinander:
      - Anzahl Bücher
      - Durchschnittspreis
      - Durchschnittsbewertung (mit Sternen)
    """
    # Drei gleich breite Spalten nebeneinander erstellen
    c1, c2, c3 = st.columns(3)

    c1.metric("Books", safe_int_len(df))
    c2.metric("Avg price", f"£ {df['price'].mean():.2f}" if len(df) else "—")

    if len(df) and df["rating"].dropna().any():
        avg_r = float(df["rating"].mean())
        num_txt = _format_rating_number_kpi(avg_r)

        # Sterne für die KPI-Kachel (etwas größer als in Karten)
        stars_html = _stars_html_from_value(avg_r, font_px=20)

        # st.markdown mit HTML ermöglicht individuelles Layout (kein Standard-st.metric)
        c3.markdown(
            f"""
            <div style="padding: 0;">
              <div style="font-size: 1.05rem; color: rgba(49, 51, 63, 0.6); margin-bottom: 0.25rem;">
                Avg rating
              </div>
              <div style="font-size: 2.2rem; font-weight: 400; line-height: 1.1; display:flex; align-items:baseline; gap:10px;">
                <span>{num_txt}</span>
                <span style="transform: translateY(-2px);">{stars_html}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        c3.metric("Avg rating", "—")


# =============================================================================
# DIAGRAMM: Bewertungsverteilung
# =============================================================================

def rating_distribution_chart(df: pd.DataFrame):
    """
    Zeigt ein Balkendiagramm, wie viele Bücher jede Bewertung (1–5 Sterne) haben.
    """
    # value_counts(): wie oft kommt jeder Bewertungswert vor?
    # sort_index(): nach dem Bewertungswert sortieren (1, 2, 3, 4, 5)
    # reset_index(): Index in normale Spalte umwandeln
    rating_counts = df["rating"].value_counts().sort_index().reset_index()
    rating_counts.columns = ["rating", "count"]

    # Lesbare Beschriftung: "3 ⭐" statt einfach "3"
    rating_counts["rating_label"] = rating_counts["rating"].astype(int).astype(str) + " ⭐"

    # Altair-Diagramm erstellen: Balkendiagramm
    chart = (
        alt.Chart(rating_counts)
        .mark_bar()  # Balkendiagramm
        .encode(
            x=alt.X("rating_label:O", title="Rating", axis=alt.Axis(labelAngle=0)),
            # :O = Ordinal (kategorisch), :Q = Quantitativ (Zahlen)
            y=alt.Y("count:Q", title="Books"),
            tooltip=["rating_label", "count"],  # Tooltip beim Hover
        )
        .properties(height=380)
    )
    st.altair_chart(chart, use_container_width=True)


# =============================================================================
# DIAGRAMM + DRILL-DOWN: Segmentierung (Preis × Bewertung)
# =============================================================================

def segment_chart_and_drilldown(df: pd.DataFrame):
    """
    Teilt Bücher in Segmente ein (günstiger/mittlerer/teurer Preis × hohe/niedrige Bewertung)
    und zeigt ein gruppiertes Balkendiagramm. Darunter kann man Bücher nach Segment filtern.
    """
    st.markdown("### Segmentation")

    # Bücher segmentieren (Funktion aus analytics_features.py)
    seg_df = segment_books(df)

    # Zählen, wie viele Bücher in jeder Kombination (Preis-Segment × Bewertungs-Segment) sind
    seg_counts = seg_df.groupby(["price_bucket", "rating_bucket"]).size().reset_index(name="count")

    # Rang für die Sortierung auf der X-Achse vergeben (Low → Mid → High)
    seg_counts["price_bucket_rank"] = seg_counts["price_bucket"].apply(
        lambda s: 0 if str(s).startswith("Low Price") else 1 if str(s).startswith("Mid Price") else 2
    )

    # Gruppiertes Balkendiagramm (bars) erstellen
    bars = (
        alt.Chart(seg_counts)
        .mark_bar()
        .encode(
            x=alt.X(
                "price_bucket:O",
                title="Price segment",
                sort=alt.SortField(field="price_bucket_rank", order="ascending"),
                axis=alt.Axis(labelAngle=0),
            ),
            xOffset=alt.XOffset("rating_bucket:O"),  # Balken nebeneinander pro Preisgruppe
            y=alt.Y("count:Q", title="Books"),
            color=alt.Color("rating_bucket:O", title="Rating segment"),
            tooltip=[
                alt.Tooltip("price_bucket:O", title="Price segment"),
                alt.Tooltip("rating_bucket:O", title="Rating segment"),
                alt.Tooltip("count:Q", title="Books"),
            ],
        )
    )

    # Anzahl-Labels über den Balken (mark_text)
    labels = (
        alt.Chart(seg_counts)
        .mark_text(dy=-10, fontSize=14)  # dy=-10: Text etwas über dem Balken
        .encode(
            x=alt.X(
                "price_bucket:O",
                sort=alt.SortField(field="price_bucket_rank", order="ascending"),
            ),
            xOffset=alt.XOffset("rating_bucket:O"),
            y=alt.Y("count:Q"),
            text=alt.Text("count:Q"),
        )
    )

    # Beide Layer übereinanderlegen (bars + labels) und anzeigen
    st.altair_chart((bars + labels).properties(height=420), use_container_width=True)

    st.markdown("#### Drill-down: pick a segment → view matching books")

    # Dropdown-Optionen für die Filterung
    price_opts = ["(all)"] + seg_counts.sort_values("price_bucket_rank")["price_bucket"].drop_duplicates().tolist()

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        sel_price_bucket = st.selectbox("Price segment", price_opts, index=0, key="drill_price_bucket")
    with c2:
        sel_rating_bucket = st.selectbox(
            "Rating segment", ["(all)", "High Rating >=4", "Low Rating <4"], index=0, key="drill_rating_bucket"
        )
    with c3:
        st.caption("Tip: Select both segments to narrow down the table below.")

    # DataFrame filtern je nach Auswahl
    drill = seg_df.copy()
    if sel_price_bucket != "(all)":
        drill = drill[drill["price_bucket"] == sel_price_bucket]
    if sel_rating_bucket != "(all)":
        drill = drill[drill["rating_bucket"] == sel_rating_bucket]

    # Nur vorhandene Spalten anzeigen
    cols = [
        c
        for c in ["title", "category", "price", "rating", "availability", "author", "publish_year", "upc"]
        if c in drill.columns
    ]
    # Sortiert nach Bewertung (absteigend) und Preis (aufsteigend), max. 200 Zeilen
    st.dataframe(
        drill.sort_values(["rating", "price"], ascending=[False, True])[cols].head(200),
        use_container_width=True,
    )


# =============================================================================
# SESSION STATE: Zustand zwischen Interaktionen merken
# =============================================================================

def init_state():
    """
    Initialisiert den Sitzungsspeicher (session_state).
    st.session_state ist wie ein Dictionary, das Werte über mehrere
    Klicks/Neuladen der App hinweg speichert.

    Hier: Favoriten-Liste und aktuell angezeigte Buch-Detailseite.
    """
    if "favorites" not in st.session_state:
        st.session_state["favorites"] = set()  # set() = Menge ohne Duplikate
    if "detail_upc" not in st.session_state:
        st.session_state["detail_upc"] = None  # None = kein Buch ausgewählt


def toggle_favorite(upc: str):
    """
    Fügt ein Buch zu den Favoriten hinzu oder entfernt es.
    upc ist der eindeutige Code des Buchs (Universal Product Code).
    """
    favs = st.session_state["favorites"]
    if upc in favs:
        favs.remove(upc)   # bereits Favorit → entfernen
    else:
        favs.add(upc)      # noch kein Favorit → hinzufügen
    st.session_state["favorites"] = favs


# =============================================================================
# HILFSFUNKTION: Jahr formatieren
# =============================================================================

def _fmt_year(y):
    """Gibt das Erscheinungsjahr als String zurück oder '—' wenn nicht vorhanden."""
    if y is None or (isinstance(y, float) and pd.isna(y)) or pd.isna(y):
        return "—"
    try:
        return str(int(y))
    except Exception:
        return "—"


# =============================================================================
# BUCHDETAIL-ANSICHT: Vollständige Informationen zu einem Buch anzeigen
# =============================================================================

def show_book_detail(df: pd.DataFrame, upc: str):
    """
    Zeigt die Detailseite für ein einzelnes Buch an.
    df: der gesamte DataFrame, upc: eindeutiger Buchcode
    """
    # Zeile im DataFrame suchen, deren UPC mit dem gesuchten übereinstimmt
    row = df[df["upc"] == upc]
    if row.empty:
        st.error("Book not found (UPC not in DataFrame).")
        return

    # Erste (und einzige) Zeile als Series holen
    b = row.iloc[0]

    # "← Back"-Button und Überschrift nebeneinander
    c1, c2 = st.columns([1, 8])
    with c1:
        if st.button("← Back", key="detail_back"):
            # Zurück zur Buchliste: detail_upc zurücksetzen und Seite neu laden
            st.session_state["detail_upc"] = None
            st.rerun()
    with c2:
        st.subheader("Book details")

    # Favoriten-Button: Text ändert sich je nach Status
    is_fav = upc in st.session_state["favorites"]
    fav_label = "⭐ Remove Favorite" if is_fav else "⭐ Add Favorite"
    if st.button(fav_label, key=f"detail_fav_{upc}"):
        toggle_favorite(upc)
        st.rerun()

    # Layout: linke Spalte = Cover-Bild, rechte Spalte = Details
    left, right = st.columns([1, 2])
    with left:
        cover_url = b.get("cover_url", None)
        if cover_url and pd.notna(cover_url):
            st.image(cover_url, use_container_width=True)
            st.markdown(f"[Open cover link]({cover_url})")
        else:
            st.info("No cover available.")

    with right:
        title = b.get("title", "")
        author = b.get("author", None)

        st.markdown(f"### {title}")
        st.write(f"**UPC:** {b.get('upc','—')}")
        st.write(f"**Category:** {b.get('category','—')}")
        st.write(
            f"**Price:** £ {b.get('price', 0):.2f}"
            if pd.notna(b.get("price", None))
            else "**Price:** —"
        )

        # Bewertung als HTML (Zahl + Sterne)
        st.markdown(
            f"**Rating:** {rating_inline_html_number_and_stars(b.get('rating', None))}",
            unsafe_allow_html=True,
        )

        st.write(f"**Author:** {author if author else '—'}")
        st.write(f"**Publish year:** {_fmt_year(b.get('publish_year', None))}")
        st.write(f"**Availability:** {b.get('availability','—')}")

        # Link-Button öffnet Amazon-Suche im Browser
        st.link_button("🛒 View on Amazon", amazon_search_url(str(title), str(author) if author else None))

    # Buchbeschreibung anzeigen
    st.markdown("### Description")
    desc = b.get("description", "")
    if desc and isinstance(desc, str) and desc.strip():
        st.write(desc)
    else:
        st.caption("No description available.")


# =============================================================================
# STREAMLIT APP – HAUPTTEIL
# =============================================================================
# Ab hier wird die eigentliche Seite aufgebaut. Streamlit führt diesen Code
# von oben nach unten aus – jedes Mal, wenn der Nutzer auf etwas klickt
# oder die Seite interagiert.
# =============================================================================

# Seitentitel und Layout festlegen (muss als ERSTES st.*-Kommando aufgerufen werden)
st.set_page_config(page_title="BookScout", layout="wide")
st.title("📚 BookScout – Book analytics dashboard")

# Sitzungsstatus initialisieren (Favoriten, Detail-Ansicht)
init_state()
processor = DataProcessor()

# --- "Refresh"-Button: Scraper erneut starten ---
colA, colB = st.columns([1, 5])
with colA:
    if st.button("🔄 Refresh (scrape again)"):
        # st.spinner zeigt einen Ladeindikator, während der Scraper läuft
        with st.spinner("Scraping in progress..."):
            run_scrape()
        st.cache_data.clear()   # Gespeicherte Daten löschen, damit neue geladen werden
        st.success("Data updated!")
        st.rerun()              # Seite neu laden

# --- Daten aus Datenbank laden ---
df = load_books_df_cached()

# Wenn keine Daten vorhanden, Warnung zeigen und App anhalten
if df.empty:
    st.warning("No data in the database. Click Refresh to scrape.")
    st.stop()

# Prüfen, ob alle notwendigen Spalten im DataFrame vorhanden sind
required_cols = {"title", "category", "price", "rating", "availability", "upc"}
missing = required_cols - set(df.columns)
if missing:
    st.error(f"Missing columns in df: {sorted(list(missing))}")
    st.stop()


# =============================================================================
# SIDEBAR: Filterformular
# =============================================================================
# Die Sidebar ist die linke Seitenleiste. Hier kann der Nutzer die Daten filtern.

st.sidebar.header("Filters")

# Session-State-Schlüssel initialisieren (nur beim ersten Aufruf)
min_price = float(df["price"].min())
max_price = float(df["price"].max())
if "f_categories" not in st.session_state:
    st.session_state["f_categories"] = []
if "f_ratings" not in st.session_state:
    st.session_state["f_ratings"] = []
if "f_price_range" not in st.session_state:
    st.session_state["f_price_range"] = (min_price, max_price)
if "f_title_query" not in st.session_state:
    st.session_state["f_title_query"] = ""

# st.sidebar.form: Alle Eingaben werden erst beim Klick auf "Apply" übernommen
with st.sidebar.form("filter_form"):
    # Kategorie-Filter: Mehrfachauswahl aller verfügbaren Kategorien
    all_categories = sorted([c for c in df["category"].dropna().unique().tolist() if c])
    st.multiselect("Category", options=all_categories, key="f_categories")

    # Bewertungs-Filter: Mehrfachauswahl der vorhandenen Sternebewertungen
    all_ratings = sorted(df["rating"].dropna().unique().tolist())
    st.multiselect("Rating (stars)", options=all_ratings, key="f_ratings")

    # Preisbereich-Filter: Schieberegler zwischen Min- und Max-Preis
    st.slider("Price range (£)", min_value=min_price, max_value=max_price, key="f_price_range")

    # Submit-Button: Formular abschicken
    st.form_submit_button("✅ Apply filters")

# Titel-Suche außerhalb des Formulars (verhindert "Press Enter to submit"-Hinweis)
st.sidebar.text_input("Search by title", key="f_title_query")

# Aktuelle Filterwerte aus session_state lesen
sel_categories = st.session_state["f_categories"]
sel_ratings = st.session_state["f_ratings"]
price_range = st.session_state["f_price_range"]
title_query = st.session_state["f_title_query"]

# DataFrame nach den Filterkriterien einschränken
filtered = processor.filter_df(
    df=df,
    categories=sel_categories,
    price_min=price_range[0],
    price_max=price_range[1],
    ratings=sel_ratings,
    title_query=title_query,
)


# =============================================================================
# TABS: Verschiedene Ansichten der App
# =============================================================================
# st.tabs erstellt Registerkarten (wie Browser-Tabs). Der Nutzer kann zwischen
# den Bereichen wechseln, ohne die Seite neu zu laden.

tab_overview, tab_analyses, tab_books, tab_compare = st.tabs(["Overview", "Analyses", "Books", "Compare"])


# -----------------------------------------------------------------------------
# TAB 1: OVERVIEW – Überblick mit Kennzahlen und Diagrammen
# -----------------------------------------------------------------------------
with tab_overview:
    st.subheader("Overview")

    # KPI-Block: Anzahl Bücher, Ø Preis, Ø Bewertung
    kpi_block(filtered)
    st.divider()  # Trennlinie

    # --- Preise nach Kategorie (Balkendiagramm) ---
    st.markdown("### Prices by category (avg / min / max)")

    # groupby: Daten nach Kategorie gruppieren, dann Statistiken berechnen
    price_stats = (
        filtered.groupby("category")["price"]
        .agg(avg="mean", min="min", max="max")   # Durchschnitt, Min, Max berechnen
        .reset_index()
        .sort_values("avg", ascending=False)      # Absteigend nach Durchschnittspreis sortieren
    )

    if price_stats.empty:
        st.info("No data for the current filters.")
    else:
        # Schieberegler: wie viele Top-Kategorien anzeigen?
        top_n = st.slider("Top categories by avg price", 5, 50, 20, key="ov_top_n")
        ps = price_stats.head(top_n).copy()

        # melt: "breites" Format (avg, min, max als Spalten) → "langes" Format (eine Zeile pro Metrik)
        # Das braucht Altair, um nach "metric" einzufärben
        ps_long = ps.melt(id_vars=["category"], value_vars=["avg", "min", "max"], var_name="metric", value_name="price")
        metric_order = ["avg", "min", "max"]

        price_chart = (
            alt.Chart(ps_long)
            .mark_bar()
            .encode(
                x=alt.X(
                    "category:O",
                    title="Category",
                    axis=alt.Axis(
                        labelAngle=-45,       # Beschriftungen schräg stellen
                        labelOverlap=False,   # Nichts ausblenden (auch bei Überlappung)
                        labelLimit=0,         # Nicht abschneiden/kürzen
                    ),
                ),
                y=alt.Y("price:Q", title="Price (£)", stack=True),  # Gestapelte Balken
                color=alt.Color("metric:O", title="Metric", sort=metric_order),
                tooltip=[
                    alt.Tooltip("category:O", title="Category"),
                    alt.Tooltip("metric:O", title="Metric"),
                    alt.Tooltip("price:Q", title="Price", format=".2f"),
                ],
            )
            .properties(height=460)
        )
        st.altair_chart(price_chart, use_container_width=True)

    st.divider()

    # --- Bewertungsverteilung ---
    st.markdown("### Rating distribution")
    if filtered["rating"].dropna().empty:
        st.info("No rating data for the current filters.")
    else:
        rating_distribution_chart(filtered)

    st.divider()

    # --- CSV-Export ---
    st.markdown("### Export")
    st.download_button(
        "⬇️ Download CSV",
        data=export_csv_bytes(filtered),
        file_name="bookscout_filtered.csv",
        mime="text/csv",
        disabled=filtered.empty,  # Button deaktivieren wenn keine Daten
    )

    st.markdown("---")
    st.caption("powered by A-Team/ Dream-Team")


# -----------------------------------------------------------------------------
# TAB 2: ANALYSES – Detaillierte Analysen
# -----------------------------------------------------------------------------
with tab_analyses:
    st.subheader("Analyses")
    if filtered.empty:
        st.warning("No data for the current filters.")
    else:
        # --- Datenqualität ---
        st.markdown("### Data quality")
        st.caption("Completeness metrics for key fields.")

        # Datenqualität für alle Daten und für gefilterte Daten berechnen
        dq_all = data_quality_metrics(df)
        dq_f = data_quality_metrics(filtered)

        # Gesamtdaten: wie viele Felder sind ausgefüllt?
        st.markdown("#### Overall (all data)")
        q1, q2, q3, q4, q5 = st.columns(5)
        q1.metric("Rows", dq_all["total"])
        q2.metric("Cover fill", f"{dq_all['cover_fill']*100:.1f}%")   # Anteil Bücher mit Cover
        q3.metric("Author fill", f"{dq_all['author_fill']*100:.1f}%") # Anteil Bücher mit Autor
        q4.metric("Year fill", f"{dq_all['year_fill']*100:.1f}%")     # Anteil Bücher mit Jahr
        q5.metric("Description fill", f"{dq_all['desc_fill']*100:.1f}%")

        # Gleiche Metriken für die aktuell gefilterten Daten
        st.markdown("#### Current filters")
        f1, f2, f3, f4, f5 = st.columns(5)
        f1.metric("Rows", dq_f["total"])
        f2.metric("Cover fill", f"{dq_f['cover_fill']*100:.1f}%")
        f3.metric("Author fill", f"{dq_f['author_fill']*100:.1f}%")
        f4.metric("Year fill", f"{dq_f['year_fill']*100:.1f}%")
        f5.metric("Description fill", f"{dq_f['desc_fill']*100:.1f}%")

        st.divider()

        # --- Teuerste und günstigste Bücher ---
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### Top 10 most expensive books")
            # sort_values: nach Preis absteigend sortieren, die ersten 10 nehmen
            st.dataframe(
                filtered.sort_values("price", ascending=False)[["title", "category", "price", "rating", "availability"]].head(10),
                use_container_width=True,
            )
        with c2:
            st.markdown("### Top 10 cheapest books")
            st.dataframe(
                filtered.sort_values("price", ascending=True)[["title", "category", "price", "rating", "availability"]].head(10),
                use_container_width=True,
            )

        st.divider()

        # --- Autorenanalyse ---
        st.markdown("### Author analytics (OpenLibrary)")
        top_n_auth = st.slider("Top authors", 5, 30, 10, key="auth_top_n")
        auth = author_analytics(filtered, top_n=top_n_auth)
        st.markdown("**Author stats (books, avg rating, avg price)**")
        st.dataframe(auth["author_stats"], use_container_width=True)

        st.divider()

        # --- Segmentierungsdiagramm ---
        segment_chart_and_drilldown(filtered)

        st.divider()

        # --- Value Score: Preis-Leistungs-Verhältnis ---
        st.markdown("### Value score (best deals)")
        top_n_value = st.slider("Top N", 5, 50, 15, key="vs_top_n")
        vs = value_score(filtered)
        if vs.empty:
            st.info("Not enough data for Value Score.")
        else:
            st.caption("Value score = rating / log(price + 1). Higher is better.")
            # Formel: höhere Bewertung bei niedrigerem Preis → hoher Score = gutes Angebot
            st.dataframe(vs.head(top_n_value), use_container_width=True)


# -----------------------------------------------------------------------------
# TAB 3: BOOKS – Buchkarten-Ansicht
# -----------------------------------------------------------------------------
with tab_books:
    st.subheader("Books")

    # Wenn ein Buch für die Detailansicht ausgewählt wurde, diese anzeigen
    if st.session_state["detail_upc"]:
        show_book_detail(df=df, upc=st.session_state["detail_upc"])
    else:
        if filtered.empty:
            st.warning("No results for the current filters.")
        else:
            # Sortier- und Favoritenoptionen
            c1, c2, c3 = st.columns([2, 2, 3])
            with c1:
                sort_option = st.selectbox("Sort by", ["Price (asc)", "Price (desc)", "Title (A-Z)", "Rating (desc)"], key="tile_sort")
            with c2:
                show_only_favs = st.checkbox("Show favorites only", value=False, key="tile_only_favs")
            with c3:
                st.caption(f"Favorites: {len(st.session_state['favorites'])}")

            show_df = filtered.copy()

            # Wenn "Nur Favoriten" aktiv: DataFrame auf Favoriten einschränken
            if show_only_favs:
                favs = st.session_state["favorites"]
                show_df = show_df[show_df["upc"].isin(list(favs))]

            # Sortierung anwenden
            if sort_option == "Price (asc)":
                show_df = show_df.sort_values("price", ascending=True)
            elif sort_option == "Price (desc)":
                show_df = show_df.sort_values("price", ascending=False)
            elif sort_option == "Title (A-Z)":
                show_df = show_df.sort_values("title", ascending=True)
            elif sort_option == "Rating (desc)":
                show_df = show_df.sort_values("rating", ascending=False)

            count = len(show_df)
            if count == 0:
                st.warning("No books for this view (maybe no favorites in the current filters).")
            else:
                # Schieberegler für Anzahl angezeigter Bücher (nur wenn mehr als 12)
                if count <= 12:
                    max_cards = count
                else:
                    max_cards = st.slider(
                        "Number of books to show",
                        min_value=12,
                        max_value=min(300, count),
                        value=min(60, count),
                        step=12,
                        key="tile_count",
                    )

                show_df = show_df.head(max_cards)

                # --- Buchkarten als Grid (3 pro Zeile) ---
                cols_per_row = 3
                # Anzahl Zeilen berechnen (aufrunden: z. B. 7 Bücher → 3 Zeilen)
                rows = (len(show_df) + cols_per_row - 1) // cols_per_row

                for r in range(rows):
                    cols = st.columns(cols_per_row)
                    for c in range(cols_per_row):
                        idx = r * cols_per_row + c   # Position im DataFrame
                        if idx >= len(show_df):
                            break  # Letzte Zeile kann weniger als 3 Bücher haben

                        # Buchdaten für die aktuelle Karte holen
                        book = show_df.iloc[idx]

                        title = str(book.get("title", ""))
                        price = book.get("price", None)
                        author = book.get("author", None)
                        rating = book.get("rating", None)
                        cover_url = book.get("cover_url", None)
                        availability = book.get("availability", None)
                        year = book.get("publish_year", None)
                        upc = book.get("upc", "")

                        is_fav = upc in st.session_state["favorites"]
                        fav_btn_label = "⭐ Remove Favorite" if is_fav else "⭐ Add Favorite"

                        # Buchkarte in der entsprechenden Spalte anzeigen
                        with cols[c]:
                            with st.container(border=True):  # Rahmen um die Karte
                                # Karte: links das Cover-Bild, rechts die Textinfos
                                left_img, right_txt = st.columns([1, 3])

                                with left_img:
                                    if cover_url and pd.notna(cover_url):
                                        st.image(cover_url, width=90)
                                    else:
                                        st.caption("No cover")

                                with right_txt:
                                    st.markdown(f"**{title}**")
                                    st.write(f"Price: **£ {price:.2f}**" if pd.notna(price) else "Price: —")
                                    st.markdown(f"Rating: {rating_inline_html_number_and_stars(rating)}", unsafe_allow_html=True)
                                    st.write(f"Author: **{author}**" if author and pd.notna(author) else "Author: —")
                                    st.write(f"Publish year: {_fmt_year(year)}")
                                    st.write(f"Availability: {availability}" if availability and pd.notna(availability) else "Availability: —")

                                    # Drei Buttons: Favorit, Amazon, Details
                                    b1, b2, b3 = st.columns([1.2, 1.2, 1.2])
                                    with b1:
                                        if st.button(fav_btn_label, key=f"fav_{upc}_{idx}"):
                                            toggle_favorite(upc)
                                            st.rerun()
                                    with b2:
                                        st.link_button("🛒 Amazon", amazon_search_url(title, str(author) if author else None))
                                    with b3:
                                        if st.button("🔎 Details", key=f"details_{upc}_{idx}"):
                                            # detail_upc setzen → beim nächsten Render die Detailseite anzeigen
                                            st.session_state["detail_upc"] = upc
                                            st.rerun()


# -----------------------------------------------------------------------------
# TAB 4: COMPARE – Zwei Kategorien direkt vergleichen
# -----------------------------------------------------------------------------
with tab_compare:
    st.subheader("Compare: Category A vs Category B")

    cats = sorted([c for c in df["category"].dropna().unique().tolist() if c])
    if len(cats) < 2:
        st.info("Not enough categories to compare.")
    else:
        # Zwei Kategorien auswählen
        cA, cB = st.columns(2)
        with cA:
            cat_a = st.selectbox("Category A", options=cats, index=0, key="cmp_a")
        with cB:
            cat_b = st.selectbox("Add a Category", options=cats, index=1, key="cmp_b")

        # DataFrame für jede Kategorie erstellen
        df_a = df[df["category"] == cat_a].copy()
        df_b = df[df["category"] == cat_b].copy()

        # KPIs und Bewertungsverteilung nebeneinander
        a1, a2 = st.columns(2)
        with a1:
            st.markdown(f"### {cat_a}")
            kpi_block(df_a)
            if not df_a.empty:
                rating_distribution_chart(df_a)
        with a2:
            st.markdown(f"### {cat_b}")
            kpi_block(df_b)
            if not df_b.empty:
                rating_distribution_chart(df_b)

        st.divider()

        # --- Boxplot: Preisverteilung der beiden Kategorien ---
        st.markdown("### Price comparison (boxplot)")

        # Beide DataFrames zusammenführen und eine "group"-Spalte hinzufügen
        # pd.concat verbindet zwei DataFrames untereinander
        cmp_df = pd.concat(
            [
                df_a.assign(group=cat_a)[["group", "price"]],  # assign fügt eine neue Spalte hinzu
                df_b.assign(group=cat_b)[["group", "price"]],
            ],
            ignore_index=True,  # Index neu durchnummerieren
        )

        # Boxplot zeigt: Median, Quartile, Ausreißer – gut für Verteilungsvergleiche
        box = (
            alt.Chart(cmp_df)
            .mark_boxplot(size=240)
            .encode(
                x=alt.X(
                    "group:O",
                    title="Category",
                    axis=alt.Axis(labelAngle=0),
                    scale=alt.Scale(paddingInner=0.15, paddingOuter=0.10),
                ),
                y=alt.Y("price:Q", title="Price (£)"),
                tooltip=["group", alt.Tooltip("price:Q", format=".2f")],
            )
            .properties(height=380)
        )
        st.altair_chart(box, use_container_width=True)
