from decimal import Decimal, InvalidOperation
import json
import math
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from db import load_table, run_query


SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_TABLE_ROWS = 500
MAX_CANDLE_POINTS = 500
PAGERANK_SOURCE_TABLE = "LIGHTGCN_USER_FACTORS"
ITEM_FACTORS_TABLE = "LIGHTGCN_ITEM_FACTORS"
PROJECT_TOKEN_TABLE = "BIGDATA_DB.STAGING.TOKEN_IN_PROJECT"
TOKEN_RECOMMENDATIONS_TABLE = "LIGHTGCN_TOKEN_RECOMMENDATIONS"
MENTORS_TABLE = "RECOMMENDATION_TOP5_MENTORS"
ANOMALY_API_URL = "https://tall-debating-seventy.ngrok-free.dev/api/anomalies"
MARKET_TREND_API_URL = "https://tall-debating-seventy.ngrok-free.dev/api/trending"
GECKOTERMINAL_BASE_URL = "https://api.geckoterminal.com/api/v2"
GECKOTERMINAL_NETWORK = "eth"
TABLE_ROW_HEIGHT = 44
TABLE_HEADER_HEIGHT = 42
TOP5_TABLE_ROW_HEIGHT = 36
BINANCE_INTERVALS = {
    "1 phút": "1m",
    "5 phút": "5m",
    "15 phút": "15m",
    "1 giờ": "1h",
    "4 giờ": "4h",
    "1 ngày": "1d",
}
BINANCE_QUOTE_PRIORITY = ["USDT", "FDUSD", "USDC", "BTC", "ETH", "BNB"]
GECKO_INTERVALS = {
    "1 phút": ("minute", 1),
    "5 phút": ("minute", 5),
    "15 phút": ("minute", 15),
    "1 giờ": ("hour", 1),
    "4 giờ": ("hour", 4),
    "1 ngày": ("day", 1),
}


st.set_page_config(
    page_title="Crypto Dashboard",
    page_icon="🪙",
    layout="wide",
)


@st.cache_data(ttl=3600)
def get_all_data():
    pagerank = run_query(
        f"""
        SELECT USER_ID AS ID, PAGERANK
        FROM {PAGERANK_SOURCE_TABLE}
        ORDER BY PAGERANK DESC
        """
    )
    fpgrowth = load_table("FPGROWTH_RULES")
    portfolio = load_table("USER_PORTFOLIOS")
    tokens = load_table("TOKENS_INDEXED")
    return pagerank, fpgrowth, portfolio, tokens


@st.cache_data(ttl=3600)
def get_portfolio_enriched(_df_po, _df_tk):
    df_po = _df_po.copy()
    df_tk = _df_tk.copy()

    df_po["TOKEN_ID"] = pd.to_numeric(df_po["TOKEN_ID"], errors="coerce").astype("Int64")
    df_po["BALANCE"] = pd.to_numeric(df_po["BALANCE"], errors="coerce")
    df_po["TX_COUNT"] = pd.to_numeric(df_po["TX_COUNT"], errors="coerce").fillna(0)
    df_tk["TOKEN_ID"] = pd.to_numeric(df_tk["TOKEN_ID"], errors="coerce").astype("Int64")

    return df_po.merge(
        df_tk[["TOKEN_ID", "SYMBOL", "NAME", "ADDRESS"]],
        on="TOKEN_ID",
        how="left",
    )


@st.cache_data(ttl=3600)
def query_wallet_candidates(query: str) -> pd.DataFrame:
    pattern = f"%{query.strip()}%"
    return run_query(
        f"""
        SELECT USER_ID AS ID, PAGERANK
        FROM {PAGERANK_SOURCE_TABLE}
        WHERE CAST(USER_ID AS VARCHAR) LIKE %s
        ORDER BY PAGERANK DESC
        """,
        (pattern,),
    )


@st.cache_data(ttl=3600)
def query_wallet_pagerank(user_id: str) -> pd.DataFrame:
    return run_query(
        f"""
        SELECT USER_ID AS ID, PAGERANK
        FROM {PAGERANK_SOURCE_TABLE}
        WHERE CAST(USER_ID AS VARCHAR) = %s
        ORDER BY PAGERANK DESC
        """,
        (str(user_id),),
    )


@st.cache_data(ttl=3600)
def query_wallet_holdings(user_id: str) -> pd.DataFrame:
    return run_query(
        """
        SELECT p.*, t.SYMBOL, t.NAME, t.ADDRESS
        FROM USER_PORTFOLIOS p
        LEFT JOIN TOKENS_INDEXED t ON p.TOKEN_ID = t.TOKEN_ID
        WHERE CAST(p.USER_ID AS VARCHAR) = %s
        ORDER BY p.BALANCE DESC
        """,
        (str(user_id),),
    )


@st.cache_data(ttl=3600)
def query_tokens(query: str) -> pd.DataFrame:
    q = query.strip()
    pattern = f"%{q.upper()}%"
    id_pattern = f"%{q}%"
    return run_query(
        """
        SELECT *
        FROM TOKENS_INDEXED
        WHERE UPPER(COALESCE(SYMBOL, '')) LIKE %s
           OR UPPER(COALESCE(NAME, '')) LIKE %s
           OR UPPER(COALESCE(ADDRESS, '')) LIKE %s
           OR CAST(TOKEN_ID AS VARCHAR) LIKE %s
        """,
        (pattern, pattern, pattern, id_pattern),
    )


@st.cache_data(ttl=3600)
def query_token_by_id(token_id: str) -> pd.DataFrame:
    return run_query(
        """
        SELECT *
        FROM TOKENS_INDEXED
        WHERE CAST(TOKEN_ID AS VARCHAR) = %s
        """,
        (str(token_id),),
    )


@st.cache_data(ttl=3600)
def query_token_by_symbol(symbol: str) -> pd.DataFrame:
    return run_query(
        """
        SELECT *
        FROM TOKENS_INDEXED
        WHERE UPPER(SYMBOL) = %s
        """,
        (str(symbol).upper(),),
    )


def quote_exact_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def qualified_information_schema(table_name: str) -> tuple[str, str, str] | None:
    parts = [part.strip() for part in str(table_name).split(".") if part.strip()]
    if len(parts) == 3 and all(SQL_IDENTIFIER_RE.fullmatch(part) for part in parts):
        database, schema, table = parts
        return f"{database}.INFORMATION_SCHEMA.COLUMNS", schema, table
    if len(parts) == 2 and all(SQL_IDENTIFIER_RE.fullmatch(part) for part in parts):
        schema, table = parts
        return "INFORMATION_SCHEMA.COLUMNS", schema, table
    if len(parts) == 1 and SQL_IDENTIFIER_RE.fullmatch(parts[0]):
        return "INFORMATION_SCHEMA.COLUMNS", "", parts[0]
    return None


@st.cache_data(ttl=3600)
def exact_table_columns(table_name: str) -> dict[str, str]:
    info = qualified_information_schema(table_name)
    if not info:
        return {}
    info_schema, schema, table = info
    if schema:
        query = f"""
            SELECT COLUMN_NAME
            FROM {info_schema}
            WHERE UPPER(TABLE_SCHEMA) = UPPER(%s)
              AND UPPER(TABLE_NAME) = UPPER(%s)
        """
        params = (schema, table)
    else:
        query = f"""
            SELECT COLUMN_NAME
            FROM {info_schema}
            WHERE TABLE_SCHEMA = CURRENT_SCHEMA()
              AND UPPER(TABLE_NAME) = UPPER(%s)
        """
        params = (table,)

    try:
        cols = run_query(query, params)
    except Exception:
        return {}
    if cols.empty or "COLUMN_NAME" not in cols.columns:
        return {}
    return {str(col).upper(): str(col) for col in cols["COLUMN_NAME"].dropna()}


def exact_column_for(table_name: str, candidates: list[str]) -> str | None:
    columns = exact_table_columns(table_name)
    for candidate in candidates:
        found = columns.get(candidate.upper())
        if found:
            return found
    return None


def project_token_columns() -> tuple[str | None, str | None]:
    columns = exact_table_columns(PROJECT_TOKEN_TABLE)
    token_id_col = exact_column_for(PROJECT_TOKEN_TABLE, ["TOKEN_ID", "ITEM_ID", "ID"])
    address_col = exact_column_for(
        PROJECT_TOKEN_TABLE,
        ["TOKEN_ADDRESS", "ADDRESS", "CONTRACT_ADDRESS", "TOKEN_CONTRACT_ADDRESS", "CONTRACT", "TOKEN_ADDR"],
    )

    if not token_id_col:
        for normalized, original in columns.items():
            if "TOKEN" in normalized and normalized.endswith("ID"):
                token_id_col = original
                break
    if not address_col:
        for normalized, original in columns.items():
            if any(key in normalized for key in ["ADDRESS", "ADRESS", "CONTRACT", "ADDR"]):
                address_col = original
                break
    return token_id_col, address_col


@st.cache_data(ttl=3600)
def query_project_tokens(query: str) -> pd.DataFrame:
    q = str(query or "").strip()
    if not q:
        return pd.DataFrame()

    token_id_col, address_col = project_token_columns()
    if not token_id_col or not address_col:
        return pd.DataFrame()

    token_id_q = quote_exact_identifier(token_id_col)
    address_q = quote_exact_identifier(address_col)
    q_upper = q.upper()
    pattern = f"%{q_upper}%"
    return run_query(
        f"""
        SELECT
            p.{token_id_q} AS TOKEN_ID,
            COALESCE(t.SYMBOL, CAST(p.{token_id_q} AS VARCHAR)) AS SYMBOL,
            COALESCE(t.NAME, 'Token ' || CAST(p.{token_id_q} AS VARCHAR)) AS NAME,
            LOWER(CAST(p.{address_q} AS VARCHAR)) AS ADDRESS,
            t.DECIMALS,
            t.TOTAL_SUPPLY
        FROM {PROJECT_TOKEN_TABLE} p
        LEFT JOIN TOKENS_INDEXED t
            ON CAST(t.TOKEN_ID AS VARCHAR) = CAST(p.{token_id_q} AS VARCHAR)
            OR LOWER(t.ADDRESS) = LOWER(CAST(p.{address_q} AS VARCHAR))
        WHERE CAST(p.{token_id_q} AS VARCHAR) = %s
           OR LOWER(CAST(p.{address_q} AS VARCHAR)) = LOWER(%s)
           OR UPPER(COALESCE(t.SYMBOL, '')) = %s
           OR UPPER(COALESCE(t.NAME, '')) = %s
           OR UPPER(COALESCE(t.SYMBOL, '')) LIKE %s
           OR UPPER(COALESCE(t.NAME, '')) LIKE %s
        ORDER BY
            CASE
                WHEN CAST(p.{token_id_q} AS VARCHAR) = %s THEN 0
                WHEN LOWER(CAST(p.{address_q} AS VARCHAR)) = LOWER(%s) THEN 0
                WHEN UPPER(COALESCE(t.SYMBOL, '')) = %s THEN 1
                WHEN UPPER(COALESCE(t.NAME, '')) = %s THEN 1
                ELSE 2
            END,
            COALESCE(t.SYMBOL, ''),
            CAST(p.{token_id_q} AS VARCHAR)
        LIMIT 50
        """,
        (q, q, q_upper, q_upper, pattern, pattern, q, q, q_upper, q_upper),
    )


@st.cache_data(ttl=3600)
def query_project_token_by_id(token_id: str) -> pd.DataFrame:
    q = id_to_text(token_id)
    if not q:
        return pd.DataFrame()
    return query_project_tokens(q)


@st.cache_data(ttl=3600)
def query_project_token_by_address(address: str) -> pd.DataFrame:
    normalized = normalize_token_address(address)
    if not normalized:
        return pd.DataFrame()
    return query_project_tokens(normalized)


@st.cache_data(ttl=3600)
def query_item_factor_tokens(query: str) -> pd.DataFrame:
    q = query.strip()
    token_col = token_id_column_for(ITEM_FACTORS_TABLE)
    item_table = quote_identifier(ITEM_FACTORS_TABLE)
    token_col_q = quote_identifier(token_col) if token_col else None
    if not q or not item_table or not token_col_q:
        return pd.DataFrame()

    pattern = f"%{q.upper()}%"
    exact_symbol = q.upper()
    return run_query(
        f"""
        SELECT
            i.{token_col_q} AS TOKEN_ID,
            t.SYMBOL,
            t.NAME,
            t.ADDRESS,
            t.DECIMALS,
            t.TOTAL_SUPPLY
        FROM {item_table} i
        LEFT JOIN TOKENS_INDEXED t
            ON CAST(i.{token_col_q} AS VARCHAR) = CAST(t.TOKEN_ID AS VARCHAR)
        WHERE CAST(i.{token_col_q} AS VARCHAR) = %s
           OR UPPER(COALESCE(t.SYMBOL, '')) = %s
           OR UPPER(COALESCE(t.SYMBOL, '')) LIKE %s
           OR UPPER(COALESCE(t.NAME, '')) LIKE %s
           OR UPPER(COALESCE(t.ADDRESS, '')) LIKE %s
        ORDER BY
            CASE
                WHEN CAST(i.{token_col_q} AS VARCHAR) = %s THEN 0
                WHEN UPPER(COALESCE(t.SYMBOL, '')) = %s THEN 1
                ELSE 2
            END,
            COALESCE(t.SYMBOL, '')
        LIMIT 100
        """,
        (q, exact_symbol, pattern, pattern, pattern, q, exact_symbol),
    )


