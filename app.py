import streamlit as st
import pandas as pd
import sqlite3
import os
import time
import re
from groq import Groq

# ---------- CONFIG ----------
MODEL = "llama-3.3-70b-versatile"
COST_PER_1M_INPUT = 0.59
COST_PER_1M_OUTPUT = 0.79
MAX_RETRIES = 2

st.set_page_config(page_title="Talk to Your Data", page_icon="💬", layout="wide")

# ---------- GROQ CLIENT ----------
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# ---------- DATABASE (Feature 1: CSV upload + fallback) ----------
st.sidebar.header("Your Data")
uploaded = st.sidebar.file_uploader("Upload a CSV", type=["csv"])

@st.cache_resource
def build_db_from_csv(file):
    df = pd.read_csv(file)
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    df.to_sql("data", conn, if_exists="replace", index=False)
    return conn

if uploaded:
    conn = build_db_from_csv(uploaded)
    st.sidebar.success("Loaded! Table name: data")
else:
    conn = sqlite3.connect("shop.db", check_same_thread=False)
    st.sidebar.info("Using demo database (shop.db)")

# ---------- SCHEMA ----------
def get_schema(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cur.fetchall()]
    schema = ""
    for t in tables:
        cur.execute(f"PRAGMA table_info({t});")
        cols = [c[1] for c in cur.fetchall()]
        schema += f"Table {t}: {', '.join(cols)}\n"
    return schema

# ---------- SAFETY (SELECT-only guardrail) ----------
def is_safe_sql(sql):
    s = sql.strip().lower()
    banned = ["drop", "delete", "update", "insert", "alter", "truncate", "create", "replace"]
    if not s.startswith("select"):
        return False, "Only SELECT queries are allowed."
    if ";" in s.rstrip(";"):
        return False, "Multiple statements are not allowed."
    for word in banned:
        if re.search(r"\b" + word + r"\b", s):
            return False, f"Banned keyword detected: {word}"
    return True, "OK"

# ---------- LLM CALL WITH METRICS (Feature 2) ----------
def call_llm_with_metrics(messages):
    start = time.time()
    resp = client.chat.completions.create(model=MODEL, messages=messages)
    latency = time.time() - start
    usage = resp.usage
    cost = (usage.prompt_tokens / 1_000_000 * COST_PER_1M_INPUT +
            usage.completion_tokens / 1_000_000 * COST_PER_1M_OUTPUT)
    metrics = {
        "latency_s": round(latency, 2),
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "cost_usd": round(cost, 6),
    }
    return resp.choices[0].message.content, metrics

# ---------- CLEAN SQL FROM MODEL OUTPUT ----------
def clean_sql(text):
    text = text.replace("```sql", "").replace("```", "").strip()
    return text

# ---------- GENERATE SQL (Feature 4: cached) ----------
@st.cache_data
def generate_sql_cached(question, schema):
    messages = [
        {"role": "system", "content":
            "You are an expert SQLite analyst. Convert the user's question into a single "
            "valid SQLite SELECT query. Use ONLY the tables and columns in the schema. "
            "Never invent table or column names. Return ONLY the SQL, no explanation."},
        {"role": "user", "content": f"Schema:\n{schema}\n\nQuestion: {question}"},
    ]
    sql, metrics = call_llm_with_metrics(messages)
    return clean_sql(sql), metrics

# ---------- FIX SQL ON ERROR ----------
def fix_sql(question, schema, bad_sql, error):
    messages = [
        {"role": "system", "content":
            "You fix broken SQLite queries. Return ONLY the corrected SELECT query, no explanation. "
            "Use ONLY the tables and columns in the schema. Never invent names."},
        {"role": "user", "content":
            f"Schema:\n{schema}\n\nQuestion: {question}\n\n"
            f"This SQL failed:\n{bad_sql}\n\nError:\n{error}\n\nFix it."},
    ]
    sql, metrics = call_llm_with_metrics(messages)
    return clean_sql(sql), metrics

# ---------- SELF-HEALING PIPELINE (Feature 3 pipeline + retry loop) ----------
def question_to_sql_with_retry(question, conn):
    schema = get_schema(conn)
    sql, metrics = generate_sql_cached(question, schema)
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        safe, reason = is_safe_sql(sql)
        if not safe:
            return None, None, sql, f"Blocked by safety guard: {reason}", metrics
        try:
            df = pd.read_sql_query(sql, conn)
            return df, sql, None, None, metrics
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                sql, m2 = fix_sql(question, schema, sql, last_error)
                metrics = m2
            else:
                return None, sql, None, last_error, metrics

# ---------- SESSION STATE ----------
if "history" not in st.session_state:
    st.session_state.history = []
if "all_metrics" not in st.session_state:
    st.session_state.all_metrics = []

# ---------- HISTORY SIDEBAR (Feature 4) ----------
with st.sidebar.expander("Query History"):
    for h in reversed(st.session_state.history[-10:]):
        st.write(f"- {h['q']}")

# ---------- MAIN UI ----------
st.title("Talk to Your Data")
st.caption("Ask questions in plain English. The AI writes safe SQL, self-heals errors, and tracks cost.")

tab1, tab2 = st.tabs(["Ask", "Metrics"])

with tab1:
    question = st.text_input("Ask a question about your data:",
                             placeholder="e.g. How many customers are there?")
    if st.button("Run") and question:
        with st.spinner("Thinking..."):
            df, sql, blocked, error, metrics = question_to_sql_with_retry(question, conn)

        if metrics:
            st.session_state.all_metrics.append(metrics)
            c1, c2, c3 = st.columns(3)
            c1.metric("Latency", f"{metrics['latency_s']}s")
            c2.metric("Tokens", metrics["input_tokens"] + metrics["output_tokens"])
            c3.metric("Cost", f"${metrics['cost_usd']:.5f}")

        if blocked:
            st.error(blocked)
        elif error:
            st.error(f"SQL error after retries: {error}")
            st.code(sql, language="sql")
        elif df is not None:
            st.session_state.history.append({"q": question, "sql": sql})
            st.code(sql, language="sql")
            st.dataframe(df)
            # Auto-chart if there's a numeric column
            numeric_cols = df.select_dtypes(include="number").columns
            if len(df) > 1 and len(numeric_cols) >= 1:
                st.bar_chart(df.set_index(df.columns[0])[numeric_cols[0]])

with tab2:
    if st.session_state.all_metrics:
        m_df = pd.DataFrame(st.session_state.all_metrics)
        a, b, c = st.columns(3)
        a.metric("Total queries", len(m_df))
        b.metric("Avg latency", f"{m_df['latency_s'].mean():.2f}s")
        c.metric("Total cost", f"${m_df['cost_usd'].sum():.5f}")
        st.line_chart(m_df["latency_s"])
    else:
        st.info("Ask some questions to see metrics here.")
