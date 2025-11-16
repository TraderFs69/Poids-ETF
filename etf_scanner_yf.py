import streamlit as st
import pandas as pd
import yfinance as yf

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="Stocks dans quels ETF ? (yfinance)",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Stocks → ETF (Top holdings via yfinance)")
st.write(
    """
    Entres **une liste d’ETF** et **une liste de stocks**.  
    L’application utilise `yfinance` pour récupérer les **top holdings** de chaque ETF
    et te montre **quels stocks se retrouvent dans quels ETF**, avec leur poids (%).

    ⚠️ Limite : seulement les **top holdings** (souvent top 10) fournis par Yahoo Finance.
    """
)

# ---------------- SIDEBAR ----------------
st.sidebar.header("⚙️ Paramètres")

default_etfs = "SPY, QQQ, XLK, XLF, IWM"
etf_input = st.sidebar.text_area(
    "📦 Liste des ETF (séparés par des virgules)",
    value=default_etfs,
    help="Ex.: SPY, QQQ, XLK, XLF, IWM"
)

default_stocks = "AAPL, MSFT, TSLA, NVDA"
stocks_input = st.sidebar.text_area(
    "📈 Liste des stocks à analyser (séparés par des virgules)",
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
def get_etf_top_holdings(etf_symbol: str) -> pd.DataFrame:
    """
    Récupère les top holdings d'un ETF via yfinance.
    Utilise Ticker.funds_data.top_holdings (voir docs yfinance).
    """
    try:
        ticker = yf.Ticker(etf_symbol)
        funds_data = ticker.funds_data
        top = funds_data.top_holdings

        if top is None or top.empty:
            return pd.DataFrame()

        df = top.copy()

        # Colonnes typiques: 'symbol', 'holdingName', 'holdingPercent'
        rename_map = {
            "symbol": "stock",
            "holdingName": "stock_name",
            "holdingPercent": "weight_pct",
        }
        df = df.rename(columns=rename_map)

        # Si poids entre 0 et 1 → on le convertit en %
        if "weight_pct" in df.columns:
            if df["weight_pct"].max() <= 1.0:
                df["weight_pct"] = df["weight_pct"] * 100

        # On garde ce qui est utile
        keep_cols = [c for c in ["stock", "stock_name", "weight_pct"] if c in df.columns]
        df = df[keep_cols]

        df["ETF"] = etf_symbol.upper()
        return df

    except Exception as e:
        st.warning(f"❗ Impossible de récupérer les top holdings pour {etf_symbol.upper()} : {e}")
        return pd.DataFrame()


def build_stock_etf_mapping(etfs, stocks_filter):
    """
    Construit un DataFrame avec les liens Stock ↔ ETF
    sur base des top holdings yfinance.
    """
    all_frames = []

    for etf in etfs:
        df_etf = get_etf_top_holdings(etf)
        if df_etf.empty:
            st.warning(f"⚠️ Aucun top holding trouvé (ou pas reconnu comme ETF) pour {etf.upper()}.")
            continue
        all_frames.append(df_etf)

    if not all_frames:
        return pd.DataFrame(), pd.DataFrame()

    holdings_all = pd.concat(all_frames, ignore_index=True)

    # Filtre les stocks si une liste est fournie
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

    # Matrice pivot stock x ETF
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
stocks_list = parse_tickers(stocks_input)

# Merge avec CSV éventuel
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
        st.error("❌ Indique au moins un ETF.")
    elif not stocks_list:
        st.error("❌ Indique au moins un stock.")
    else:
        with st.spinner("Récupération des top holdings des ETF via yfinance..."):
            df_links, df_matrix = build_stock_etf_mapping(etf_list, stocks_list)

        if df_links.empty:
            st.warning("Aucun lien Stock ↔ ETF trouvé avec ces paramètres (dans les top holdings).")
        else:
            st.subheader("📋 Stocks présents dans les top holdings des ETF")

            st.write(
                "Chaque ligne représente un **stock** présent dans les **top holdings** d’un ETF, "
                "avec son poids (%) estimé."
            )

            st.dataframe(df_links, use_container_width=True, height=500)

            csv = df_links.to_csv(index=False).encode("utf-8")
            st.download_button(
                "💾 Télécharger les résultats en CSV",
                data=csv,
                file_name="stock_etf_top_holdings_yf.csv",
                mime="text/csv"
            )

            if not df_matrix.empty:
                st.subheader("🧊 Matrice poids (%) stocks × ETF")
                st.write("Les valeurs représentent le **poids (%)** du stock dans chaque ETF (top holdings).")
                st.dataframe(df_matrix, use_container_width=True, height=400)
else:
    st.info(
        "👈 Entre une liste d’ETF et une liste de stocks, puis clique sur **🚀 Lancer le scan**.\n\n"
        "Les données viennent de Yahoo Finance via la librairie `yfinance`."
    )
