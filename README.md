# 💬 Talk to Your Data

An AI-powered analytics tool that lets you ask questions about your data in plain English. The app converts your question into safe SQL, runs it, self-heals on errors, and tracks cost and latency in real time.

**🔗 Live demo:** [your-streamlit-link-here]

---

## ✨ Features

- **Natural language → SQL** — Ask "What is the total revenue?" and get an answer, no SQL needed.
- **Self-healing queries** — If the generated SQL fails, the app feeds the error back to the model and retries automatically (up to 2 times).
- **Safety guardrails** — Only `SELECT` queries run. `DROP`, `DELETE`, `UPDATE`, and multi-statement attacks are blocked.
- **CSV upload** — Drop in any CSV and query it instantly (loaded as a table called `data`).
- **Cost & latency monitoring** — Every query logs tokens, latency, and USD cost; a Metrics tab shows running totals.
- **Auto-charting** — Results with a numeric column render as a bar chart automatically.
- **Query history** — Recent questions are saved in the sidebar.



## 🛠️ Tech Stack

| Layer | Tool |
|---|---|
| LLM | Groq (Llama 3.3 70B) |
| Frontend | Streamlit |
| Data | SQLite + pandas |
| Language | Python |

---

## 🚀 Run it locally

```bash
git clone https://github.com/your-username/talk-to-your-data.git
cd talk-to-your-data
pip install -r requirements.txt