@st.cache_data(ttl=3600)
def query_item_factor_by_id(token_id: str) -> pd.DataFrame:
    token_col = token_id_column_for(ITEM_FACTORS_TABLE)
    item_table = quote_identifier(ITEM_FACTORS_TABLE)
    token_col_q = quote_identifier(token_col) if token_col else None
    if not token_id or not item_table or not token_col_q:
        return pd.DataFrame()

    return run_query(
        f"""
        SELECT
            i.{token_col_q} AS TOKEN_ID,
            t.SYMBOL,
            t.NAME,
            t.ADDRESS,
            t.DECIMALS,
            t.TOTAL_SUPPLY
        FROM {item_table} i
        LEFT JOIN TOKENS_INDEXED t
            ON CAST(i.{token_col_q} AS VARCHAR) = CAST(t.TOKEN_ID AS VARCHAR)
        WHERE CAST(i.{token_col_q} AS VARCHAR) = %s
        """,
        (str(token_id),),
    )


@st.cache_data(ttl=3600)
def query_token_holders(token_id: str) -> pd.DataFrame:
    return run_query(
        """
        SELECT p.*, t.SYMBOL, t.NAME, t.ADDRESS
        FROM USER_PORTFOLIOS p
        LEFT JOIN TOKENS_INDEXED t ON p.TOKEN_ID = t.TOKEN_ID
        WHERE CAST(p.TOKEN_ID AS VARCHAR) = %s
        ORDER BY p.BALANCE DESC
        """,
        (str(token_id),),
    )


df_pr, df_fp, df_po, df_tk = get_all_data()

if "PAGERANK" in df_pr.columns:
    df_pr["PAGERANK"] = pd.to_numeric(df_pr["PAGERANK"], errors="coerce")
for metric_col in ["CONFIDENCE", "LIFT", "SUPPORT"]:
    if metric_col in df_fp.columns:
        df_fp[metric_col] = pd.to_numeric(df_fp[metric_col], errors="coerce")

df_po_rich = get_portfolio_enriched(df_po, df_tk)


def as_text(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("")


def id_to_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass

    text = str(value).strip()
    try:
        number = Decimal(text)
        if number == number.to_integral_value():
            return str(int(number))
    except (InvalidOperation, ValueError):
        pass

    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def safe_float(value, default=0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def fmt_score(value) -> str:
    return f"{safe_float(value):.8f}" if pd.notna(value) else "N/A"


def fmt_number(value) -> str:
    if pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):,.8g}"
    except (TypeError, ValueError):
        return str(value)


def compact_histogram(
    series: pd.Series,
    *,
    bins: int,
    x_name: str,
    y_name: str,
    upper_quantile: float | None = None,
) -> pd.DataFrame:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if upper_quantile is not None and not values.empty:
        values = values[values <= values.quantile(upper_quantile)]
    if values.empty:
        return pd.DataFrame(columns=[x_name, y_name])

    counts = pd.cut(values, bins=bins).value_counts(sort=False)
    return pd.DataFrame(
        {
            x_name: [interval.mid for interval in counts.index],
            y_name: counts.to_numpy(),
        }
    )


def compact_for_browser(df: pd.DataFrame, max_rows: int = MAX_TABLE_ROWS) -> pd.DataFrame:
    if len(df) <= max_rows:
        return df.reset_index(drop=True)
    st.caption(f"Hiển thị {max_rows:,}/{len(df):,} dòng đầu để tránh quá tải browser.")
    return df.head(max_rows).reset_index(drop=True)


def table_height(row_count: int, max_height: int = 540) -> int:
    visible_rows = max(1, min(int(row_count), MAX_TABLE_ROWS))
    return min(max_height, TABLE_HEADER_HEIGHT + visible_rows * TABLE_ROW_HEIGHT + 6)


def top5_table_height(row_count: int) -> int:
    visible_rows = max(1, min(int(row_count), 5))
    return TABLE_HEADER_HEIGHT + visible_rows * TOP5_TABLE_ROW_HEIGHT + 8


def log_tick_values(values: pd.Series, max_ticks: int = 7) -> tuple[list[float], list[str]]:
    numeric = pd.to_numeric(values, errors="coerce")
    numeric = numeric[numeric > 0].dropna()
    if numeric.empty:
        return [], []

    min_exp = math.floor(math.log10(float(numeric.min())))
    max_exp = math.ceil(math.log10(float(numeric.max())))
    span = max(1, max_exp - min_exp)
    target_step = math.ceil(span / max(1, max_ticks - 1))
    step = next((candidate for candidate in [1, 2, 3, 5, 10, 20, 25, 50, 100] if candidate >= target_step), target_step)
    start_exp = math.floor(min_exp / step) * step
    end_exp = math.ceil(max_exp / step) * step
    exponents = list(range(start_exp, end_exp + 1, step))

    def label_for(exp: int) -> str:
        if exp == 0:
            return "1"
        if 0 < exp <= 5:
            return f"{10 ** exp:,}"
        return f"10^{exp}"

    ticks = [10 ** exp for exp in exponents]
    labels = [label_for(exp) for exp in exponents]
    return ticks, labels


def apply_log_axis(fig, axis: str, values: pd.Series, title: str):
    ticks, labels = log_tick_values(values)
    axis_args = dict(type="log", title=title, tickangle=0)
    if ticks:
        axis_args.update(tickvals=ticks, ticktext=labels)
    if axis == "x":
        fig.update_xaxes(**axis_args)
    else:
        fig.update_yaxes(**axis_args)


def power_bucket_counts(series: pd.Series, value_name: str = "Số lượng") -> pd.DataFrame:
    values = pd.to_numeric(series, errors="coerce").dropna()
    positive = values[values > 0]
    if positive.empty:
        return pd.DataFrame({"Bucket": [], value_name: []})

    exponents = positive.apply(lambda value: math.floor(math.log10(float(value))))
    counts = exponents.value_counts().sort_index()
    return pd.DataFrame(
        {
            "Bucket": [f"10^{int(exp)}" if int(exp) != 0 else "1" for exp in counts.index],
            value_name: counts.to_numpy(),
        }
    )


def balance_bar_figure(df: pd.DataFrame, *, title_y: str = "Số dư"):
    plot_df = df.copy()
    plot_df["BALANCE"] = pd.to_numeric(plot_df["BALANCE"], errors="coerce")
    plot_df = plot_df[plot_df["BALANCE"] > 0].sort_values("BALANCE", ascending=False).head(20)
    if plot_df.empty:
        return None

    ticks, labels = log_tick_values(plot_df["BALANCE"])
    fig = px.bar(
        plot_df,
        x="SYMBOL",
        y="BALANCE",
        template="plotly_dark",
        color="SYMBOL",
        text=plot_df["BALANCE"].map(fmt_number),
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        height=360,
        margin=dict(t=20, b=20, l=10, r=10),
        showlegend=False,
        yaxis_title=title_y,
        xaxis_title="Token",
    )
    fig.update_yaxes(type="log", tickvals=ticks, ticktext=labels)
    return fig


def pagerank_ecdf(df: pd.DataFrame, max_points: int = 1200) -> pd.DataFrame:
    values = pd.to_numeric(df["PAGERANK"], errors="coerce").dropna()
    values = values[values > 0].sort_values()
    if values.empty:
        return pd.DataFrame(columns=["PAGERANK", "Tỷ lệ tích lũy"])
    ecdf = pd.DataFrame(
        {
            "PAGERANK": values.to_numpy(),
            "Tỷ lệ tích lũy": (range(1, len(values) + 1)),
        }
    ).assign(**{"Tỷ lệ tích lũy": lambda d: d["Tỷ lệ tích lũy"] / len(values)})
    if len(ecdf) > max_points:
        sample_idx = pd.Index(pd.Series(range(len(ecdf))).quantile(
            [i / (max_points - 1) for i in range(max_points)]
        ).round().astype(int).unique())
        ecdf = ecdf.iloc[sample_idx].reset_index(drop=True)
    return ecdf


def add_empty_padding(df: pd.DataFrame, target_rows: int = 5) -> pd.DataFrame:
    if len(df) >= target_rows:
        return df
    rows = target_rows - len(df)
    padding = pd.DataFrame([{col: "" for col in df.columns} for _ in range(rows)])
    return pd.concat([df, padding], ignore_index=True)


def parse_tokens(value) -> list[str]:
    return [token.strip() for token in str(value).split(",") if token and token.strip()]


def selected_row(event, source_df: pd.DataFrame):
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")

    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows")

    if rows:
        return source_df.iloc[int(rows[0])]
    return None


def selectable_dataframe(
    source_df: pd.DataFrame,
    *,
    key: str,
    height: int | None = 320,
    columns: list[str] | None = None,
    display_df: pd.DataFrame | None = None,
    hide_index: bool = True,
):
    source = source_df.reset_index(drop=True)
    view = display_df.copy() if display_df is not None else source[columns].copy() if columns else source.copy()
    if len(view) > MAX_TABLE_ROWS:
        st.caption(f"Hiển thị {MAX_TABLE_ROWS:,}/{len(view):,} dòng đầu để tránh quá tải browser.")
        view = view.head(MAX_TABLE_ROWS).reset_index(drop=True)
        source = source.head(MAX_TABLE_ROWS).reset_index(drop=True)
    resolved_height = table_height(len(view)) if height is None else height
    try:
        event = st.dataframe(
            view,
            use_container_width=True,
            height=resolved_height,
            hide_index=hide_index,
            on_select="rerun",
            selection_mode="single-row",
            key=key,
        )
        return selected_row(event, source)
    except TypeError:
        st.dataframe(view, use_container_width=True, height=resolved_height, hide_index=hide_index)
        return None


def quote_identifier(value: str) -> str | None:
    value = str(value).upper()
    if not SQL_IDENTIFIER_RE.fullmatch(value):
        return None
    return f'"{value}"'


