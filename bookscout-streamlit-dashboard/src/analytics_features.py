# =============================================================================
# analytics_features.py – Analysefunktionen für Buchdaten
# =============================================================================
# Diese Datei enthält alle Analysefunktionen, die in der App (app.py) verwendet werden.
# Jede Funktion bekommt einen pandas DataFrame und gibt aufbereitete Daten zurück.
# =============================================================================

import pandas as pd   # Tabellen und Datenverarbeitung
import numpy as np    # Mathematische Funktionen (z. B. Logarithmus, Quantile)


# =============================================================================
# Hilfsvariable: Mapping von Metrik-Namen zu Spalten-Namen
# =============================================================================
# Dieses Dictionary verbindet den Namen einer Qualitätsmetrik mit der
# entsprechenden DataFrame-Spalte, die wir prüfen wollen.

_FILL_COLS = {
    "cover_fill":  "cover_url",    # Wie viele Bücher haben ein Cover-Bild?
    "author_fill": "author",       # Wie viele haben einen Autor?
    "year_fill":   "publish_year", # Wie viele haben ein Erscheinungsjahr?
    "desc_fill":   "description",  # Wie viele haben eine Beschreibung?
    "avail_fill":  "availability", # Wie viele haben Verfügbarkeitsinfos?
}


# =============================================================================
# Datenqualität prüfen
# =============================================================================

def data_quality_metrics(df: pd.DataFrame) -> dict:
    """Berechnet Vollständigkeitsmetriken für die wichtigsten Felder.

    Gibt ein Dictionary zurück, z. B.:
      {"total": 1000, "cover_fill": 0.85, "author_fill": 0.72, ...}
    Die Werte sind Anteile (0.0–1.0), also: 0.85 = 85 % ausgefüllt.
    """
    total = len(df)
    # Startwert: alle Metriken auf 0.0 initialisieren
    out = {"total": total, **{k: 0.0 for k in _FILL_COLS}}

    if total == 0:
        return out   # Leerer DataFrame → alle Werte bleiben 0.0

    def fill_rate(col: str) -> float:
        """Berechnet den Anteil nicht-leerer Werte in einer Spalte.

        Leer = NaN (fehlend) ODER leerer String "".
        .mean() auf einem Bool-Array gibt den Anteil True-Werte zurück.
        """
        if col not in df.columns:
            return 0.0
        s = df[col]
        # notna(): True wo kein NaN | str.strip() != "": True wo kein leerer String
        return float((s.notna() & (s.astype(str).str.strip() != "")).mean())

    # Alle Metriken berechnen und ins Ergebnis-Dictionary schreiben
    out.update({k: fill_rate(col) for k, col in _FILL_COLS.items()})
    return out


# =============================================================================
# Autorenanalyse
# =============================================================================

def author_analytics(df: pd.DataFrame, top_n: int = 10) -> dict:
    """Berechnet Statistiken für die Top-Autoren.

    Gibt ein Dictionary mit zwei DataFrames zurück:
      "top_authors_count": Top-Autoren nach Anzahl Bücher
      "author_stats":      Detailstatistiken (Bücher, Ø Bewertung, Ø Preis)
    """
    # Leere DataFrames für den Fehlerfall vorbereiten
    empty_top = pd.DataFrame(columns=["author", "books"])
    empty_stats = pd.DataFrame(columns=["author", "books", "avg_rating", "avg_price"])

    if "author" not in df.columns or df.empty:
        return {"top_authors_count": empty_top, "author_stats": empty_stats}

    d = df.copy()

    # Fehlende Autorennamen bereinigen: NaN → "", dann Leerzeichen entfernen
    d["author"] = d["author"].fillna("").astype(str).str.strip()

    # Zeilen ohne Autor entfernen
    d = d[d["author"] != ""]

    if d.empty:
        return {"top_authors_count": empty_top, "author_stats": empty_stats}

    # Top-Autoren nach Anzahl Bücher
    # value_counts(): wie oft kommt jeder Autor vor?
    # rename_axis/reset_index: Index in Spalte umwandeln
    top_authors = (
        d["author"].value_counts().head(top_n).rename_axis("author").reset_index(name="books")
    )

    # Detailstatistiken: pro Autor Bücher zählen, Ø Bewertung und Ø Preis berechnen
    # groupby + agg: Daten gruppieren und mehrere Funktionen gleichzeitig anwenden
    author_stats = (
        d.groupby("author", as_index=False)
        .agg(
            books=("title", "count"),         # Wie viele Bücher hat dieser Autor?
            avg_rating=("rating", "mean"),     # Durchschnittliche Bewertung
            avg_price=("price", "mean"),       # Durchschnittlicher Preis
        )
        .sort_values(["books", "avg_rating"], ascending=[False, False])  # Meiste Bücher zuerst
        .head(top_n)
    )
    author_stats["avg_price"] = author_stats["avg_price"].round(1)
    author_stats["avg_rating"] = author_stats["avg_rating"].round(1)

    return {"top_authors_count": top_authors, "author_stats": author_stats}


