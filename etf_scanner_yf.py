import streamlit as st
import pandas as pd
import yfinance as yf

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="Scanner ETF ↔ Stocks (yfinance)",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Scanner ETF ↔ Stocks (Top holdings Yahoo Finance / yfinance)")
st.write(
    """
    Cet outil utilise **yfinance** (Yahoo Finance) pour récupérer les **top holdings** des ETF  
    et voir rapidement **dans quels ETF se retrouvent tes stocks**.
    
    ⚠️ Limite importante : Yahoo / yfinance ne donne ici que les **top holdings** (souvent top 10),
    pas forcément *tous* les constituents de l’ETF.
    """
)

# ---------------- SIDEBAR ----------------
st.sidebar.header("⚙️ Paramètres")

default_etfs = "SPY, QQQ, XLK, XLF, IWM"
etf_input = st.sidebar.text_area(
    "📦 Liste des ETF (séparés par des virgules)",
    value=default_etfs,
    help="Exemple : SPY, QQQ, XLF, XLK, IWM"
)

default_stocks = "AAPL, MSFT, TSLA, NVDA"
stocks_input = st.sidebar.text_area(
    "📈 Liste des stocks à analyser (optionnel, séparés par des virgules)",
    value=default_stocks,
    help="Laisse vide pour voir **tous** les top holdings des ETF"
)

upload_file = st.sidebar.file_uploader(
    "📤 Importer un CSV de stocks (colonne 'symbol')",
    type=["csv"],
    help="Optionnel : un fichier contenant une colonne 'symbol' avec les tickers."
)

run_scan = st.sidebar.button("🚀 Lancer le scan")


# ---------------- HELPERS ----------------
def parse_tickers(text: str):
    if not text:
        return []
    return [t.strip().upper() for t in text.split(",") if t.strip()]


@st.cache_data(show_spinner=True)
def get_etf_top_holdings_yf(etf_symbol: str) -> pd.DataFrame:
    """
    Récupère les top holdings d'un ETF via yfinance.
    Utilise Ticker.funds_data.top_holdings (Yahoo Finance).
    """
    try:
        ticker = yf.Ticker(etf_symbol)
        funds_data = ticker.funds_data  # FundsData object
        top = funds_data.top_holdings   # pd.DataFrame selon la doc

        if top is None or top.empty:
            return pd.DataFrame()

        df = top.copy()

        # Les colonnes typiques sont souvent : 'symbol', 'holdingName', 'holdingPercent'
        # On standardise les noms.
        rename_map = {
            "symbol": "stock",
            "holdingName": "stock_name",
            "holdingPercent": "weight_pct",
        }
        df = df.rename(columns=rename_map)

        # Si le poids est entre 0 et 1, on le convertit en %
        if "weight_pct" in df.columns:
            # Heuristique : si max < 1.0 on suppose que c'est une fraction
            if df["weight_pct"].max() <= 1.0:
                df["weight_pct"] = df["weight_pct"] * 100

        # On garde les colonnes utiles
        keep_cols = [c for c in ["stock", "stock_name", "weight_pct"] if c in df.columns]
        df = df[keep_cols]

        df["ETF"] = etf_symbol.upper()
        return df

    except Exception as e:
        st.warning(f"❗ Impossible de récupérer les top holdings pour {etf_symbol.upper()} : {e}")
        return pd.DataFrame()


def build_mapping(etfs, stocks_filter):
    """
    Construit un DataFrame avec les liens Stock ↔ ETF (via top holdings)
    + une matrice pivot pour visualisation type heatmap.
    """
    all_frames = []

    for etf in etfs:
        df_etf = get_etf_top_holdings_yf(etf)
        if df_etf.empty:
            st.warning(f"⚠️ Aucun top holding trouvé pour {etf.upper()} (ou pas un ETF/fonds reconnu).")
            continue

        all_frames.append(df_etf)

    if not all_frames:
        return pd.DataFrame(), pd.DataFrame()

    holdings_all = pd.concat(all_frames, ignore_index=True)

    # Filtre sur les stocks demandés (si fournis)
    if stocks_filter:
        holdings_filtered = holdings_all[holdings_all["stock"].isin(stocks_filter)].copy()
    else:
        holdings_filtered = holdings_all.copy()

    # Tri
    if "weight_pct" in holdings_filtered.columns:
        holdings_filtered = holdings_filtered.sort_values(
            ["stock", "weight_pct"], ascending=[True, False]
        )
    else:
        holdings_filtered = holdings_filtered.sort_values(["stock", "ETF"])

    # Matrice pivot pour heatmap (poids en %)
    if "weight_pct" in holdings_filtered.columns:
        pivot = holdings_filtered.pivot_table(
            index="stock",
            columns="ETF",
            values="weight_pct",
            aggfunc="sum"
        )
    else:
        pivot = pd.DataFrame()

    return holdings_filtered, pivot


# ---------------- MAIN LOGIC ----------------
etf_list = parse_tickers(etf_input)

# Construire la liste de stocks à partir du texte + fichier CSV
stocks_list = parse_tickers(stocks_input)

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
    if not etf_list:
        st.error("❌ Merci d'indiquer au moins un ETF.")
    else:
        with st.spinner("Récupération des top holdings des ETF via yfinance (Yahoo Finance)..."):
            df_links, df_matrix = build_mapping(etf_list, stocks_list)

        if df_links.empty:
            st.warning("Aucun lien Stock ↔ ETF trouvé avec ces paramètres.")
        else:
            st.subheader("📋 Tableau détaillé Stocks ↔ ETF (Top holdings)")

            st.write(
                "Chaque ligne représente un **top holding** : un stock présent dans un ETF, "
                "avec son poids (%) selon Yahoo Finance."
            )

            st.dataframe(df_links, use_container_width=True, height=400)

            # Bouton de téléchargement CSV
            csv = df_links.to_csv(index=False).encode("utf-8")
            st.download_button(
                "💾 Télécharger les résultats en CSV",
                data=csv,
                file_name="stock_etf_top_holdings_yf.csv",
                mime="text/csv"
            )

            if not df_matrix.empty:
                st.subheader("🧊 Matrice des poids (heatmap style)")
                st.write(
                    "Les valeurs représentent le **poids (%) du stock dans chaque ETF** "
                    "pour les top holdings."
                )
                st.dataframe(df_matrix, use_container_width=True, height=400)
            else:
                st.info("Pas de matrice possible (colonnes de poids manquantes).")

else:
    st.info(
        "👈 Entre tes ETF et éventuellement tes stocks, puis clique sur **🚀 Lancer le scan**.\n\n"
        "Aucune clé API n'est nécessaire : tout passe par **yfinance** (Yahoo Finance)."
    )