def first_existing(columns: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


@st.cache_data(ttl=3600)
def table_columns(table_name: str) -> set[str]:
    try:
        cols = run_query(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = CURRENT_SCHEMA()
              AND TABLE_NAME = %s
            """,
            (str(table_name).upper(),),
        )
    except Exception:
        return set()
    if cols.empty or "COLUMN_NAME" not in cols.columns:
        return set()
    return {str(col).upper() for col in cols["COLUMN_NAME"].dropna()}


def token_id_column_for(table_name: str) -> str | None:
    return first_existing(table_columns(table_name), ["TOKEN_ID", "ITEM_ID", "ID"])


@st.cache_data(ttl=3600)
def discover_candle_source() -> dict[str, object]:
    try:
        cols = run_query(
            """
            SELECT TABLE_NAME, COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = CURRENT_SCHEMA()
            """
        )
    except Exception:
        return {}

    if cols.empty:
        return {}

    candidates = []
    grouped = cols.groupby("TABLE_NAME")["COLUMN_NAME"].apply(lambda values: {str(v).upper() for v in values})
    for table_name, columns in grouped.items():
        table = str(table_name).upper()
        if quote_identifier(table) is None:
            continue

        time_col = first_existing(
            columns,
            ["TS", "TIME", "TIMESTAMP", "DATETIME", "DATE", "DAY", "BLOCK_TIMESTAMP", "RECORDED_AT", "CREATED_AT"],
        )
        key_cols = {
            "TOKEN_ID": first_existing(columns, ["TOKEN_ID", "ASSET_ID", "COIN_ID"]),
            "SYMBOL": first_existing(columns, ["SYMBOL", "TOKEN_SYMBOL", "ASSET_SYMBOL"]),
            "ADDRESS": first_existing(columns, ["ADDRESS", "TOKEN_ADDRESS", "CONTRACT_ADDRESS"]),
        }
        key_cols = {name: col for name, col in key_cols.items() if col}
        if not time_col or not key_cols:
            continue

        open_col = first_existing(columns, ["OPEN", "OPEN_PRICE", "PRICE_OPEN", "O"])
        high_col = first_existing(columns, ["HIGH", "HIGH_PRICE", "PRICE_HIGH", "H"])
        low_col = first_existing(columns, ["LOW", "LOW_PRICE", "PRICE_LOW", "L"])
        close_col = first_existing(columns, ["CLOSE", "CLOSE_PRICE", "PRICE_CLOSE", "C"])
        price_col = first_existing(columns, ["PRICE", "USD_PRICE", "PRICE_USD", "CLOSE", "CLOSE_PRICE"])
        volume_col = first_existing(columns, ["VOLUME", "VOLUME_USD", "VOL", "TX_VOLUME", "AMOUNT", "QUANTITY"])

        table_score = 0
        for keyword in ["OHLC", "CANDLE", "PRICE", "MARKET"]:
            if keyword in table:
                table_score += 1

        if open_col and high_col and low_col and close_col:
            candidates.append(
                {
                    "priority": 10 + table_score,
                    "mode": "ohlc",
                    "table": table,
                    "time": time_col,
                    "open": open_col,
                    "high": high_col,
                    "low": low_col,
                    "close": close_col,
                    "volume": volume_col,
                    "keys": key_cols,
                }
            )
        elif price_col:
            candidates.append(
                {
                    "priority": 5 + table_score,
                    "mode": "price",
                    "table": table,
                    "time": time_col,
                    "price": price_col,
                    "volume": volume_col,
                    "keys": key_cols,
                }
            )

    if not candidates:
        return {}
    return sorted(candidates, key=lambda item: item["priority"], reverse=True)[0]


def normalize_candles(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()

    candles = raw.copy()
    candles["TS"] = pd.to_datetime(candles["TS"], errors="coerce")
    for col in ["OPEN", "HIGH", "LOW", "CLOSE"]:
        candles[col] = pd.to_numeric(candles[col], errors="coerce")
    if "VOLUME" in candles.columns:
        candles["VOLUME"] = pd.to_numeric(candles["VOLUME"], errors="coerce").fillna(0)
    else:
        candles["VOLUME"] = 0
    candles = candles.dropna(subset=["TS", "OPEN", "HIGH", "LOW", "CLOSE"])
    return candles.sort_values("TS")


def price_series_to_candles(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()

    prices = raw.copy()
    prices["TS"] = pd.to_datetime(prices["TS"], errors="coerce")
    prices["PRICE"] = pd.to_numeric(prices["PRICE"], errors="coerce")
    if "VOLUME" in prices.columns:
        prices["VOLUME"] = pd.to_numeric(prices["VOLUME"], errors="coerce").fillna(0)
    else:
        prices["VOLUME"] = 0
    prices = prices.dropna(subset=["TS", "PRICE"]).sort_values("TS")
    if prices.empty:
        return pd.DataFrame()

    prices["DAY"] = prices["TS"].dt.floor("D")
    candles = prices.groupby("DAY").agg(
        OPEN=("PRICE", "first"),
        HIGH=("PRICE", "max"),
        LOW=("PRICE", "min"),
        CLOSE=("PRICE", "last"),
        VOLUME=("VOLUME", "sum"),
    ).reset_index().rename(columns={"DAY": "TS"})
    return normalize_candles(candles)


@st.cache_data(ttl=3600)
def query_market_candles(token_id: str, symbol: str, address: str) -> tuple[pd.DataFrame, str]:
    source = discover_candle_source()
    if not source:
        return pd.DataFrame(), ""

    table = quote_identifier(source["table"])
    time_col = quote_identifier(source["time"])
    keys = source.get("keys", {})
    if not table or not time_col or not isinstance(keys, dict):
        return pd.DataFrame(), ""

    condition = None
    param = None
    if token_id and keys.get("TOKEN_ID"):
        condition = f"CAST({quote_identifier(keys['TOKEN_ID'])} AS VARCHAR) = %s"
        param = token_id
    elif symbol and keys.get("SYMBOL"):
        condition = f"UPPER(CAST({quote_identifier(keys['SYMBOL'])} AS VARCHAR)) = %s"
        param = symbol.upper()
    elif address and keys.get("ADDRESS"):
        condition = f"LOWER(CAST({quote_identifier(keys['ADDRESS'])} AS VARCHAR)) = %s"
        param = address.lower()

    if not condition or param is None:
        return pd.DataFrame(), ""

    try:
        if source["mode"] == "ohlc":
            open_col = quote_identifier(source["open"])
            high_col = quote_identifier(source["high"])
            low_col = quote_identifier(source["low"])
            close_col = quote_identifier(source["close"])
            volume_col = quote_identifier(source["volume"]) if source.get("volume") else None
            if not all([open_col, high_col, low_col, close_col]):
                return pd.DataFrame(), ""
            volume_expr = f"{volume_col} AS VOLUME" if volume_col else "0 AS VOLUME"
            raw = run_query(
                f"""
                SELECT
                    {time_col} AS TS,
                    {open_col} AS OPEN,
                    {high_col} AS HIGH,
                    {low_col} AS LOW,
                    {close_col} AS CLOSE,
                    {volume_expr}
                FROM {table}
                WHERE {condition}
                ORDER BY {time_col} DESC
                LIMIT {MAX_CANDLE_POINTS}
                """,
                (param,),
            )
            return normalize_candles(raw), str(source["table"])

        price_col = quote_identifier(source["price"])
        if not price_col:
            return pd.DataFrame(), ""
        volume_col = quote_identifier(source["volume"]) if source.get("volume") else None
        volume_expr = f", {volume_col} AS VOLUME" if volume_col else ", 0 AS VOLUME"
        raw = run_query(
            f"""
            SELECT {time_col} AS TS, {price_col} AS PRICE {volume_expr}
            FROM {table}
            WHERE {condition}
            ORDER BY {time_col} DESC
            LIMIT {MAX_CANDLE_POINTS}
            """,
            (param,),
        )
        return price_series_to_candles(raw), str(source["table"])
    except Exception:
        return pd.DataFrame(), ""


def holder_activity_candles(holders: pd.DataFrame) -> pd.DataFrame:
    if holders.empty or "LAST_ACTIVE" not in holders.columns or "BALANCE" not in holders.columns:
        return pd.DataFrame()

    data = holders.copy()
    data["TS"] = pd.to_datetime(data["LAST_ACTIVE"], errors="coerce")
    data["BALANCE"] = pd.to_numeric(data["BALANCE"], errors="coerce")
    data["TX_COUNT"] = pd.to_numeric(data.get("TX_COUNT", 0), errors="coerce").fillna(0)
    data = data.dropna(subset=["TS", "BALANCE"]).sort_values("TS")
    data = data[data["BALANCE"] > 0]
    if data.empty:
        return pd.DataFrame()

    data["PRICE_PROXY"] = data["BALANCE"].apply(lambda value: math.log10(float(value) + 1.0))
    data["DAY"] = data["TS"].dt.floor("D")
    candles = data.groupby("DAY").agg(
        OPEN=("PRICE_PROXY", "first"),
        HIGH=("PRICE_PROXY", "max"),
        LOW=("PRICE_PROXY", "min"),
        CLOSE=("PRICE_PROXY", "last"),
        VOLUME=("TX_COUNT", "sum"),
    ).reset_index().rename(columns={"DAY": "TS"})
    return normalize_candles(candles)


def local_pagerank_for_user(user_id: str) -> pd.DataFrame:
    user_id = id_to_text(user_id)
    mask = df_pr["ID"].apply(id_to_text) == user_id
    return df_pr[mask].copy()


def pagerank_for_user(user_id: str) -> pd.DataFrame:
    user_id = id_to_text(user_id)
    result = local_pagerank_for_user(user_id)
    if result.empty:
        result = query_wallet_pagerank(user_id)
    return result


def normalize_holdings(holdings: pd.DataFrame) -> pd.DataFrame:
    holdings = holdings.copy()
    if "USER_ID" in holdings.columns:
        holdings["USER_ID"] = holdings["USER_ID"].apply(id_to_text)
    if "TOKEN_ID" in holdings.columns:
        holdings["TOKEN_ID"] = pd.to_numeric(holdings["TOKEN_ID"], errors="coerce").astype("Int64")
    if "BALANCE" in holdings.columns:
        holdings["BALANCE"] = pd.to_numeric(holdings["BALANCE"], errors="coerce")
    if "TX_COUNT" in holdings.columns:
        holdings["TX_COUNT"] = pd.to_numeric(holdings["TX_COUNT"], errors="coerce").fillna(0)
    return holdings


def wallet_holdings_for_user(user_id: str) -> pd.DataFrame:
    user_id = id_to_text(user_id)
    mask = df_po_rich["USER_ID"].apply(id_to_text) == user_id
    holdings = df_po_rich[mask].copy()
    if holdings.empty:
        holdings = query_wallet_holdings(user_id)
    return normalize_holdings(holdings)


def wallet_candidates(query: str) -> pd.DataFrame:
    q = query.strip()
    if not q:
        candidates = df_pr.sort_values("PAGERANK", ascending=False).copy()
    else:
        ids = df_pr["ID"].apply(id_to_text)
        mask = ids.str.contains(q, case=False, regex=False, na=False)
        candidates = df_pr[mask].sort_values("PAGERANK", ascending=False).copy()
        if candidates.empty:
            candidates = query_wallet_candidates(q)

    if candidates.empty:
        return candidates

    candidates = candidates[["ID", "PAGERANK"]].copy()
    candidates["ID"] = candidates["ID"].apply(id_to_text)
    candidates["PAGERANK"] = pd.to_numeric(candidates["PAGERANK"], errors="coerce")
    candidates = candidates.sort_values("PAGERANK", ascending=False).reset_index(drop=True)
    candidates.insert(0, "RANK", range(1, len(candidates) + 1))
    return candidates


def local_token_results(query: str) -> pd.DataFrame:
    q = query.strip()
    if not q:
        return df_tk.copy()

    mask = (
        as_text(df_tk["SYMBOL"]).str.contains(q, case=False, regex=False, na=False)
        | as_text(df_tk["NAME"]).str.contains(q, case=False, regex=False, na=False)
        | as_text(df_tk["ADDRESS"]).str.contains(q, case=False, regex=False, na=False)
        | as_text(df_tk["TOKEN_ID"]).str.contains(q, case=False, regex=False, na=False)
    )
    return df_tk[mask].copy()


def token_results(query: str) -> pd.DataFrame:
    q = query.strip()
    if not q:
        return pd.DataFrame()

    project_results = query_project_tokens(q)
    item_results = query_item_factor_tokens(q)
    local_results = local_token_results(q)
    snowflake_results = query_tokens(q) if local_results.empty else pd.DataFrame()
    results = pd.concat([project_results, item_results, local_results, snowflake_results], ignore_index=True)

    if "TOKEN_ID" in results.columns:
        results["TOKEN_ID"] = pd.to_numeric(results["TOKEN_ID"], errors="coerce").astype("Int64")
        results["TOKEN_ID_TEXT"] = results["TOKEN_ID"].apply(id_to_text)
    else:
        results["TOKEN_ID_TEXT"] = ""

    if "SYMBOL" not in results.columns:
        results["SYMBOL"] = ""
    if "NAME" not in results.columns:
        results["NAME"] = ""
    if "ADDRESS" not in results.columns:
        results["ADDRESS"] = ""

    q_upper = q.upper()
    q_address = normalize_token_address(q)
    results["MATCH_PRIORITY"] = 3
    results.loc[results["TOKEN_ID_TEXT"] == q, "MATCH_PRIORITY"] = 0
    if q_address:
        results.loc[as_text(results["ADDRESS"]).str.lower() == q_address, "MATCH_PRIORITY"] = 0
    results.loc[as_text(results["SYMBOL"]).str.upper() == q_upper, "MATCH_PRIORITY"] = 1
    results.loc[as_text(results["NAME"]).str.upper() == q_upper, "MATCH_PRIORITY"] = 1
    results.loc[
        results["MATCH_PRIORITY"].eq(3)
        & (
            as_text(results["SYMBOL"]).str.contains(q, case=False, regex=False, na=False)
            | as_text(results["NAME"]).str.contains(q, case=False, regex=False, na=False)
        ),
        "MATCH_PRIORITY",
    ] = 2

    return (
        results.sort_values(["MATCH_PRIORITY", "SYMBOL", "TOKEN_ID_TEXT"])
        .drop_duplicates("TOKEN_ID_TEXT")
        .reset_index(drop=True)
    )


def token_by_identifier(token_id=None, symbol=None) -> pd.DataFrame:
    token = pd.DataFrame()

    if token_id is not None and pd.notna(token_id):
        token_id_text = id_to_text(token_id)
        token = query_project_token_by_id(token_id_text)
        item_token = query_item_factor_by_id(token_id_text)
        token_ids = pd.to_numeric(df_tk["TOKEN_ID"], errors="coerce").astype("Int64")
        mask = as_text(token_ids) == token_id_text
        local_token = df_tk[mask].copy()
        if token.empty:
            token = item_token
        elif not item_token.empty:
            token = pd.concat([token, item_token], ignore_index=True)
        if token.empty:
            token = local_token
        elif not local_token.empty:
            token = pd.concat([token, local_token], ignore_index=True)
        if token.empty:
            token = query_token_by_id(token_id_text)

    if token.empty:
        address = normalize_token_address(symbol)
        if address:
            token = query_project_token_by_address(address)

    if token.empty and symbol:
        symbol_text = str(symbol).strip()
        mask = as_text(df_tk["SYMBOL"]).str.upper() == symbol_text.upper()
        token = df_tk[mask].copy()
        if token.empty:
            token = query_token_by_symbol(symbol_text)

    if "TOKEN_ID" in token.columns:
        token["TOKEN_ID"] = pd.to_numeric(token["TOKEN_ID"], errors="coerce").astype("Int64")
        token["TOKEN_ID_TEXT"] = token["TOKEN_ID"].apply(id_to_text)
        token = token.drop_duplicates("TOKEN_ID_TEXT")
    return token.reset_index(drop=True)


def token_holders_for_token(token_id) -> pd.DataFrame:
    token_id_text = id_to_text(token_id)
    local_token_id = pd.to_numeric(df_po_rich["TOKEN_ID"], errors="coerce").astype("Int64")
    holders = df_po_rich[as_text(local_token_id) == token_id_text].copy()

    if holders.empty:
        holders = query_token_holders(token_id_text)
    return normalize_holdings(holders)


@st.cache_data(ttl=3600)
def query_lightgcn_recommendations(user_id: str) -> pd.DataFrame:
    columns = table_columns(TOKEN_RECOMMENDATIONS_TABLE)
    rec_table = quote_identifier(TOKEN_RECOMMENDATIONS_TABLE)
    if not columns or not rec_table:
        return pd.DataFrame()

    user_col = first_existing(columns, ["USER_ID", "WALLET_ID", "ID"])
    token_col = first_existing(columns, ["TOKEN_ID", "ITEM_ID"])
    score_col = first_existing(
        columns,
        ["SCORE", "RECOMMENDATION_SCORE", "PRED_SCORE", "PREDICTED_SCORE", "PREDICTION", "RATING", "CONFIDENCE"],
    )
    rank_col = first_existing(columns, ["RANK", "RN", "RECOMMENDATION_RANK"])
    if not token_col:
        return pd.DataFrame()

    token_col_q = quote_identifier(token_col)
    score_expr = f"r.{quote_identifier(score_col)}" if score_col else "NULL"
    rank_expr = f"r.{quote_identifier(rank_col)}" if rank_col else "NULL"
    where_clause = ""
    params: tuple[object, ...] = ()
    if user_col:
        where_clause = f"WHERE CAST(r.{quote_identifier(user_col)} AS VARCHAR) = %s"
        params = (id_to_text(user_id),)

    order_clause = "ORDER BY "
    if score_col:
        order_clause += f"r.{quote_identifier(score_col)} DESC"
    elif rank_col:
        order_clause += f"r.{quote_identifier(rank_col)} ASC"
    else:
        order_clause += f"r.{token_col_q}"

    return run_query(
        f"""
        SELECT
            r.{token_col_q} AS TOKEN_ID,
            {score_expr} AS SCORE,
            {rank_expr} AS RANK,
            t.SYMBOL,
            t.NAME,
            t.ADDRESS
        FROM {rec_table} r
        LEFT JOIN TOKENS_INDEXED t
            ON CAST(r.{token_col_q} AS VARCHAR) = CAST(t.TOKEN_ID AS VARCHAR)
        {where_clause}
        {order_clause}
        LIMIT 100
        """,
        params,
    )


def fpgrowth_token_recommendations(holdings: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty or df_fp.empty:
        return pd.DataFrame()

    held_tokens = {
        str(token).strip().upper()
        for token in holdings["SYMBOL"].dropna().tolist()
        if str(token).strip()
    }
    if not held_tokens:
        return pd.DataFrame()

    rules = df_fp.copy()
    rules["ANTECEDENT_TOKENS"] = rules["ANTECEDENT"].apply(parse_tokens)
    rules["CONSEQUENT_TOKEN"] = rules["CONSEQUENT"].astype(str).str.strip()

    def full_match(tokens):
        normalized = {token.upper() for token in tokens}
        return bool(normalized) and normalized.issubset(held_tokens)

    def partial_match(tokens):
        normalized = {token.upper() for token in tokens}
        return bool(normalized & held_tokens)

    matched = rules[rules["ANTECEDENT_TOKENS"].apply(full_match)].copy()
    if matched.empty:
        matched = rules[rules["ANTECEDENT_TOKENS"].apply(partial_match)].copy()
    if matched.empty:
        return matched

    matched = matched[~matched["CONSEQUENT_TOKEN"].str.upper().isin(held_tokens)]
    for col in ["CONFIDENCE", "LIFT", "SUPPORT"]:
        matched[col] = pd.to_numeric(matched[col], errors="coerce").fillna(0)

    max_lift = matched["LIFT"].max()
    lift_norm = matched["LIFT"] / max_lift if max_lift > 0 else 0
    matched["SCORE"] = matched["CONFIDENCE"] * 0.7 + lift_norm * 0.2 + matched["SUPPORT"] * 0.1
    matched = matched.sort_values(["SCORE", "CONFIDENCE", "LIFT", "SUPPORT"], ascending=False)
    return matched.drop_duplicates("CONSEQUENT_TOKEN").reset_index(drop=True)


def token_recommendations(user_id: str, holdings: pd.DataFrame) -> pd.DataFrame:
    recommendations = query_lightgcn_recommendations(id_to_text(user_id))
    if not recommendations.empty:
        recommendations = recommendations.copy()
        recommendations["TOKEN_ID"] = pd.to_numeric(recommendations["TOKEN_ID"], errors="coerce").astype("Int64")
        recommendations["TOKEN_ID_TEXT"] = recommendations["TOKEN_ID"].apply(id_to_text)
        recommendations["SCORE"] = pd.to_numeric(recommendations["SCORE"], errors="coerce")
        recommendations["RANK"] = pd.to_numeric(recommendations["RANK"], errors="coerce")

        held_ids = {id_to_text(token_id) for token_id in holdings.get("TOKEN_ID", pd.Series(dtype=object)).dropna()}
        recommendations = recommendations[~recommendations["TOKEN_ID_TEXT"].isin(held_ids)]
        recommendations = recommendations.sort_values(
            ["SCORE", "RANK"],
            ascending=[False, True],
            na_position="last",
        )
        return recommendations.drop_duplicates("TOKEN_ID_TEXT").head(5).reset_index(drop=True)

    fallback = fpgrowth_token_recommendations(holdings)
    if fallback.empty:
        return fallback
    fallback["TOKEN_ID"] = pd.NA
    fallback["SYMBOL"] = fallback["CONSEQUENT_TOKEN"]
    fallback["NAME"] = ""
    fallback["ADDRESS"] = ""
    fallback["RANK"] = range(1, len(fallback) + 1)
    return fallback.head(5)


def matching_key_frame(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["USER_ID_TEXT"] = result["USER_ID"].apply(id_to_text)
    token_id_key = pd.to_numeric(result["TOKEN_ID"], errors="coerce").astype("Int64").astype("string")
    symbol_key = as_text(result["SYMBOL"]).str.upper()
    result["MATCH_KEY"] = symbol_key.mask(symbol_key.eq(""), token_id_key)
    return result.dropna(subset=["MATCH_KEY"])


def similar_reputable_wallets(user_id: str, holdings: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty or df_po_rich.empty:
        return pd.DataFrame()

    target_id = id_to_text(user_id)
    target = matching_key_frame(holdings)
    target_keys = set(target["MATCH_KEY"].dropna())
    if not target_keys:
        return pd.DataFrame()

    all_portfolios = matching_key_frame(df_po_rich)
    all_portfolios = all_portfolios[all_portfolios["USER_ID_TEXT"] != target_id]
    intersecting_users = all_portfolios[all_portfolios["MATCH_KEY"].isin(target_keys)]["USER_ID_TEXT"].unique()
    if len(intersecting_users) == 0:
        return pd.DataFrame()

    candidates = all_portfolios[all_portfolios["USER_ID_TEXT"].isin(intersecting_users)]
    grouped = candidates.groupby("USER_ID_TEXT").agg(
        TOKEN_SET=("MATCH_KEY", lambda values: set(values)),
        TX_COUNT=("TX_COUNT", "sum"),
    ).reset_index()

    rows = []
    for _, row in grouped.iterrows():
        token_set = row["TOKEN_SET"]
        common = target_keys & token_set
        union = target_keys | token_set
        if not common or not union:
            continue
        rows.append(
            {
                "USER_ID": row["USER_ID_TEXT"],
                "SIMILARITY": len(common) / len(union),
                "COMMON_TOKENS": len(common),
                "TX_COUNT": row["TX_COUNT"],
                "MATCHED_TOKENS": ", ".join(sorted(common)[:10]),
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    pr = df_pr[["ID", "PAGERANK"]].copy()
    pr["USER_ID"] = pr["ID"].apply(id_to_text)
    result = result.merge(pr[["USER_ID", "PAGERANK"]], on="USER_ID", how="left")
    result["PAGERANK"] = pd.to_numeric(result["PAGERANK"], errors="coerce").fillna(0)
    max_pr = result["PAGERANK"].max()
    result["PAGERANK_NORM"] = result["PAGERANK"] / max_pr if max_pr > 0 else 0
    result["UY_TIN_SCORE"] = result["SIMILARITY"] * 0.65 + result["PAGERANK_NORM"] * 0.35
    return result.sort_values(["UY_TIN_SCORE", "PAGERANK", "SIMILARITY"], ascending=False).reset_index(drop=True)


@st.cache_data(ttl=3600)
def query_top5_mentors(user_id: str) -> pd.DataFrame:
    return run_query(
        f"""
        SELECT
            USER_ID_SIMILARITY AS USER_ID,
            RANK,
            PAGERANK
        FROM {MENTORS_TABLE}
        WHERE CAST(USER_ID AS VARCHAR) = %s
        ORDER BY RANK ASC, PAGERANK DESC
        LIMIT 5
        """,
        (id_to_text(user_id),),
    )


def top5_mentor_wallets(user_id: str) -> pd.DataFrame:
    mentors = query_top5_mentors(user_id)
    if mentors.empty:
        return mentors
    mentors = mentors.copy()
    mentors["USER_ID"] = mentors["USER_ID"].apply(id_to_text)
    mentors["RANK"] = pd.to_numeric(mentors["RANK"], errors="coerce").astype("Int64")
    mentors["PAGERANK"] = pd.to_numeric(mentors["PAGERANK"], errors="coerce")
    return mentors.sort_values(["RANK", "PAGERANK"], ascending=[True, False]).reset_index(drop=True)


def render_candlestick(token_row: pd.Series, holders: pd.DataFrame, key_prefix: str):
    token_id = id_to_text(token_row.get("TOKEN_ID"))
    symbol = str(token_row.get("SYMBOL", "") or "")
    address = str(token_row.get("ADDRESS", "") or "")
    candles, source_name = query_market_candles(token_id, symbol, address)
    source_label = "Giá"
    is_proxy = False

    if candles.empty:
        candles = holder_activity_candles(holders)
        source_label = "Chỉ số holder"
        is_proxy = True

    if candles.empty:
        st.info("Chưa có dữ liệu nến cho token này.")
        return

    candles = candles.tail(MAX_CANDLE_POINTS).copy()
    candles["MA7"] = candles["CLOSE"].rolling(7, min_periods=1).mean()
    candles["MA25"] = candles["CLOSE"].rolling(25, min_periods=1).mean()
    candles["UP"] = candles["CLOSE"] >= candles["OPEN"]
    volume_colors = candles["UP"].map({True: "rgba(34,197,94,0.55)", False: "rgba(239,68,68,0.55)"})

    title = f"{symbol or token_id} - Candlestick"
    st.subheader("Đồ thị giá")
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.74, 0.26],
    )
    fig.add_trace(
        go.Candlestick(
            x=candles["TS"],
            open=candles["OPEN"],
            high=candles["HIGH"],
            low=candles["LOW"],
            close=candles["CLOSE"],
            name="OHLC",
            increasing_line_color="#16a34a",
            increasing_fillcolor="#16a34a",
            decreasing_line_color="#dc2626",
            decreasing_fillcolor="#dc2626",
            whiskerwidth=0.35,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=candles["TS"],
            y=candles["MA7"],
            mode="lines",
            line=dict(color="#f59e0b", width=1.4),
            name="MA 7",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=candles["TS"],
            y=candles["MA25"],
            mode="lines",
            line=dict(color="#38bdf8", width=1.4),
            name="MA 25",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=candles["TS"],
            y=candles["VOLUME"],
            marker_color=volume_colors,
            name="Volume",
        ),
        row=2,
        col=1,
    )

    latest = candles.iloc[-1]
    fig.add_hline(
        y=float(latest["CLOSE"]),
        line_width=1,
        line_dash="dot",
        line_color="#94a3b8",
        row=1,
        col=1,
    )
    fig.update_layout(
        title=dict(text=title, x=0.01, font=dict(size=18)),
        height=620,
        template="plotly_dark",
        margin=dict(t=56, b=28, l=10, r=28),
        hovermode="x unified",
        dragmode="pan",
        showlegend=True,
        legend=dict(orientation="h", y=1.04, x=0),
        xaxis=dict(
            rangeselector=dict(
                buttons=[
                    dict(count=7, label="7D", step="day", stepmode="backward"),
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(step="all", label="ALL"),
                ],
                bgcolor="rgba(30,41,59,0.9)",
                activecolor="#334155",
            ),
            rangeslider=dict(visible=True, thickness=0.06),
            type="date",
        ),
        xaxis2=dict(rangeslider=dict(visible=False)),
        yaxis=dict(title=source_label, side="right", fixedrange=False),
        yaxis2=dict(title="Volume", side="right", fixedrange=False),
        modebar_add=["drawline", "drawrect", "eraseshape"],
        modebar_remove=["lasso2d", "select2d"],
    )
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", showline=True)
    fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor", showline=True)

    if is_proxy:
        st.caption("Chưa có bảng giá/OHLC thật cho token này; chart đang dùng chỉ số holder đã log-scale để tránh outlier.")
    else:
        st.caption("Chart dùng nến OHLC kiểu chứng khoán, kèm MA7, MA25, volume và range slider.")
    st.plotly_chart(fig, use_container_width=True)
    if source_name:
        st.caption(f"Nguồn nến: {source_name}")


def render_token_detail(token_row: pd.Series, key_prefix: str, allow_holder_click: bool = True):
    token_id = token_row.get("TOKEN_ID")
    symbol = token_row.get("SYMBOL", "Unknown")

    st.subheader(f"Thông tin token: {symbol}")
    ci0, ci1, ci2, ci3, ci4 = st.columns(5)
    ci0.metric("Token ID", id_to_text(token_id))
    ci1.metric("Symbol", str(symbol))
    ci2.metric("Tên", str(token_row.get("NAME", "N/A")))
    ci3.metric("Decimals", str(token_row.get("DECIMALS", "N/A")))
    ci4.metric("Total Supply", fmt_number(token_row.get("TOTAL_SUPPLY")))

    address = token_row.get("ADDRESS")
    if pd.notna(address):
        st.code(f"Contract: {address}", language=None)

    render_address_price_chart(symbol, address, f"{key_prefix}_{id_to_text(token_id)}")
    holders = token_holders_for_token(token_id)

    if holders.empty:
        st.info("Token này chưa có trong USER_PORTFOLIOS.")
        return

    p1, p2, p3 = st.columns(3)
    p1.metric("Số ví nắm giữ", f"{len(holders):,}")
    p2.metric("Tổng TX Count", f"{safe_int(holders['TX_COUNT'].sum()):,}")
    p3.metric("Balance trung bình", f"{safe_float(holders['BALANCE'].mean()):.4g}")

    col_hist, col_top = st.columns(2)
    with col_hist:
        st.subheader("Phân bổ holder theo lũy thừa số dư")
        hist_df = power_bucket_counts(holders["BALANCE"], value_name="Số ví")
        fig = px.bar(
            hist_df,
            x="Bucket",
            y="Số ví",
            template="plotly_dark",
            color_discrete_sequence=["#7c3aed"],
        )
        fig.update_layout(
            height=320,
            margin=dict(t=10, b=10),
            xaxis_title="Bucket số dư",
            yaxis_title="Số ví",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_top:
        st.subheader("Top ví nắm nhiều nhất")
        top_holders = (
            holders.sort_values("BALANCE", ascending=False)
            .head(20)[["USER_ID", "BALANCE", "TX_COUNT", "LAST_ACTIVE"]]
            .reset_index(drop=True)
        )
        selected_holder = selectable_dataframe(
            top_holders,
            key=f"{key_prefix}_holder_select",
            height=None,
            hide_index=False,
        )

    if allow_holder_click and selected_holder is not None:
        st.divider()
        render_wallet_detail(id_to_text(selected_holder["USER_ID"]), f"{key_prefix}_selected_holder", compact=True)


def render_recommendation_tables(user_id: str, holdings: pd.DataFrame, key_prefix: str):
    col_tokens, col_wallets = st.columns(2)

    with col_tokens:
        st.subheader("Top token đáng mua nhất")
        recommendations = token_recommendations(user_id, holdings)
        selected_token = None
        if recommendations.empty:
            st.info("Chưa có gợi ý token phù hợp với ví này.")
        else:
            for col in ["TOKEN_ID", "SYMBOL", "NAME", "SCORE", "RANK"]:
                if col not in recommendations.columns:
                    recommendations[col] = pd.NA
            token_view = recommendations[["RANK", "TOKEN_ID", "SYMBOL", "NAME", "SCORE"]].head(5).copy()
            token_view["RANK"] = token_view["RANK"].fillna(pd.Series(range(1, len(token_view) + 1)))
            token_view = token_view.rename(columns={"SYMBOL": "TOKEN", "NAME": "TÊN", "SCORE": "ĐIỂM"})
            selected_token = selectable_dataframe(
                recommendations.head(5),
                key=f"{key_prefix}_recommendation_select",
                display_df=token_view,
                height=top5_table_height(len(token_view)),
            )

    with col_wallets:
        st.subheader("Top ví uy tín có hành vi giống")
        similar_wallets = top5_mentor_wallets(user_id)
        selected_wallet = None
        if similar_wallets.empty:
            st.info("Chưa có dữ liệu mentor cho ví này trong RECOMMENDATION_TOP5_MENTORS.")
        else:
            wallet_view = similar_wallets[["RANK", "USER_ID", "PAGERANK"]].head(5).copy()
            wallet_view = wallet_view.rename(
                columns={
                    "USER_ID": "VÍ TƯƠNG TỰ",
                    "PAGERANK": "PAGERANK",
                }
            )
            selected_wallet = selectable_dataframe(
                similar_wallets.head(5),
                key=f"{key_prefix}_similar_wallet_select",
                display_df=wallet_view,
                height=top5_table_height(len(wallet_view)),
            )

    if selected_token is not None:
        token = token_by_identifier(
            token_id=selected_token.get("TOKEN_ID"),
            symbol=selected_token.get("SYMBOL"),
        )
        if not token.empty:
            st.divider()
            render_token_detail(token.iloc[0], f"{key_prefix}_recommended_token", allow_holder_click=False)

    if selected_wallet is not None:
        st.divider()
        render_wallet_detail(id_to_text(selected_wallet["USER_ID"]), f"{key_prefix}_similar_wallet", compact=True)


def wallet_holdings_view(holdings: pd.DataFrame) -> pd.DataFrame:
    cols = ["TOKEN_ID", "SYMBOL", "NAME", "BALANCE", "TX_COUNT", "LAST_ACTIVE", "ADDRESS"]
    cols = [col for col in cols if col in holdings.columns]
    return holdings[cols].rename(
        columns={
            "TOKEN_ID": "TOKEN_ID",
            "SYMBOL": "TOKEN",
            "NAME": "TÊN",
            "BALANCE": "SỐ DƯ HIỆN TẠI",
            "TX_COUNT": "SỐ GIAO DỊCH",
            "LAST_ACTIVE": "LẦN ACTIVE CUỐI",
            "ADDRESS": "CONTRACT",
        }
    )


def render_wallet_detail(
    user_id: str,
    key_prefix: str,
    compact: bool = False,
    include_recommendations: bool = False,
):
    user_id = id_to_text(user_id)
    pagerank = pagerank_for_user(user_id)
    holdings = wallet_holdings_for_user(user_id)

    st.subheader(f"Thông tin ví: {user_id}")

    score = pagerank.iloc[0]["PAGERANK"] if not pagerank.empty else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PageRank", fmt_score(score))
    c2.metric("Số loại token", f"{len(holdings):,}")
    c3.metric("Tổng giao dịch", f"{safe_int(holdings['TX_COUNT'].sum()) if not holdings.empty else 0:,}")
    if holdings.empty:
        c4.metric("Lần active gần nhất", "N/A")
    else:
        last = pd.to_datetime(holdings["LAST_ACTIVE"], errors="coerce").max()
        c4.metric("Lần active gần nhất", str(last)[:10] if pd.notna(last) else "N/A")

    if holdings.empty:
        st.warning("Không tìm thấy portfolio của ví này trong USER_PORTFOLIOS.")
        return

    display = holdings.copy()
    token_filter = st.text_input("Lọc token trong ví", "", key=f"{key_prefix}_token_filter")
    if token_filter:
        display = display[
            as_text(display["SYMBOL"]).str.contains(token_filter, case=False, regex=False, na=False)
            | as_text(display["NAME"]).str.contains(token_filter, case=False, regex=False, na=False)
            | as_text(display["ADDRESS"]).str.contains(token_filter, case=False, regex=False, na=False)
        ]

    display = display.sort_values("BALANCE", ascending=False).reset_index(drop=True)
    if display.empty:
        st.info("Không có token khớp bộ lọc.")
        return

    if compact:
        selectable_dataframe(
            display.head(30),
            key=f"{key_prefix}_holdings_compact",
            display_df=wallet_holdings_view(display.head(30)),
            height=None,
        )
        return

    col_table, col_chart = st.columns([3, 2])
    selected_token = None
    with col_table:
        st.subheader("Token đang nắm giữ")
        selected_token = selectable_dataframe(
            display,
            key=f"{key_prefix}_holdings_select",
            display_df=wallet_holdings_view(display),
            height=None,
        )

    with col_chart:
        st.subheader("Phân bổ số dư theo token")
        fig = balance_bar_figure(holdings)
        if fig is None:
            st.info("Không có số dư dương để vẽ biểu đồ.")
        else:
            st.plotly_chart(fig, use_container_width=True)

    if selected_token is not None:
        token = token_by_identifier(
            token_id=selected_token.get("TOKEN_ID"),
            symbol=selected_token.get("SYMBOL"),
        )
        if not token.empty:
            st.divider()
            render_token_detail(token.iloc[0], f"{key_prefix}_selected_token", allow_holder_click=False)

    if include_recommendations:
        st.divider()
        render_recommendation_tables(user_id, holdings, key_prefix)


def render_dashboard():
    st.title("🪙 Crypto Analytics Dashboard")
    st.caption("Ethereum On-chain · PageRank · Portfolio · Token")

    st.divider()

    st.subheader("🏆 Top ví PageRank cao nhất")
    top_n = st.slider("Số ví PageRank hiển thị", 5, 50, 20, key="dashboard_pr_slider")
    top_pr = (
        df_pr.sort_values("PAGERANK", ascending=False)
        .head(top_n)[["ID", "PAGERANK"]]
        .reset_index(drop=True)
    )
    top_pr["ID"] = top_pr["ID"].apply(id_to_text)
    top_pr.index += 1
    max_pr = float(top_pr["PAGERANK"].max()) if not top_pr.empty else 0.0

    top_pr_table = top_pr.reset_index(names="RANK").copy()
    top_pr_table["TỶ LỆ SO VỚI TOP 1"] = (
        top_pr_table["PAGERANK"] / max_pr * 100 if max_pr > 0 else 0
    )
    top_pr_table = top_pr_table.rename(columns={"ID": "ID VÍ", "PAGERANK": "ĐIỂM PAGERANK"})
    st.dataframe(
        top_pr_table,
        use_container_width=True,
        height=420,
        hide_index=True,
        column_config={
            "RANK": st.column_config.NumberColumn("RANK", format="%d", width="small"),
            "ID VÍ": st.column_config.TextColumn("ID VÍ", width="medium"),
            "ĐIỂM PAGERANK": st.column_config.NumberColumn("ĐIỂM PAGERANK", format="%.3e"),
            "TỶ LỆ SO VỚI TOP 1": st.column_config.ProgressColumn(
                "TỶ LỆ SO VỚI TOP 1",
                min_value=0,
                max_value=100,
                format="%.1f%%",
            ),
        },
    )

    st.divider()

    st.subheader("💰 Top ví nhiều tiền nhất")
    st.caption("Tổng Balance = cộng tất cả token đang giữ của mỗi ví")
    top_m = st.slider("Số ví balance hiển thị", 5, 50, 20, key="dashboard_bal_slider")
    portfolio = df_po.copy()
    portfolio["BALANCE"] = pd.to_numeric(portfolio["BALANCE"], errors="coerce").fillna(0)
    portfolio["TX_COUNT"] = pd.to_numeric(portfolio["TX_COUNT"], errors="coerce").fillna(0)
    top_rich = (
        portfolio.groupby("USER_ID")
        .agg(
            Tong_Balance=("BALANCE", "sum"),
            So_loai_token=("TOKEN_ID", "count"),
            Tong_TX=("TX_COUNT", "sum"),
        )
        .reset_index()
        .sort_values("Tong_Balance", ascending=False)
        .head(top_m)
        .reset_index(drop=True)
    )
    top_rich.index += 1

    col_tl, col_tr = st.columns([2, 3])
    with col_tl:
        st.dataframe(
            top_rich.rename(
                columns={
                    "USER_ID": "User ID",
                    "Tong_Balance": "Tổng Balance",
                    "So_loai_token": "Số loại token",
                    "Tong_TX": "Tổng giao dịch",
                }
            ),
            use_container_width=True,
            height=420,
        )
    with col_tr:
        fig2 = px.bar(
            top_rich.head(20),
            x="Tong_Balance",
            y=top_rich.head(20)["USER_ID"].astype(str),
            orientation="h",
            template="plotly_dark",
            color="Tong_Balance",
            color_continuous_scale=["#1e2133", "#f59e0b", "#fcd34d"],
            labels={"y": "User ID", "Tong_Balance": "Tổng Balance"},
        )
        fig2.update_layout(
            height=420,
            margin=dict(t=10, b=10, l=10, r=10),
            yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False,
            paper_bgcolor="#0f1117",
            plot_bgcolor="#0f1117",
        )
        apply_log_axis(fig2, "x", top_rich["Tong_Balance"], "Tổng Balance (log10)")
        fig2.update_xaxes(gridcolor="#1e2133")
        fig2.update_yaxes(gridcolor="#1e2133")
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    st.subheader("🪙 Top token được giữ nhiều nhất")
    token_frame = df_po_rich.copy()
    token_frame["SYMBOL"] = token_frame["SYMBOL"].fillna(token_frame["TOKEN_ID"].apply(lambda value: f"Token {id_to_text(value)}"))
    token_frame["BALANCE"] = pd.to_numeric(token_frame["BALANCE"], errors="coerce").fillna(0)
    token_frame["TX_COUNT"] = pd.to_numeric(token_frame["TX_COUNT"], errors="coerce").fillna(0)

    col_opt1, col_opt2 = st.columns([2, 2])
    top_t = col_opt1.slider("Số token hiển thị", 5, 30, 15, key="dashboard_tk_slider")
    metric = col_opt2.radio(
        "Xếp hạng theo",
        ["Số ví nắm giữ", "Tổng Balance", "Tổng giao dịch"],
        horizontal=True,
        key="dashboard_token_metric",
    )
    metric_col = {
        "Số ví nắm giữ": ("USER_ID", "count"),
        "Tổng Balance": ("BALANCE", "sum"),
        "Tổng giao dịch": ("TX_COUNT", "sum"),
    }
    agg_col, agg_fn = metric_col[metric]
    top_tokens = (
        token_frame.groupby("SYMBOL")[agg_col]
        .agg(agg_fn)
        .reset_index()
        .rename(columns={agg_col: metric})
        .sort_values(metric, ascending=False)
        .head(top_t)
        .reset_index(drop=True)
    )
    top_tokens.index += 1

    col_bl, col_br = st.columns([3, 2])
    with col_bl:
        color_map = {
            "Số ví nắm giữ": ["#1e2133", "#06b6d4", "#67e8f9"],
            "Tổng Balance": ["#1e2133", "#f59e0b", "#fcd34d"],
            "Tổng giao dịch": ["#1e2133", "#26a69a", "#86efac"],
        }
        fig3 = px.bar(
            top_tokens,
            x="SYMBOL",
            y=metric,
            template="plotly_dark",
            color=metric,
            color_continuous_scale=color_map[metric],
            text=metric,
        )
        fig3.update_traces(texttemplate="%{text:.3s}", textposition="outside")
        fig3.update_layout(
            height=400,
            margin=dict(t=30, b=10, l=10, r=10),
            coloraxis_showscale=False,
            paper_bgcolor="#0f1117",
            plot_bgcolor="#0f1117",
        )
        fig3.update_xaxes(gridcolor="#1e2133")
        if metric == "Tổng Balance":
            apply_log_axis(fig3, "y", top_tokens[metric], "Tổng Balance (log10)")
        fig3.update_yaxes(gridcolor="#1e2133")
        st.plotly_chart(fig3, use_container_width=True)
    with col_br:
        fig4 = px.pie(
            top_tokens,
            names="SYMBOL",
            values=metric,
            hole=0.45,
            template="plotly_dark",
            title=f"Tỷ lệ {metric}",
        )
        fig4.update_layout(
            height=400,
            margin=dict(t=40, b=10, l=10, r=10),
            paper_bgcolor="#0f1117",
            showlegend=True,
            legend=dict(font=dict(size=10)),
        )
        st.plotly_chart(fig4, use_container_width=True)


def render_recommendation_page():
    st.title("💡 Gợi ý token")
    user_input = st.text_input("Nhập User ID", placeholder="vd: 26420870", key="recommendation_user_id")
    if not user_input.strip():
        st.info("Nhập một ví để xem top token đáng mua nhất và top ví uy tín có hành vi giống.")
        return

    user_id = id_to_text(user_input)
    holdings = wallet_holdings_for_user(user_id)
    if holdings.empty:
        st.warning(f"Không tìm thấy portfolio của ví `{user_id}`.")
        return

    st.subheader(f"Ví đang phân tích: {user_id}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Số token đang giữ", f"{len(holdings):,}")
    c2.metric("Tổng số dư token", fmt_number(holdings["BALANCE"].sum()))
    c3.metric("Tổng giao dịch", f"{safe_int(holdings['TX_COUNT'].sum()):,}")

    render_recommendation_tables(user_id, holdings, "recommendation_page")


def render_wallet_search():
    st.title("🔍 Tìm kiếm ví & gợi ý token")
    with st.form("wallet_lookup_form"):
        query_input = st.text_input("Nhập User ID", placeholder="vd: 26420870", key="wallet_search_input")
        submitted = st.form_submit_button("Tìm kiếm")
    if submitted:
        st.session_state["wallet_lookup_query"] = query_input

    query = st.session_state.get("wallet_lookup_query", "")

    if not query.strip():
        st.info("Nhập User ID rồi bấm Tìm kiếm để xem portfolio, top token đáng mua và ví uy tín có hành vi giống.")
        return

    candidates = wallet_candidates(query)
    selected_user_id = id_to_text(query)

    if not candidates.empty:
        candidates = candidates.head(50).reset_index(drop=True)
        st.subheader("Kết quả khớp")
        option_idx = st.selectbox(
            "Chọn ví",
            options=list(range(len(candidates))),
            format_func=lambda idx: (
                f"{candidates.iloc[idx]['ID']}  |  PageRank {fmt_score(candidates.iloc[idx]['PAGERANK'])}"
            ),
            key="wallet_result_select",
            label_visibility="collapsed",
        )
        selected_user_id = id_to_text(candidates.iloc[option_idx]["ID"])

    st.divider()
    render_wallet_detail(selected_user_id, "wallet_search", include_recommendations=True)


def render_token_search():
    st.title("📈 Tìm kiếm token")
    query = st.text_input("Tìm theo symbol, tên, contract hoặc Token ID", "", key="token_search_input")
    if not query.strip():
        st.info("Nhập symbol, tên, contract hoặc Token ID để tìm token.")
        return

    results = token_results(query)

    if results.empty:
        st.warning("Không tìm thấy token nào.")
        return

    query_upper = query.strip().upper()
    exact = results[as_text(results["SYMBOL"]).str.upper() == query_upper] if "SYMBOL" in results.columns else pd.DataFrame()
    if not exact.empty:
        results = pd.concat([exact, results.drop(exact.index)]).drop_duplicates("TOKEN_ID").reset_index(drop=True)

    selected = results.iloc[0]
    if len(results) > 1:
        st.caption(f"Tìm thấy {len(results):,} kết quả, tự lấy kết quả đầu tiên: {selected.get('SYMBOL', 'N/A')}.")

    token = token_by_identifier(token_id=selected.get("TOKEN_ID"), symbol=selected.get("SYMBOL"))
    if token.empty:
        st.warning("Không tải được thông tin token đã chọn.")
        return
    render_token_detail(token.iloc[0], "token_search")


@st.cache_data(ttl=2, show_spinner=False)
def fetch_anomaly_data(api_url: str) -> tuple[pd.DataFrame, str | None]:
    try:
        request = Request(api_url, headers={"User-Agent": "eth-dashboard/1.0"})
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                return pd.DataFrame(), f"API trả HTTP {response.status}"
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return pd.DataFrame(), str(exc)

    if isinstance(payload, dict) and "error" in payload:
        return pd.DataFrame(), str(payload["error"])
    if not isinstance(payload, list):
        payload = [payload]

    return pd.DataFrame(payload), None


@st.cache_data(ttl=2, show_spinner=False)
def fetch_market_trend_data(api_url: str) -> tuple[pd.DataFrame, str | None]:
    try:
        request = Request(api_url, headers={"User-Agent": "eth-dashboard/1.0"})
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                return pd.DataFrame(), f"API trả HTTP {response.status}"
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return pd.DataFrame(), str(exc)

    if isinstance(payload, dict) and "error" in payload:
        return pd.DataFrame(), str(payload["error"])
    if not isinstance(payload, list):
        payload = [payload]

    return pd.DataFrame(payload), None


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {str(col).lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def binance_base_symbol(symbol: str) -> str:
    symbol = re.sub(r"[^A-Za-z0-9]", "", str(symbol or "")).upper()
    wrapped_map = {
        "WETH": "ETH",
        "WBTC": "BTC",
        "WBNB": "BNB",
        "WMATIC": "MATIC",
        "WAVAX": "AVAX",
    }
    return wrapped_map.get(symbol, symbol)


def fmt_usd_price(value) -> str:
    price = safe_float(value)
    if price >= 100:
        return f"${price:,.2f}"
    if price >= 1:
        return f"${price:,.4f}"
    return f"${price:,.8f}"


def normalize_token_address(address) -> str:
    text = str(address or "").strip()
    if re.fullmatch(r"0x[a-fA-F0-9]{40}", text):
        return text.lower()
    return ""


def api_get_json(url: str, timeout: int = 10) -> tuple[dict | list | None, str | None]:
    request = Request(url, headers={"User-Agent": "eth-dashboard/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return None, f"HTTP {response.status}"
            return json.loads(response.read().decode("utf-8")), None
    except HTTPError as exc:
        message = str(exc)
        try:
            body = json.loads(exc.read().decode("utf-8"))
            message = body.get("errors") or body.get("msg") or message
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, AttributeError):
            pass
        return None, str(message)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, str(exc)


def token_side_for_pool(pool_item: dict, token_address: str) -> str:
    relationships = pool_item.get("relationships", {}) if isinstance(pool_item, dict) else {}
    base_id = str(relationships.get("base_token", {}).get("data", {}).get("id", "")).lower()
    quote_id = str(relationships.get("quote_token", {}).get("data", {}).get("id", "")).lower()
    address = token_address.lower()
    if address in base_id:
        return "base"
    if address in quote_id:
        return "quote"
    return "base"


@st.cache_data(ttl=3600, show_spinner=False)
def get_gecko_token_pools(token_address: str) -> tuple[pd.DataFrame, str | None]:
    address = normalize_token_address(token_address)
    if not address:
        return pd.DataFrame(), "Token address không hợp lệ."

    params = urlencode({"include": "base_token,quote_token", "page": 1})
    url = f"{GECKOTERMINAL_BASE_URL}/networks/{GECKOTERMINAL_NETWORK}/tokens/{address}/pools?{params}"
    payload, error = api_get_json(url)
    if error:
        return pd.DataFrame(), error

    data = payload.get("data", []) if isinstance(payload, dict) else []
    rows = []
    for item in data:
        attrs = item.get("attributes", {}) if isinstance(item, dict) else {}
        volume_usd = attrs.get("volume_usd") or {}
        pool_address = attrs.get("address") or str(item.get("id", "")).split("_")[-1]
        rows.append(
            {
                "POOL_ADDRESS": str(pool_address).lower(),
                "POOL_NAME": attrs.get("name") or str(pool_address),
                "DEX": attrs.get("dex_id") or "",
                "TOKEN_SIDE": token_side_for_pool(item, address),
                "PRICE_USD": safe_float(attrs.get("base_token_price_usd")),
                "RESERVE_USD": safe_float(attrs.get("reserve_in_usd")),
                "VOLUME_H24": safe_float(volume_usd.get("h24") if isinstance(volume_usd, dict) else 0),
            }
        )

    pools = pd.DataFrame(rows)
    if pools.empty:
        return pools, None
    pools = pools[pools["POOL_ADDRESS"].str.match(r"^0x[a-f0-9]{40}$", na=False)]
    pools = pools.sort_values(["RESERVE_USD", "VOLUME_H24"], ascending=False).reset_index(drop=True)
    return pools, None


@st.cache_data(ttl=10, show_spinner=False)
def get_gecko_pool_ohlcv(
    pool_address: str,
    timeframe: str,
    aggregate: int,
    token_side: str,
    limit: int = 500,
) -> tuple[pd.DataFrame, str | None]:
    address = normalize_token_address(pool_address)
    if not address:
        return pd.DataFrame(), "Pool address không hợp lệ."

    params = urlencode(
        {
            "aggregate": int(aggregate),
            "limit": int(limit),
            "currency": "usd",
            "token": token_side if token_side in {"base", "quote"} else "base",
        }
    )
    url = (
        f"{GECKOTERMINAL_BASE_URL}/networks/{GECKOTERMINAL_NETWORK}/pools/"
        f"{address}/ohlcv/{timeframe}?{params}"
    )
    payload, error = api_get_json(url)
    if error:
        return pd.DataFrame(), error

    attributes = payload.get("data", {}).get("attributes", {}) if isinstance(payload, dict) else {}
    rows = attributes.get("ohlcv_list", [])
    if not rows:
        return pd.DataFrame(), "GeckoTerminal không trả OHLCV cho pool này."

    candles = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    candles["time"] = pd.to_datetime(candles["time"], unit="s", errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        candles[col] = pd.to_numeric(candles[col], errors="coerce")
    candles = candles.dropna(subset=["time", "open", "high", "low", "close"])
    candles = candles.sort_values("time").reset_index(drop=True)
    return candles, None


def render_address_price_chart(symbol: str, token_address: str, key_prefix: str) -> bool:
    address = normalize_token_address(token_address)
    if not address:
        st.info("Token này chưa có contract address hợp lệ để lấy chart theo address.")
        return False

    st.subheader("Đồ thị giá theo token address")
    pools, pool_error = get_gecko_token_pools(address)
    if pool_error:
        st.info(f"Không lấy được pool từ GeckoTerminal: {pool_error}")
        return False
    if pools.empty:
        st.info(f"Không tìm thấy pool DEX trên Ethereum cho token `{symbol}` ({address}).")
        return False

    control_pool, control_interval = st.columns([3, 2])
    pool_limit = min(len(pools), 20)
    pool_idx = 0
    if pool_limit > 1:
        pool_idx = control_pool.selectbox(
            "Pool DEX theo token address",
            options=list(range(pool_limit)),
            format_func=lambda idx: (
                f"{pools.iloc[idx]['POOL_NAME']} | "
                f"Liquidity ${pools.iloc[idx]['RESERVE_USD']:,.0f} | "
                f"Vol 24h ${pools.iloc[idx]['VOLUME_H24']:,.0f}"
            ),
            key=f"{key_prefix}_gecko_pool",
        )
    else:
        control_pool.metric("Pool DEX theo token address", pools.iloc[0]["POOL_NAME"])

    interval_label = control_interval.selectbox(
        "Khung thời gian",
        list(GECKO_INTERVALS.keys()),
        index=3,
        key=f"{key_prefix}_gecko_interval",
    )
    pool = pools.iloc[int(pool_idx)]
    timeframe, aggregate = GECKO_INTERVALS[interval_label]
    candles, candle_error = get_gecko_pool_ohlcv(
        pool["POOL_ADDRESS"],
        timeframe,
        aggregate,
        pool["TOKEN_SIDE"],
    )
    if candle_error:
        st.info(f"Không lấy được nến theo token address: {candle_error}")
        return False
    if candles.empty:
        st.info("Pool này chưa có dữ liệu OHLCV.")
        return False

    latest = candles.iloc[-1]
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Giá gần nhất", fmt_usd_price(latest["close"]))
    p2.metric("Liquidity", f"${safe_float(pool['RESERVE_USD']):,.0f}")
    p3.metric("Volume 24h", f"${safe_float(pool['VOLUME_H24']):,.0f}")
    p4.metric("Nguồn", "GeckoTerminal")

    candles = candles.copy()
    candles["MA20"] = candles["close"].rolling(20, min_periods=1).mean()
    candles["MA50"] = candles["close"].rolling(50, min_periods=1).mean()
    candles["MA200"] = candles["close"].rolling(200, min_periods=1).mean()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )
    fig.add_trace(
        go.Candlestick(
            x=candles["time"],
            open=candles["open"],
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            name=str(symbol or pool["POOL_NAME"]),
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            increasing_fillcolor="#26a69a",
            decreasing_fillcolor="#ef5350",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=candles["time"], y=candles["MA20"], name="MA20", line=dict(color="#f59e0b", width=1)),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=candles["time"], y=candles["MA50"], name="MA50", line=dict(color="#06b6d4", width=1)),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=candles["time"], y=candles["MA200"], name="MA200", line=dict(color="#a78bfa", width=1, dash="dot")),
        row=1,
        col=1,
    )
    colors = ["#26a69a" if close >= open_ else "#ef5350" for close, open_ in zip(candles["close"], candles["open"])]
    fig.add_trace(
        go.Bar(x=candles["time"], y=candles["volume"], name="Volume", marker_color=colors, opacity=0.6),
        row=2,
        col=1,
    )
    fig.update_layout(
        template="plotly_dark",
        height=620,
        margin=dict(t=20, b=20, l=10, r=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02),
        paper_bgcolor="#0f1117",
        plot_bgcolor="#0f1117",
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#1e2133", showspikes=True, spikemode="across", spikesnap="cursor")
    fig.update_yaxes(gridcolor="#1e2133", side="right", showspikes=True, spikemode="across", spikesnap="cursor")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Contract: {address} | Pool: {pool['POOL_ADDRESS']} | Network: Ethereum")
    return True


@st.cache_data(ttl=10, show_spinner=False)
def get_binance_klines(symbol: str, interval: str, limit: int = 500) -> tuple[pd.DataFrame, str | None]:
    params = urlencode({"symbol": symbol, "interval": interval, "limit": int(limit)})
    request = Request(
        f"https://api.binance.com/api/v3/klines?{params}",
        headers={"User-Agent": "eth-dashboard/1.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                return pd.DataFrame(), f"Binance trả HTTP {response.status}"
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = str(exc)
        try:
            body = json.loads(exc.read().decode("utf-8"))
            message = body.get("msg") or message
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
        return pd.DataFrame(), message
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return pd.DataFrame(), str(exc)

    if isinstance(payload, dict):
        return pd.DataFrame(), str(payload.get("msg") or payload)
    if not isinstance(payload, list) or not payload:
        return pd.DataFrame(), "Binance không trả dữ liệu nến hợp lệ."

    df = pd.DataFrame(
        payload,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "qav",
            "trades",
            "tbbav",
            "tbqav",
            "ignore",
        ],
    )
    df["time"] = pd.to_datetime(df["time"], unit="ms", errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time", "open", "high", "low", "close"]).reset_index(drop=True)
    return df, None


@st.cache_data(ttl=3600, show_spinner=False)
def get_binance_exchange_symbols() -> tuple[pd.DataFrame, str | None]:
    request = Request(
        "https://api.binance.com/api/v3/exchangeInfo",
        headers={"User-Agent": "eth-dashboard/1.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                return pd.DataFrame(), f"Binance trả HTTP {response.status}"
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = str(exc)
        try:
            body = json.loads(exc.read().decode("utf-8"))
            message = body.get("msg") or message
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
        return pd.DataFrame(), message
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return pd.DataFrame(), str(exc)

    symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
    if not symbols:
        return pd.DataFrame(), "Binance không trả danh sách cặp giao dịch."
    df = pd.DataFrame(symbols)
    keep = [col for col in ["symbol", "baseAsset", "quoteAsset", "status"] if col in df.columns]
    return df[keep], None


def resolve_binance_pair(base_symbol: str) -> tuple[str | None, str | None]:
    pairs, error = binance_pairs_for_base(base_symbol)
    return (pairs[0] if pairs else None), error


def binance_pairs_for_base(base_symbol: str) -> tuple[list[str], str | None]:
    exchange_symbols, error = get_binance_exchange_symbols()
    if error or exchange_symbols.empty:
        return [f"{base_symbol}USDT"], error

    matches = exchange_symbols[
        (exchange_symbols["baseAsset"].astype(str).str.upper() == str(base_symbol).upper())
        & (exchange_symbols["status"].astype(str).str.upper() == "TRADING")
    ].copy()
    if matches.empty:
        return [], None

    matches["quote_rank"] = matches["quoteAsset"].astype(str).str.upper().apply(
        lambda quote: BINANCE_QUOTE_PRIORITY.index(quote)
        if quote in BINANCE_QUOTE_PRIORITY
        else len(BINANCE_QUOTE_PRIORITY)
    )
    matches = matches.sort_values(["quote_rank", "symbol"]).reset_index(drop=True)
    return matches["symbol"].astype(str).tolist(), None


@st.cache_data(ttl=10, show_spinner=False)
def get_binance_ticker(symbol: str) -> tuple[dict, str | None]:
    params = urlencode({"symbol": symbol})
    request = Request(
        f"https://api.binance.com/api/v3/ticker/24hr?{params}",
        headers={"User-Agent": "eth-dashboard/1.0"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                return {}, f"Binance trả HTTP {response.status}"
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = str(exc)
        try:
            body = json.loads(exc.read().decode("utf-8"))
            message = body.get("msg") or message
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
        return {}, message
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {}, str(exc)

    if not isinstance(payload, dict) or "lastPrice" not in payload:
        return {}, str(payload.get("msg") if isinstance(payload, dict) else "Ticker Binance không hợp lệ.")
    return payload, None


def render_binance_live_chart(symbol: str, key_prefix: str):
    base_symbol = binance_base_symbol(symbol)
    if not base_symbol:
        st.info("Token này chưa có symbol hợp lệ để tìm cặp Binance.")
        return False

    st.subheader("Đồ thị giá Binance")

    pairs, pair_error = binance_pairs_for_base(base_symbol)
    if pair_error:
        st.caption(f"Không kiểm tra được danh sách cặp Binance: {pair_error}. Chỉ thử cặp `{base_symbol}USDT`.")
    if not pairs:
        st.info(f"Binance không có cặp đang giao dịch cho token `{base_symbol}`. Không vẽ chart của token khác.")
        return False

    control_pair, control_interval = st.columns([3, 2])
    if len(pairs) == 1:
        pair = pairs[0]
        control_pair.metric(f"Cặp Binance của {base_symbol}", pair)
    else:
        pair = control_pair.selectbox(
            f"Cặp Binance của {base_symbol}",
            pairs,
            index=0,
            key=f"{key_prefix}_binance_pair",
        )
    interval_label = control_interval.selectbox(
        "Khung thời gian",
        list(BINANCE_INTERVALS.keys()),
        index=3,
        key=f"{key_prefix}_binance_interval",
    )

    interval = BINANCE_INTERVALS[interval_label]
    df, error = get_binance_klines(pair, interval)
    ticker, ticker_error = get_binance_ticker(pair)

    if error:
        st.info(f"Không lấy được dữ liệu Binance cho `{pair}`: {error}. Không vẽ chart của token khác.")
        return False
    if df.empty:
        st.info(f"Binance chưa có dữ liệu nến cho `{pair}`.")
        return False

    if ticker and not ticker_error:
        pct = safe_float(ticker.get("priceChangePercent"))
        t1, t2, t3, t4, t5 = st.columns(5)
        t1.metric("Giá", fmt_usd_price(ticker.get("lastPrice")), f"{pct:+.2f}%")
        t2.metric("Cao 24h", fmt_usd_price(ticker.get("highPrice")))
        t3.metric("Thấp 24h", fmt_usd_price(ticker.get("lowPrice")))
        t4.metric("Volume 24h", f"{safe_float(ticker.get('volume')):,.0f}")
        t5.metric("Số GD 24h", f"{safe_int(ticker.get('count')):,}")
    elif ticker_error:
        st.caption(f"Không lấy được ticker 24h: {ticker_error}")

    df = df.copy()
    df["MA20"] = df["close"].rolling(20, min_periods=1).mean()
    df["MA50"] = df["close"].rolling(50, min_periods=1).mean()
    df["MA200"] = df["close"].rolling(200, min_periods=1).mean()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25],
    )
    fig.add_trace(
        go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=pair,
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            increasing_fillcolor="#26a69a",
            decreasing_fillcolor="#ef5350",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["time"], y=df["MA20"], name="MA20", line=dict(color="#f59e0b", width=1)),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["time"], y=df["MA50"], name="MA50", line=dict(color="#06b6d4", width=1)),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["time"], y=df["MA200"], name="MA200", line=dict(color="#a78bfa", width=1, dash="dot")),
        row=1,
        col=1,
    )

    colors = ["#26a69a" if close >= open_ else "#ef5350" for close, open_ in zip(df["close"], df["open"])]
    fig.add_trace(
        go.Bar(x=df["time"], y=df["volume"], name="Volume", marker_color=colors, opacity=0.6),
        row=2,
        col=1,
    )
    fig.update_layout(
        template="plotly_dark",
        height=620,
        margin=dict(t=20, b=20, l=10, r=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02),
        paper_bgcolor="#0f1117",
        plot_bgcolor="#0f1117",
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#1e2133", showspikes=True, spikemode="across", spikesnap="cursor")
    fig.update_yaxes(gridcolor="#1e2133", side="right", showspikes=True, spikemode="across", spikesnap="cursor")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Dữ liệu Binance REST được cache 10 giây; đổi cặp hoặc khung thời gian để cập nhật.")
    return True


def render_realtime_price_if_available(df: pd.DataFrame):
    time_col = find_column(df, ["timestamp", "time", "created_at", "last_active", "block_timestamp"])
    open_col = find_column(df, ["open", "open_price", "price_open"])
    high_col = find_column(df, ["high", "high_price", "price_high"])
    low_col = find_column(df, ["low", "low_price", "price_low"])
    close_col = find_column(df, ["close", "close_price", "price_close", "price"])
    volume_col = find_column(df, ["volume", "amount", "so_eth_giao_dich", "value_eth"])

    if not all([time_col, open_col, high_col, low_col, close_col]):
        st.info(
            "API realtime hiện là dữ liệu bất thường giao dịch, chưa có OHLC/price token nên không dùng để dựng đồ thị giá chứng khoán thật được."
        )
        return

    candles = df[[time_col, open_col, high_col, low_col, close_col]].copy()
    candles.columns = ["TS", "OPEN", "HIGH", "LOW", "CLOSE"]
    if volume_col:
        candles["VOLUME"] = df[volume_col]
    candles = normalize_candles(candles)
    if candles.empty:
        st.info("Có cột OHLC nhưng dữ liệu không đủ hợp lệ để vẽ nến.")
        return

    st.subheader("Đồ thị giá realtime từ API")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.035)
    fig.add_trace(
        go.Candlestick(
            x=candles["TS"],
            open=candles["OPEN"],
            high=candles["HIGH"],
            low=candles["LOW"],
            close=candles["CLOSE"],
            increasing_line_color="#16a34a",
            decreasing_line_color="#dc2626",
            name="OHLC",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(go.Bar(x=candles["TS"], y=candles["VOLUME"], marker_color="#475569", name="Volume"), row=2, col=1)
    fig.update_layout(
        height=560,
        template="plotly_dark",
        margin=dict(t=30, b=20, l=10, r=24),
        xaxis_rangeslider_visible=True,
        yaxis=dict(side="right", title="Giá"),
        yaxis2=dict(side="right", title="Volume"),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_realtime_anomaly_page():
    st.title("🚨 Phát hiện bất thường real-time")
    st.caption("Tích hợp từ app2.py, lấy dữ liệu từ API anomaly backend.")

    c_url, c_auto = st.columns([4, 1])
    with c_url:
        api_url = st.text_input("API endpoint", ANOMALY_API_URL, key="anomaly_api_url")
    with c_auto:
        auto_refresh = st.checkbox("Auto 2s", value=False, key="anomaly_auto_refresh")

    refresh = st.button("Refresh dữ liệu", key="anomaly_refresh")
    if refresh:
        fetch_anomaly_data.clear()

    df_current, error = fetch_anomaly_data(api_url)
    if error:
        st.warning(f"Không lấy được dữ liệu realtime: {error}")
        if auto_refresh:
            time.sleep(2)
            st.rerun()
        return

    if df_current.empty:
        st.info("Hệ thống đang quét luồng, chưa có giao dịch bất thường.")
        if auto_refresh:
            time.sleep(2)
            st.rerun()
        return

    amount_col = find_column(df_current, ["so_eth_giao_dich", "amount", "value_eth", "eth", "value"])
    sender_col = find_column(df_current, ["vi_gui_rui_ro", "from", "from_address", "sender", "wallet", "user_id"])
    receiver_col = find_column(df_current, ["vi_nhan", "to", "to_address", "receiver"])
    pagerank_col = find_column(df_current, ["pagerank", "page_rank", "score"])
    time_col = find_column(df_current, ["timestamp", "time", "created_at", "block_timestamp"])

    if amount_col:
        df_current[amount_col] = pd.to_numeric(df_current[amount_col], errors="coerce").fillna(0)

    total_alerts = len(df_current)
    total_eth = df_current[amount_col].sum() if amount_col else 0
    max_eth = df_current[amount_col].max() if amount_col else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tổng cảnh báo", f"{total_alerts:,}")
    m2.metric("Tổng ETH bất thường", f"{total_eth:,.4g}")
    m3.metric("Giao dịch lớn nhất", f"{max_eth:,.4g}")
    m4.metric("Nguồn API", "Online")

    st.divider()
    chart_l, chart_r = st.columns(2)

    if amount_col and sender_col:
        with chart_l:
            st.subheader("Top ví rủi ro theo ETH")
            top_transfers = (
                df_current.groupby(sender_col)[amount_col]
                .sum()
                .reset_index()
                .sort_values(amount_col, ascending=False)
                .head(10)
            )
            top_transfers[sender_col] = top_transfers[sender_col].astype(str)
            fig_top = px.bar(
                top_transfers.sort_values(amount_col, ascending=True),
                x=amount_col,
                y=sender_col,
                orientation="h",
                template="plotly_dark",
                color=amount_col,
                color_continuous_scale="Reds",
                labels={sender_col: "Ví gửi rủi ro", amount_col: "ETH"},
            )
            fig_top.update_layout(height=380, margin=dict(t=10, b=10))
            st.plotly_chart(fig_top, use_container_width=True)

    if amount_col:
        with chart_r:
            st.subheader("Luồng ETH bất thường")
            series = df_current.copy()
            if time_col:
                series["_TS"] = pd.to_datetime(series[time_col], errors="coerce")
            else:
                series["_TS"] = range(1, len(series) + 1)
            fig_flow = px.area(
                series,
                x="_TS",
                y=amount_col,
                template="plotly_dark",
                color_discrete_sequence=["#ef4444"],
                labels={"_TS": "Thời gian" if time_col else "Thứ tự bản ghi", amount_col: "ETH"},
            )
            fig_flow.update_layout(height=380, margin=dict(t=10, b=10))
            st.plotly_chart(fig_flow, use_container_width=True)

    if amount_col and pagerank_col:
        st.subheader("Tương quan PageRank và giá trị giao dịch")
        df_current[pagerank_col] = pd.to_numeric(df_current[pagerank_col], errors="coerce")
        fig_scatter = px.scatter(
            df_current,
            x=pagerank_col,
            y=amount_col,
            color=amount_col,
            size=amount_col,
            hover_data=[col for col in [sender_col, receiver_col] if col],
            template="plotly_dark",
            color_continuous_scale="Reds",
            labels={pagerank_col: "PageRank", amount_col: "ETH"},
        )
        fig_scatter.update_layout(height=420, margin=dict(t=10, b=10))
        st.plotly_chart(fig_scatter, use_container_width=True)

    st.subheader("Danh sách giao dịch bất thường")
    display = df_current.iloc[::-1].reset_index(drop=True)
    if amount_col:
        display = display.sort_values(amount_col, ascending=False).reset_index(drop=True)
    selectable_dataframe(display.head(200), key="anomaly_table", height=None)

    if auto_refresh:
        time.sleep(2)
        st.rerun()


def render_market_trend_page():
    st.title("📈 Ethereum Real-time Market Trend Dashboard")
    st.caption("Bê từ app2.py: tổng hợp xu hướng token theo cửa sổ realtime.")

    c_url, c_auto = st.columns([4, 1])
    with c_url:
        api_url = st.text_input("API endpoint", MARKET_TREND_API_URL, key="market_trend_api_url")
    with c_auto:
        auto_refresh = st.checkbox("Auto 2s", value=True, key="market_trend_auto_refresh")

    refresh = st.button("Refresh dữ liệu", key="market_trend_refresh")
    if refresh:
        fetch_market_trend_data.clear()

    df_trends, error = fetch_market_trend_data(api_url)
    if error:
        st.info(f"⏳ Đang chờ Spark tổng hợp khung 2 phút đầu tiên hoặc API chưa sẵn sàng: {error}")
        if auto_refresh:
            time.sleep(2)
            st.rerun()
        return

    if df_trends.empty:
        st.info("Chưa có dữ liệu xu hướng thị trường.")
        if auto_refresh:
            time.sleep(2)
            st.rerun()
        return

    token_col = find_column(df_trends, ["token_id", "TOKEN_ID", "mã token", "ma_token"])
    volume_col = find_column(df_trends, ["tong_khoi_luong", "total_volume", "volume", "khoi_luong"])
    count_col = find_column(df_trends, ["tong_so_lenh", "total_orders", "order_count", "so_lenh"])
    start_col = find_column(df_trends, ["bat_dau", "start", "window_start", "begin"])
    end_col = find_column(df_trends, ["ket_thuc", "end", "window_end", "finish"])

    if not all([token_col, volume_col, count_col]):
        st.warning("API trending chưa trả đủ cột token_id, tong_khoi_luong, tong_so_lenh.")
        selectable_dataframe(df_trends.head(200), key="market_trend_raw", height=None)
        return

    df_trends = df_trends.copy()
    df_trends[volume_col] = pd.to_numeric(df_trends[volume_col], errors="coerce").fillna(0)
    df_trends[count_col] = pd.to_numeric(df_trends[count_col], errors="coerce").fillna(0)
    df_trends[token_col] = df_trends[token_col].astype(str)
    df_trends = df_trends.sort_values(volume_col, ascending=False).reset_index(drop=True)

    top_volume = df_trends.iloc[0]
    top_freq = df_trends.loc[df_trends[count_col].idxmax()]

    st.subheader("🔥 TOKEN HOT NHẤT (Cửa Sổ 2 Phút)")
    col_vol, col_freq = st.columns(2)

    with col_vol:
        st.markdown("#### 🐳 Top Khối Lượng")
        c1, c2 = st.columns(2)
        c1.metric("🏆 Mã Token", f"ID: {top_volume[token_col]}")
        c2.metric("⚡ Số Lệnh", f"{safe_int(top_volume[count_col]):,} lệnh")
        st.metric("💰 Tổng Khối Lượng", f"{safe_float(top_volume[volume_col]):,.2f} ETH")

    with col_freq:
        st.markdown("#### 🐝 Top Lượt Giao Dịch")
        c3, c4 = st.columns(2)
        c3.metric("🏆 Mã Token", f"ID: {top_freq[token_col]}")
        c4.metric("⚡ Số Lệnh", f"{safe_int(top_freq[count_col]):,} lệnh")
        st.metric("💰 Tổng Khối Lượng", f"{safe_float(top_freq[volume_col]):,.2f} ETH")

    st.markdown("<br><hr>", unsafe_allow_html=True)

    col_chart, col_table = st.columns([6, 4])
    with col_chart:
        st.subheader("📊 Top 10 Token (Theo Khối Lượng)")
        top_n = df_trends.head(10).copy()
        fig = px.bar(
            top_n,
            x=token_col,
            y=volume_col,
            labels={token_col: "Mã Token", volume_col: "Khối Lượng (ETH)"},
            color=volume_col,
            color_continuous_scale="Viridis",
            text_auto=".2s",
            log_y=True,
            template="plotly_dark",
        )
        fig.update_xaxes(type="category")
        fig.update_traces(textfont_size=13, textangle=0, textposition="outside", cliponaxis=False)
        fig.update_layout(height=430, margin=dict(t=30, b=10, l=10, r=10), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.subheader("📋 Bảng Xếp Hạng Chi Tiết")
        display_cols = [token_col, volume_col, count_col]
        rename_cols = {
            token_col: "Mã Token",
            volume_col: "Khối Lượng (ETH)",
            count_col: "Số Lệnh",
        }
        if start_col:
            display_cols.append(start_col)
            rename_cols[start_col] = "Bắt Đầu"
        if end_col:
            display_cols.append(end_col)
            rename_cols[end_col] = "Kết Thúc"
        st.dataframe(
            df_trends[display_cols].rename(columns=rename_cols),
            use_container_width=True,
            height=400,
        )

    if auto_refresh:
        time.sleep(2)
        fetch_market_trend_data.clear()
        st.rerun()


with st.sidebar:
    st.title("🪙 Crypto Analytics")
    st.divider()
    menu = st.radio(
        "menu",
        [
            "🏠 Dashboard",
            "🔍 Tìm kiếm ví & gợi ý token",
            "📈 Tìm kiếm token",
            "📊 Xu hướng thị trường Real-time",
            "🚨 Phát hiện bất thường real-time",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(f"📦 {len(df_pr):,} ví PageRank | {df_tk['SYMBOL'].nunique():,} token")


if menu == "🏠 Dashboard":
    render_dashboard()
elif menu == "🔍 Tìm kiếm ví & gợi ý token":
    render_wallet_search()
elif menu == "📈 Tìm kiếm token":
    render_token_search()
elif menu == "📊 Xu hướng thị trường Real-time":
    render_market_trend_page()
else:
    render_realtime_anomaly_page()
