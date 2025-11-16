import streamlit as st
import pandas as pd
import requests

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="ETF Exposure ↔ Stocks (ETFdb)",
    page_icon="📊",
    layout="wide"
)

st.title("📊 ETF Exposure ↔ Stocks (via ETFdb)")
st.write(
    """
    Cet outil récupère, pour **chaque stock**, la liste des **ETFs qui le détiennent**  
    à partir des pages publiques d'**ETFdb** (ex.: https://etfdb.com/stock/AAPL/).

    🔹 100 % gratuit, aucune clé API  
    🔹 Résultat : tableau *Stock → ETF, Catégorie, Poids (%), Expense Ratio*  
    🔹 Export CSV pour ton journal ou d'autres scripts
    """
)

# ---------------- SIDEBAR ----------------
st.sidebar.header("⚙️ Paramètres")

default_stocks = "AAPL, MSFT, TSLA, NVDA"
stocks_input = st.sidebar.text_area(
    "📈 Liste des stocks (séparés par des virgules)",
    value=default_stocks,
    help="Ex.: AAPL, MSFT, TSLA, NVDA"
)

upload_file = st.sidebar.file_uploader(
    "📤 Importer un CSV de stocks (colonne 'symbol')",
    type=["csv"],
    help="Optionnel : fichier contenant une colonne 'symbol' avec les tickers."
)

run_scan = st.sidebar.button("🚀 Lancer le scan")


# ---------------- HELPERS ----------------
def parse_tickers(text: str):
    if not text:
        return []
    return [t.strip().upper() for t in text.split(",") if t.strip()]


@st.cache_data(show_spinner=True)
def get_stock_etf_exposure_etfdb(symbol: str) -> pd.DataFrame:
    """
    Va chercher la page ETFdb pour un stock (ex.: https://etfdb.com/stock/AAPL/)
    et essaie de parser le tableau "ETFs with <stock> Exposure".

    Retourne un DataFrame avec au moins :
    - stock
    - etf_ticker
    - etf_name
    - category
    - expense_ratio
    - weighting
    """

    url = f"https://etfdb.com/stock/{symbol}/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        st.warning(f"❗ Impossible de récupérer la page ETFdb pour {symbol}: {e}")
        return pd.DataFrame()

    try:
        # ETFdb a un tableau principal "ETFs with <stock> Exposure"
        tables = pd.read_html(resp.text)
    except ValueError:
        # Aucun tableau trouvé
        st.warning(f"⚠️ Aucun tableau détecté sur ETFdb pour {symbol}.")
        return pd.DataFrame()

    if not tables:
        st.warning(f"⚠️ Aucun tableau détecté sur ETFdb pour {symbol}.")
        return pd.DataFrame()

    # En général, le premier tableau est le bon
    df = tables[0].copy()

    # Aplanir les colonnes si MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    else:
        df.columns = [str(c) for c in df.columns]

    # On essaie de repérer les colonnes importantes
    col_map = {
        "Ticker": None,
        "ETF": None,
        "ETF Database Category": None,
        "Expense Ratio": None,
        "Weighting": None,
    }

    for col in df.columns:
        col_norm = col.strip().lower()
        if "ticker" in col_norm and col_map["Ticker"] is None:
            col_map["Ticker"] = col
        elif col_norm == "etf" and col_map["ETF"] is None:
            col_map["ETF"] = col
        elif "database category" in col_norm and col_map["ETF Database Category"] is None:
            col_map["ETF Database Category"] = col
        elif "expense" in col_norm and col_map["Expense Ratio"] is None:
            col_map["Expense Ratio"] = col
        elif "weight" in col_norm and col_map["Weighting"] is None:
            col_map["Weighting"] = col

    # On garde seulement les colonnes qu'on a réussi à identifier
    keep_real_cols = [c for c in col_map.values() if c is not None]
    if not keep_real_cols:
        st.warning(f"⚠️ Impossible d'identifier les colonnes du tableau pour {symbol}.")
        return pd.DataFrame()

    df = df[keep_real_cols].copy()

    # Renommer en noms standard
    rename_to = {}
    for canonical, real_col in col_map.items():
        if real_col is not None:
            rename_to[real_col] = canonical

    df = df.rename(columns=rename_to)

    # Supprimer les éventuelles lignes d'en-têtes répétées (quand la table est paginée dans le HTML)
    if "Ticker" in df.columns:
        df = df[df["Ticker"].astype(str).str.upper() != "TICKER"]

    # Nettoyages simples
    if "Expense Ratio" in df.columns:
        df["Expense Ratio"] = df["Expense Ratio"].astype(str).str.strip()
    if "Weighting" in df.columns:
        df["Weighting"] = df["Weighting"].astype(str).str.strip()

    # Ajouter le symbole du stock
    df["stock"] = symbol.upper()

    # Réordonner les colonnes pour quelque chose de propre
    ordered_cols = ["stock", "Ticker", "ETF", "ETF Database Category", "Expense Ratio", "Weighting"]
    ordered_cols = [c for c in ordered_cols if c in df.columns]
    df = df[ordered_cols]

    return df


def build_exposure(stocks):
    """
    Construit un DataFrame consolidé Stock → ETFs.
    """
    frames = []
    for s in stocks:
        sub = get_stock_etf_exposure_etfdb(s)
        if sub.empty:
            st.warning(f"⚠️ Aucun ETF trouvé (ou parsing impossible) pour {s}.")
        else:
            frames.append(sub)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    return combined


# ---------------- MAIN LOGIC ----------------
stocks_list = parse_tickers(stocks_input)

# Si CSV uploadé, on fusionne
if upload_file is not None:
    try:
        df_upload = pd.read_csv(upload_file)
        if "symbol" in df_upload.columns:
            from_csv = df_upload["symbol"].astype(str).str.upper().tolist()
            stocks_list = sorted(set(stocks_list + from_csv))
        else:
            st.sidebar.warning("Le fichier CSV doit contenir une colonne 'symbol'.")
    except Exception as e:
        st.sidebar.warning(f"Erreur lors de la lecture du CSV : {e}")

if run_scan:
    if not stocks_list:
        st.error("❌ Merci d'indiquer au moins un stock.")
    else:
        with st.spinner("Récupération de l'exposition ETF pour chaque stock via ETFdb..."):
            df_result = build_exposure(stocks_list)

        if df_result.empty:
            st.warning("Aucun résultat exploitable trouvé avec ces paramètres.")
        else:
            st.subheader("📋 Exposition ETF par stock")

            st.write(
                "Chaque ligne représente un **ETF qui détient ce stock**, "
                "avec sa catégorie, son expense ratio et le **poids du stock dans l’ETF**."
            )

            st.dataframe(df_result, use_container_width=True, height=500)

            # Bouton de téléchargement
            csv = df_result.to_csv(index=False).encode("utf-8")
            st.download_button(
                "💾 Télécharger en CSV",
                data=csv,
                file_name="stock_etf_exposure_etfdb.csv",
                mime="text/csv"
            )
else:
    st.info(
        "👈 Entre une liste de stocks (et éventuellement un CSV) puis clique sur **🚀 Lancer le scan**.\n\n"
        "Les données proviennent de ETFdb (pages publiques `https://etfdb.com/stock/<SYMBOL>/`)."
    )