# =============================================================================
# Bücher segmentieren (Preis × Bewertung)
# =============================================================================

def segment_books(df: pd.DataFrame) -> pd.DataFrame:
    """Teilt Bücher in Preis- und Bewertungssegmente ein.

    Preissegmente: Low / Mid / High (basierend auf dem 20. und 80. Perzentil)
    Bewertungssegmente: High Rating (>= 4) / Low Rating (< 4)

    Warum Perzentile?
    Das 20. Perzentil bedeutet: 20 % der Bücher kosten weniger als dieser Wert.
    Das macht die Grenzen unabhängig von absoluten Preisen – dynamisch angepasst.
    """
    if df.empty:
        return df.assign(segment=pd.Series(dtype=str))

    d = df.copy()

    # Schwellenwerte für Preissegmente berechnen
    # quantile(0.20) = Preis, unter dem 20 % der Bücher liegen
    p20, p80 = map(float, (d["price"].quantile(0.20), d["price"].quantile(0.80)))

    def price_bucket(x: float) -> str:
        """Gibt das Preissegment für einen einzelnen Preis zurück."""
        if x <= p20:
            return f"Low Price: <{round(p20)}"
        if x <= p80:
            return f"Mid Price: >{round(p20)} & <{round(p80)}"
        return f"High Price: >{round(p80)}"

    # Preissegment-Spalte hinzufügen: apply() wendet price_bucket auf jede Zeile an
    d["price_bucket"] = d["price"].apply(price_bucket)

    # Bewertungssegment-Spalte hinzufügen
    # np.where(bedingung, wert_wenn_true, wert_wenn_false) – vektorisierte if-else-Logik
    d["rating_bucket"] = np.where(d["rating"] >= 4, "High Rating >=4", "Low Rating <4")

    # Kombination aus Preis- und Bewertungssegment
    d["segment"] = d["price_bucket"] + "\n" + d["rating_bucket"]

    return d


# =============================================================================
# Hidden Gems (versteckte Perlen)
# =============================================================================

def hidden_gems(df: pd.DataFrame, min_rating: float = 4.0, max_price_quantile: float = 0.35) -> pd.DataFrame:
    """Findet Bücher mit hoher Bewertung und niedrigem Preis ("Hidden Gems").

    Kriterien:
    - Bewertung >= min_rating (Standard: 4 Sterne)
    - Preis <= 35. Perzentil (unteres Preisdrittel)

    Gibt einen sortierten DataFrame mit den besten Deals zurück.
    """
    if df.empty:
        return df

    d = df.copy()

    # Preisgrenze: 35 % der Bücher kosten weniger als dieser Wert
    price_thr = float(d["price"].quantile(max_price_quantile))

    # Filtern: hohe Bewertung UND niedriger Preis
    gems = d[(d["rating"] >= min_rating) & (d["price"] <= price_thr)].copy()

    # Bestes Bewertung zuerst, bei gleicher Bewertung günstigste zuerst
    gems = gems.sort_values(["rating", "price"], ascending=[False, True])

    # Nur vorhandene Spalten zurückgeben
    cols = [
        c
        for c in ["title", "category", "price", "rating", "availability", "author", "publish_year"]
        if c in gems.columns
    ]
    return gems[cols]


# =============================================================================
# Heatmap-Datenquelle (Kategorie × Bewertung)
# =============================================================================

def category_rating_heatmap_source(df: pd.DataFrame) -> pd.DataFrame:
    """Bereitet Daten für eine Heatmap vor: Kategorie × Bewertung → Anzahl Bücher.

    Gibt einen DataFrame zurück mit den Spalten:
      category | rating | count | rating_label
    """
    if df.empty:
        return pd.DataFrame(columns=["category", "rating", "count"])

    # Zeilen mit fehlenden Kategorie- oder Bewertungsdaten entfernen
    d = df.dropna(subset=["category", "rating"]).copy()
    d["category"] = d["category"].astype(str)
    d["rating"] = d["rating"].astype(int)

    # Für jede Kombination (Kategorie, Bewertung) die Anzahl zählen
    pivot = d.groupby(["category", "rating"]).size().reset_index(name="count")

    # Lesbare Bewertungs-Beschriftung: "3 ⭐"
    pivot["rating_label"] = pivot["rating"].astype(str) + " ⭐"
    return pivot


# =============================================================================
# Automatische Texthinweise generieren
# =============================================================================

