import os
import sqlite3
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from groq import Groq

# --- Setup ---
st.set_page_config(page_title="Talk to Your Data", page_icon="💬")
st.title("💬 Talk to Your Data")
st.caption("Ask questions in plain English → AI writes SQL → you get answers.")

client = Groq(api_key=st.secrets["GROQ_API_KEY"])
DB_FILE = "shop.db"

# --- Schema ---
def get_schema(db_file):
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table';")
    schema = "\n".join(row[0] for row in cur.fetchall() if row[0])
    conn.close()
    return schema

# --- Safety guard ---
def is_safe_sql(sql):
    s = sql.strip().lower()
    if not (s.startswith("select") or s.startswith("with")):
        return False, "Only SELECT queries are allowed (read-only app)."
    banned = ["drop", "delete", "update", "insert", "alter",
              "truncate", "replace", "create", "attach", "pragma"]
    for word in banned:
        if f" {word} " in f" {s} " or s.startswith(word):
            return False, f"Blocked: '{word}' is not allowed (read-only app)."
    if ";" in s.rstrip(";"):
        return False, "Blocked: multiple statements are not allowed."
    return True, "OK"

# --- Self-healing SQL generator ---
def question_to_sql_with_retry(question, schema, db_file, max_tries=3):
    last_error = ""
    sql = ""
    for attempt in range(1, max_tries + 1):
        if attempt == 1:
            prompt = f"""You are an expert SQLite analyst.
Given the schema below, write ONE SQL query that answers the question.

Rules:
- Return ONLY raw SQL. No explanations, no markdown.
- Use only tables and columns that exist in the schema.
- When the question asks about a CATEGORY, GROUP BY category and aggregate across ALL products.
- Use JOINs when the question needs data from more than one table.
- Prefer SUM/COUNT/AVG with GROUP BY for "which X sells/earns the most" questions.

Schema:
{schema}

Question: {question}
"""
        else:
            prompt = f"""You are an expert SQLite analyst.
Your previous SQL FAILED. Fix it.

Schema:
{schema}

Question: {question}

Previous (broken) SQL:
{sql}

Error it produced:
{last_error}

Return ONLY the corrected raw SQL. No explanations, no markdown.
"""
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        sql = response.choices[0].message.content.strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()

        try:
            safe, reason = is_safe_sql(sql)
            if not safe:
                last_error = f"SAFETY BLOCK: {reason}"
                if attempt == max_tries:
                    return sql, None, reason
                continue
            conn = sqlite3.connect(db_file)
            df = pd.read_sql_query(sql, conn)
            conn.close()
            return sql, df, None
        except Exception as e:
            last_error = str(e)
            if attempt == max_tries:
                return sql, None, last_error
    return sql, None, last_error

# --- UI ---
question = st.text_input("Ask a question about your data:",
                         placeholder="e.g. total quantity sold per category")

if question:
    schema = get_schema(DB_FILE)
    with st.spinner("Thinking..."):
        sql, df, err = question_to_sql_with_retry(question, schema, DB_FILE)

    st.subheader("🧠 Generated SQL")
    st.code(sql, language="sql")

    if df is not None:
        st.subheader("📊 Result")
        st.dataframe(df)
        # auto-chart if 2 columns: label + number
        if df.shape[1] == 2 and pd.api.types.is_numeric_dtype(df.iloc[:, 1]):
            fig, ax = plt.subplots()
            ax.bar(df.iloc[:, 0].astype(str), df.iloc[:, 1])
            plt.xticks(rotation=45, ha="right")
            st.pyplot(fig)
    else:
        st.error(f"Couldn't get a working query. Reason: {err}")
