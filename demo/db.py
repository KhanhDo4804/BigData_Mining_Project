import re
from typing import Optional, Sequence

import pandas as pd
import snowflake.connector
import streamlit as st


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ORDER_ITEM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\s+(ASC|DESC))?$", re.IGNORECASE)


def _connect():
    return snowflake.connector.connect(
        account=st.secrets["SNOWFLAKE_ACCOUNT"],
        user=st.secrets["SNOWFLAKE_USER"],
        password=st.secrets["SNOWFLAKE_PASSWORD"],
        role=st.secrets["SNOWFLAKE_ROLE"],
        warehouse=st.secrets["SNOWFLAKE_WAREHOUSE"],
        database=st.secrets["SNOWFLAKE_DATABASE"],
        schema=st.secrets["SNOWFLAKE_SCHEMA"],
    )


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.upper() for c in df.columns]
    return df


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return value.upper()


def _safe_order_by(value: str) -> str:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items or not all(_ORDER_ITEM_RE.fullmatch(item) for item in items):
        raise ValueError(f"Unsafe ORDER BY clause: {value}")
    return ", ".join(item.upper() for item in items)


@st.cache_data(ttl=3600, show_spinner="Dang tai du lieu tu Snowflake...")
def run_query(query: str, params: Optional[Sequence[object]] = None) -> pd.DataFrame:
    conn = _connect()
    try:
        if params is None:
            df = pd.read_sql(query, conn)
        else:
            df = pd.read_sql(query, conn, params=tuple(params))
    finally:
        conn.close()
    return _normalize_columns(df)


@st.cache_data(ttl=3600, show_spinner="Dang tai du lieu tu Snowflake...")
def load_table(table_name: str, limit: Optional[int] = None, order_by: Optional[str] = None) -> pd.DataFrame:
    table = _safe_identifier(table_name)

    query = f"SELECT * FROM {table}"
    if order_by:
        query += f" ORDER BY {_safe_order_by(order_by)}"
    if limit is not None:
        query += f" LIMIT {max(1, int(limit))}"

    return run_query(query)
