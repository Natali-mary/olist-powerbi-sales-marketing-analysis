# =============================================================================
# data_processor.py – Hilfsfunktionen zum Verarbeiten von Buchdaten
# =============================================================================
# Diese Datei enthält die Klasse DataProcessor mit Methoden zum:
#   - Umwandeln von Rohdaten in einen pandas DataFrame
#   - Filtern des DataFrames (nach Kategorie, Preis, Bewertung, Titel)
#   - Berechnen von Preisstatistiken nach Kategorie
# =============================================================================

import pandas as pd   # pandas: Bibliothek für Tabellen (DataFrames)


class DataProcessor:
    """Verarbeitet und filtert Buchdaten als pandas DataFrame."""

    def to_dataframe(self, books: list) -> pd.DataFrame:
        """Wandelt eine Liste von Buch-Dictionaries in einen pandas DataFrame um.

        Beispiel-Eingabe:
          [{"title": "Clean Code", "price": "12.99", "rating": "4"}, ...]

        Stellt sicher, dass 'price' und 'rating' als Zahlen gespeichert sind,
        nicht als Strings.
        """
        df = pd.DataFrame(books)   # Liste von Dicts → Tabelle

        # pd.to_numeric wandelt Strings wie "12.99" in float 12.99 um
        # errors="coerce": Wenn ein Wert nicht umgewandelt werden kann, wird NaN gesetzt
        for col in ("price", "rating"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def filter_df(
        self,
        df: pd.DataFrame,
        categories: list,
        price_min: float,
        price_max: float,
        ratings: list,
        title_query: str,
    ) -> pd.DataFrame:
        """Filtert einen DataFrame nach den angegebenen Kriterien.

        categories:  Liste erlaubter Kategorien (leer = alle Kategorien)
        price_min:   Mindestpreis (inklusiv)
        price_max:   Höchstpreis (inklusiv)
        ratings:     Liste erlaubter Bewertungen (leer = alle Bewertungen)
        title_query: Suchtext im Buchtitel (Groß-/Kleinschreibung egal)

        Gibt einen neuen gefilterten DataFrame zurück (Original bleibt unverändert).
        """
        out = df.copy()   # Kopie erstellen, damit das Original nicht verändert wird

        # Kategorien filtern: nur Zeilen behalten, deren Kategorie in der Liste ist
        # isin() = "ist in der Liste enthalten?"
        if categories:
            out = out[out["category"].isin(categories)]

        # Preis filtern: between() prüft ob price >= price_min UND price <= price_max
        out = out[out["price"].between(price_min, price_max)]

        # Bewertungen filtern
        if ratings:
            out = out[out["rating"].isin(ratings)]

        # Titelsuche: str.contains() sucht einen Teilstring im Titel
        # case=False: Groß-/Kleinschreibung ignorieren ("python" findet auch "Python")
        # na=False:   Fehlende Werte (NaN) werden als "nicht gefunden" behandelt
        if title_query:
            out = out[out["title"].str.contains(title_query, case=False, na=False)]

        return out

    def price_stats_by_category(self, df: pd.DataFrame) -> pd.DataFrame:
        """Berechnet Preisstatistiken (Durchschnitt, Min, Max) gruppiert nach Kategorie.

        Gibt einen DataFrame zurück mit den Spalten:
          category | mean | min | max
        Sortiert nach Durchschnittspreis (absteigend).
        """
        return (
            df.groupby("category")["price"]   # Nach Kategorie gruppieren, Spalte "price" auswählen
            .agg(["mean", "min", "max"])       # Drei Kennzahlen berechnen
            .reset_index()                     # "category" von Index → normale Spalte
            .sort_values("mean", ascending=False)  # Teuerste Kategorie oben
        )
