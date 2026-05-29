Feature,Where it lives
1. CSV upload,Sidebar → uploads become a table called data; falls back to shop.db
2. Cost + latency logging,call_llm_with_metrics() → shown as 3 metric cards after every query
3. Eval-ready pipeline,question_to_sql_with_retry() is callable standalone (see note below)
4. History + caching,Sidebar history + @st.cache_data on generate_sql_cached()
5. Metrics dashboard,The 📊 Metrics tab aggregates latency + cost across the session
Safety,"is_safe_sql() — SELECT-only, blocks drop/delete/etc. + multi-statements"
Self-healing,Retry loop catches SQL errors and asks the model to fix them