def generate_insights(df: pd.DataFrame) -> list[str]:
    """Generiert kurze automatische Erkenntnisse aus den Daten (Markdown-Strings).

    Beispiele:
    - "Teuerste Kategorie im Durchschnitt: Mystery (£24.50)"
    - "Beste Bewertung im Durchschnitt: Classics (4.3 ⭐)"
    - "Preis-Bewertungs-Korrelation: r = 0.02 (schwach)"
    """
    if df.empty:
        return ["No data available. Please run Refresh."]

    insights: list[str] = []

    # --- Teuerste Kategorie ---
    cat_price = df.groupby("category")["price"].mean().sort_values(ascending=False)
    if not cat_price.empty:
        insights.append(
            f"Most expensive category on average: **{cat_price.index[0]}** (avg £{cat_price.iloc[0]:.2f})."
        )

    # --- Bestbewertete Kategorie ---
    cat_rating = df.groupby("category")["rating"].mean().sort_values(ascending=False)
    if not cat_rating.empty:
        insights.append(
            f"Best-rated category on average: **{cat_rating.index[0]}** (avg {cat_rating.iloc[0]:.2f} ⭐)."
        )

    # --- Korrelation Preis vs. Bewertung ---
    # corr() berechnet den Pearson-Korrelationskoeffizient (-1 bis +1)
    # Werte nahe 0: kaum linearer Zusammenhang
    if df["price"].notna().any() and df["rating"].notna().any():
        corr = float(df["price"].corr(df["rating"]))
        insights.append(f"Price vs rating correlation: **r = {corr:.3f}** (near 0 ⇒ weak linear relationship).")

    # --- Anzahl Bücher ohne Cover ---
    if "cover_url" in df.columns:
        missing_cover = int((df["cover_url"].isna() | (df["cover_url"].astype(str).str.strip() == "")).sum())
        insights.append(f"**{missing_cover}** books currently have **no cover**.")

    # --- Bestes Preis-Leistungs-Buch ---
    try:
        vs = value_score(df)
        if not vs.empty:
            best = vs.iloc[0]
            insights.append(
                f"Best value: **{best['title']}** (score {best['value_score']:.2f}, {best['rating']} ⭐, £{best['price']:.2f})."
            )
    except Exception:
        pass

    # --- Anzahl überteuerte Bücher ---
    try:
        over = overpriced_detector(df)
        if isinstance(over, pd.DataFrame):
            insights.append(f"Overpriced candidates (default rule): **{len(over)}** books.")
    except Exception:
        pass

    return insights


# =============================================================================
# Value Score (Preis-Leistungs-Verhältnis)
# =============================================================================

def value_score(df: pd.DataFrame) -> pd.DataFrame:
    """Berechnet einen Preis-Leistungs-Score für jedes Buch.

    Formel: value_score = rating / log(price + 1)

    Warum log(price + 1)?
    - Der Logarithmus dämpft den Preiseinfluss: ein Buch für £2 vs £4 ist ein
      größerer Unterschied als £20 vs £22.
    - +1 verhindert log(0), falls ein Preis 0 wäre.

    Höherer Score = besseres Preis-Leistungs-Verhältnis.
    """
    if df.empty:
        return df

    # Zeilen mit fehlenden Preis- oder Bewertungsdaten entfernen
    d = df.dropna(subset=["price", "rating"]).copy()

    # clip(lower=0.01): Preis auf mindestens 0.01 begrenzen, um log(0) zu vermeiden
    d["price_safe"] = d["price"].clip(lower=0.01)

    # np.log1p(x) = log(x + 1) – numerisch stabiler als np.log(x + 1)
    d["value_score"] = d["rating"] / np.log1p(d["price_safe"])

    # Nur vorhandene Spalten zurückgeben
    cols = [
        c
        for c in ["title", "category", "price", "rating", "value_score", "availability", "author", "publish_year"]
        if c in d.columns
    ]
    # Bestes Preis-Leistungs-Verhältnis zuerst
    return d[cols].sort_values("value_score", ascending=False)


# =============================================================================
# Überteuerte Bücher erkennen
# =============================================================================

def overpriced_detector(
    df: pd.DataFrame,
    low_rating_max: float = 3.0,
    high_price_quantile: float = 0.80,
) -> pd.DataFrame:
    """Findet Bücher mit niedriger Bewertung und hohem Preis ("Overpriced").

    Kriterien:
    - Bewertung <= low_rating_max (Standard: max. 3 Sterne)
    - Preis >= 80. Perzentil (oberes Preisfünftel)

    Teuerste und schlechtbewertete Bücher werden zuerst angezeigt.
    """
    if df.empty:
        return df

    # Zeilen mit fehlenden Werten entfernen
    d = df.dropna(subset=["price", "rating"]).copy()

    # Preisgrenze: 80 % der Bücher kosten weniger als dieser Wert
    price_thr = float(d["price"].quantile(high_price_quantile))

    # Filtern: schlechte Bewertung UND hoher Preis
    bad = d[(d["rating"] <= low_rating_max) & (d["price"] >= price_thr)].copy()

    # Teuerste zuerst, bei gleichem Preis schlechteste Bewertung zuerst
    bad = bad.sort_values(["price", "rating"], ascending=[False, True])

    # Nur vorhandene Spalten zurückgeben
    cols = [
        c
        for c in ["title", "category", "price", "rating", "availability", "author", "publish_year"]
        if c in bad.columns
    ]
    return bad[cols]
