import os
from typing import Dict, Any

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from urllib.parse import quote_plus
import google.generativeai as genai
from database import get_db_config

# # Setup the key
# if "GOOGLE_API_KEY" in st.secrets:
#     genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
# else:
#     genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Setup the key - HARDCODED for safety
API_KEY = "YOUR_API_KEY"
genai.configure(api_key=API_KEY)


# --- AI CORE LOGIC ---
def get_ai_sql(user_query: str) -> str:
    """Uses Gemini 1.5 to translate natural language into PostgreSQL with your specific rules."""
    if "ai_cache" not in st.session_state:
        st.session_state.ai_cache = {}

    query_key = user_query.lower().strip()

    if query_key in st.session_state.ai_cache:
        return st.session_state.ai_cache[query_key]

    try:
        # 1. Define YOUR specific Rules
        schema_context = """
        You are a SQL expert for PostgreSQL. 

        RULES:
        - All tables are in the 'costco_analytics' schema.
        - Use 'costco_analytics.tablename' in your JOINS.
        - The current database name is 'zava'.
        - If the user asks for 'underperforming', 'worst', or 'low', use ORDER BY ASC.
        - Use ILIKE with wildcards (e.g., ILIKE '%Seattle%') for Warehouse and Product name searches to ensure matches.
        - DATA INTERPRETATION: Do not flag results as "incomplete" or "missing details" if a query returns a few rows (e.g., one grocery item). Acknowledge the returned data as the full current state of the warehouse.

        9-TABLE SCHEMA (CRITICAL COLUMN NAMES):
        - Warehouse: warehouseid, name, region, managername
        - Category: categoryid, name, deptcode
        - Supplier: supplierid, name, contactperson, email, phone
        - Member: memberid, name, email, membershiptype, joindate
        - Product: productid, categoryid, name, price, product_details
        - ProductSupplier: productid, supplierid, supplycost, leadtimedays
        - Inventory: warehouseid, productid, stockquantity, reorderlevel
        - SalesTransaction: transactionid, memberid, warehouseid, transactiondate, totalamount
        - SalesTransactionItem: lineitemid, transactionid, productid, quantity, unitpriceatsale, subtotal

        BUSINESS LOGIC FOR SCENARIOS:
        - Scenario 1 (Revenue): SUM(subtotal) grouped by Category name.
        - Scenario 2 (Performance): SUM(totalamount) grouped by Warehouse name.
        - Scenario 3 (Reorder): stockquantity < reorderlevel. Join Supplier to get contact info.
        - Scenario 4 (Underperforming): Identify Warehouse/Category pairs with lowest SUM(subtotal).
        - Scenario 5 (Promotional): Identify products where COALESCE(SUM(quantity), 0) < (stockquantity * 0.05). Calculate trapped_capital AS (stockquantity * price). ORDER BY trapped_capital DESC.

        Write ONLY the SQL code, no markdown, no backticks.
        """
        
        # 2. Call Gemini 1.5 Flash (Better quota limits for Free Tier)
        prompt = f"{schema_context}\n\nUser Question: {user_query}\nSQL Query:"
        model = genai.GenerativeModel('gemini-2.5-flash') 
        response = model.generate_content(prompt)
        
        sql = response.text.replace('```sql', '').replace('```', '').strip()
        st.session_state.ai_cache[query_key] = sql
        
        return sql
    
    except Exception as e:
        if "429" in str(e):
            return "SELECT 'Error' as Status, 'API Quota Exceeded. Please wait 60 seconds or use a different key.' as Message;"
        return f"SELECT 'Error' as Status, '{str(e)}' as Message;"
    

st.set_page_config(
    page_title="Costco-Inspired Sales & Inventory Dashboard",
    page_icon="🏬",
    layout="wide",
)

# ------------------------------------------------------------
# Database connection
# ------------------------------------------------------------

# def get_db_config() -> Dict[str, Any]:
#     """Read database config from Streamlit secrets or environment variables.

#     For local pg_hba.conf trust authentication, password can be omitted or blank.
#     """
#     if "postgres" in st.secrets:
#         cfg = dict(st.secrets["postgres"])
#     else:
#         cfg = {
#             "host": os.getenv("PGHOST", "localhost"),
#             "port": os.getenv("PGPORT", "5432"),
#             "database": os.getenv("PGDATABASE", "zava"),
#             "user": os.getenv("PGUSER", "postgres"),
#             "password": os.getenv("PGPASSWORD", "Ana123meyu$"),
#         }
#     cfg.setdefault("host", "localhost")
#     cfg.setdefault("port", "5432")
#     cfg.setdefault("database", "zava")    # <--- CHANGE THIS to zava
#     cfg.setdefault("user", "postgres")    # <--- Corrected this from "zava" to "postgres"
#     cfg.setdefault("password", "Ana123meyu$") # <--- ADD YOUR PASSWORD HERE
#     return cfg

@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    cfg = get_db_config()
    user = quote_plus(str(cfg["user"]))
    password = str(cfg.get("password", ""))
    host = cfg["host"]
    port = cfg["port"]
    database = cfg["database"]
    if password:
        url = f"postgresql+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{database}"
    else:
        # Works when local PostgreSQL is configured with trust authentication.
        url = f"postgresql+psycopg2://{user}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True)

@st.cache_data(ttl=60, show_spinner=False)
def run_query(sql: str, params: Dict[str, Any] | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def test_connection() -> bool:
    try:
        run_query("SELECT 1 AS ok")
        return True
    except Exception as exc:
        st.error(f"Database connection failed: {exc}")
        return False

# ------------------------------------------------------------
# Helper queries for filters
# ------------------------------------------------------------

def load_filter_values():
    regions = run_query("SELECT DISTINCT region FROM costco_analytics.warehouse ORDER BY region")
    warehouses = run_query("SELECT warehouseid, name FROM costco_analytics.warehouse ORDER BY name")
    categories = run_query("SELECT categoryid, name FROM costco_analytics.category ORDER BY name")
    dates = run_query("SELECT MIN(transactiondate)::date AS min_date, MAX(transactiondate)::date AS max_date FROM costco_analytics.salestransaction")
    return regions, warehouses, categories, dates


def make_params(region, warehouse, category, start_date, end_date):
    return {
        "region": region,
        "warehouse": warehouse,
        "category": category,
        "start_date": start_date,
        "end_date": end_date,
    }

# ------------------------------------------------------------
# Business SQL queries
# ------------------------------------------------------------

CATEGORY_REVENUE_SQL = """
SELECT
    c.name AS category_name,
    c.deptcode AS department_code,
    ROUND(SUM(sti.subtotal)::numeric, 2) AS total_revenue,
    SUM(sti.quantity) AS total_units_sold,
    COUNT(DISTINCT st.transactionid) AS transaction_count
FROM costco_analytics.salestransactionitem sti
JOIN costco_analytics.product p ON sti.productid = p.productid
JOIN costco_analytics.category c ON p.categoryid = c.categoryid
JOIN costco_analytics.salestransaction st ON sti.transactionid = st.transactionid
JOIN costco_analytics.warehouse w ON st.warehouseid = w.warehouseid
WHERE (:region = 'All' OR w.region = :region)
  AND (:warehouse = 'All' OR w.name = :warehouse)
  AND (:category = 'All' OR c.name = :category)
  AND st.transactiondate::date BETWEEN :start_date AND :end_date
GROUP BY c.name, c.deptcode
ORDER BY total_revenue DESC;
"""

WAREHOUSE_PERFORMANCE_SQL = """
SELECT
    w.warehouseid,
    w.name AS warehouse_name,
    w.location,
    w.region,
    ROUND(COALESCE(SUM(st.totalamount), 0)::numeric, 2) AS total_revenue,
    COUNT(st.transactionid) AS transaction_count,
    RANK() OVER (
        PARTITION BY w.region
        ORDER BY COALESCE(SUM(st.totalamount), 0) DESC
    ) AS regional_rank
FROM costco_analytics.warehouse w
LEFT JOIN costco_analytics.salestransaction st ON w.warehouseid = st.warehouseid
WHERE (:region = 'All' OR w.region = :region)
  AND (:warehouse = 'All' OR w.name = :warehouse)
  -- This subquery checks if the transaction contains the filtered category 
  -- without duplicating the transaction row!
  AND (:category = 'All' OR st.transactionid IN (
        SELECT sti.transactionid 
        FROM costco_analytics.salestransactionitem sti
        JOIN costco_analytics.product p ON sti.productid = p.productid
        JOIN costco_analytics.category c ON p.categoryid = c.categoryid
        WHERE c.name = :category
      ))
  AND (st.transactiondate IS NULL OR st.transactiondate::date BETWEEN :start_date AND :end_date)
GROUP BY w.warehouseid, w.name, w.location, w.region
ORDER BY total_revenue DESC;
"""

LOW_INVENTORY_SQL = """
SELECT
    w.name AS warehouse_name,
    p.name AS product_name,
    i.stockquantity,
    i.reorderlevel,
    ps.leadtimedays,
    s.name AS supplier_name,
    CASE
        WHEN i.stockquantity = 0 THEN 'Out of Stock'
        WHEN i.stockquantity < i.reorderlevel THEN 'Restock Now'
        WHEN i.stockquantity <= i.reorderlevel + 5 THEN 'Monitor Closely'
        ELSE 'Healthy'
    END AS inventory_status
FROM costco_analytics.inventory i
JOIN costco_analytics.warehouse w ON i.warehouseid = w.warehouseid
JOIN costco_analytics.product p ON i.productid = p.productid
JOIN costco_analytics.category c ON p.categoryid = c.categoryid
LEFT JOIN costco_analytics.productsupplier ps ON p.productid = ps.productid
LEFT JOIN costco_analytics.supplier s ON ps.supplierid = s.supplierid
WHERE i.stockquantity <= i.reorderlevel + 5
  AND (:region = 'All' OR w.region = :region)
  AND (:warehouse = 'All' OR w.name = :warehouse)
  AND (:category = 'All' OR c.name = :category)
ORDER BY
    CASE
        WHEN i.stockquantity = 0 THEN 1
        WHEN i.stockquantity < i.reorderlevel THEN 2
        ELSE 3
    END,
    ps.leadtimedays DESC NULLS LAST;
"""

WAREHOUSE_CATEGORY_SQL = """
SELECT
    w.name AS warehouse_name,
    w.location,
    w.region,
    c.name AS category_name,
    ROUND(SUM(sti.subtotal)::numeric, 2) AS category_revenue,
    SUM(sti.quantity) AS units_sold,
    COUNT(DISTINCT st.transactionid) AS transaction_count
FROM costco_analytics.warehouse w
JOIN costco_analytics.salestransaction st ON w.warehouseid = st.warehouseid
JOIN costco_analytics.salestransactionitem sti ON st.transactionid = sti.transactionid
JOIN costco_analytics.product p ON sti.productid = p.productid
JOIN costco_analytics.category c ON p.categoryid = c.categoryid
WHERE (:region = 'All' OR w.region = :region)
  AND (:warehouse = 'All' OR w.name = :warehouse)
  AND (:category = 'All' OR c.name = :category)
  AND st.transactiondate::date BETWEEN :start_date AND :end_date
GROUP BY w.name, w.location, w.region, c.name
ORDER BY category_revenue ASC;
"""

PROMOTION_SQL = """
SELECT
    w.name AS warehouse_name,
    p.name AS product_name,
    i.stockquantity,
    i.reorderlevel,
    COALESCE(SUM(sti.quantity), 0) AS units_sold,
    CASE
        WHEN i.stockquantity > 50 AND COALESCE(SUM(sti.quantity), 0) < 5 
            THEN 'Overstock: Run Promotion'
        WHEN p.product_details::text ILIKE '%Winter%' AND i.stockquantity > i.reorderlevel 
            THEN 'Seasonal Clearance'
        ELSE 'Healthy Inventory'
    END AS promotion_recommendation
FROM costco_analytics.inventory i
JOIN costco_analytics.warehouse w ON i.warehouseid = w.warehouseid
JOIN costco_analytics.product p ON i.productid = p.productid
LEFT JOIN costco_analytics.salestransactionitem sti ON p.productid = sti.productid
LEFT JOIN costco_analytics.salestransaction st ON sti.transactionid = st.transactionid
    AND st.transactiondate::date BETWEEN :start_date AND :end_date
WHERE 
    (:region = 'All' OR w.region = :region) AND 
    (:warehouse = 'All' OR w.name = :warehouse) AND 
    (:category = 'All' OR p.categoryid IN (SELECT categoryid FROM costco_analytics.category WHERE name = :category))
GROUP BY w.name, p.name, i.stockquantity, i.reorderlevel, p.product_details
ORDER BY i.stockquantity DESC;
"""


# ------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------

def show_metrics(df: pd.DataFrame, metric_col: str, label_prefix: str):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(f"{label_prefix} Rows", len(df))
    with c2:
        if not df.empty and metric_col in df:
            st.metric("Total", f"{df[metric_col].sum():,.2f}")
        else:
            st.metric("Total", "0")
    with c3:
        if not df.empty and metric_col in df:
            st.metric("Highest", f"{df[metric_col].max():,.2f}")
        else:
            st.metric("Highest", "0")



def simple_insight(df: pd.DataFrame, name_col: str, value_col: str, subject: str):
    if df.empty or name_col not in df or value_col not in df:
        st.info("No records found for the selected filters.")
        return
    
    # Sort to find top and bottom
    df_sorted = df.sort_values(value_col, ascending=False)
    top = df_sorted.iloc[0]
    bottom = df_sorted.iloc[-1]
    
    if len(df) == 1:
        # Specialized message for a single result
        st.info(f"Business insight: At this filtered level, {top[name_col]} is the sole contributor with a value of {top[value_col]:,.2f}.")
    else:
        # Original message for multiple results
        st.info(
            f"Business insight: {top[name_col]} is the strongest {subject} in this view "
            f"({top[value_col]:,.2f}), while {bottom[name_col]} is the weakest "
            f"({bottom[value_col]:,.2f})."
        )


def display_table(df: pd.DataFrame):
    st.dataframe(df, use_container_width=True, hide_index=True)

# ------------------------------------------------------------
# Main app
# ------------------------------------------------------------

st.title("Costco-Inspired Sales & Inventory Insights System")
st.caption("Pre-AI Streamlit dashboard: SQL-driven metrics, tables, and visualizations.")


# Visual framing: make the AI assistant feel like the central copilot,
# while leaving actual AI/API logic for teammate integration.
st.markdown("""
<style>
.ai-callout {
    border: 1px solid #d7e8ff;
    background: linear-gradient(135deg, #f4f9ff 0%, #ffffff 100%);
    padding: 1rem 1.2rem;
    border-radius: 16px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.06);
    margin-bottom: 1rem;
}
.ai-callout h3 {
    margin-top: 0;
    margin-bottom: .35rem;
}
.ai-floating-note {
    position: fixed;
    right: 24px;
    bottom: 24px;
    z-index: 9999;
    max-width: 330px;
    background: #ffffff;
    border: 1px solid #d7e8ff;
    border-radius: 18px;
    padding: 14px 16px;
    box-shadow: 0 8px 28px rgba(0,0,0,0.16);
    font-size: 0.92rem;
}
.ai-floating-note strong {
    color: #0f4c81;
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Database")
    cfg = get_db_config()
    st.write(f"DB: `{cfg['database']}`")
    st.write(f"User: `{cfg['user']}`")
    st.write(f"Host: `{cfg['host']}:{cfg['port']}`")

if not test_connection():
    st.stop()

regions_df, warehouses_df, categories_df, dates_df = load_filter_values()
regions = ["All"] + regions_df["region"].dropna().tolist()
warehouses = ["All"] + warehouses_df["name"].dropna().tolist()
categories = ["All"] + categories_df["name"].dropna().tolist()

min_date = pd.to_datetime(dates_df.loc[0, "min_date"]).date()
max_date = pd.to_datetime(dates_df.loc[0, "max_date"]).date()

with st.sidebar:
    st.header("Filters")
    region = st.selectbox("Region", regions)
    warehouse = st.selectbox("Warehouse", warehouses)
    category = st.selectbox("Category", categories)
    start_date, end_date = st.date_input(
        "Transaction date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if start_date > end_date:
        st.error("Start date must be before end date.")
        st.stop()

params = make_params(region, warehouse, category, start_date, end_date)

tabs = st.tabs([
    "AI Copilot",
    "1. Category Winners",
    "2. Warehouse Battle",
    "3. Empty Shelf",
    "4. Hidden Failure",
    "5. Promotion Candidates",
])


with tabs[0]:
    st.subheader("AI Supply Chain Copilot")
    st.markdown(
        """
        <div class="ai-callout">
        <h3>Central AI Interaction Layer</h3>
        <p>Ask plain-English business questions. The AI will translate your request into SQL, query the <strong>zava</strong> database, and provide real-time insights.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    user_question = st.text_input(
        "Ask the AI Copilot a business question",
        placeholder="Example: Which warehouse-category combinations are underperforming?",
    )

    quick_questions = [
        "Which product categories generate the most revenue?",
        "Which warehouses are performing best or worst?",
        "Which products are below reorder level?",
        "Which warehouse-category combinations are underperforming?",
        "Which products may need promotional action?",
    ]
    st.caption("Suggested questions for the AI layer")
    st.write(" | ".join([f"`{q}`" for q in quick_questions]))

    # --- THE LIVE AI INTEGRATION ---
    if user_question:
        with st.spinner("AI is thinking and querying the database..."):
            # 1. Convert English to SQL
            generated_sql = get_ai_sql(user_question)
            
            # 2. Show the SQL for transparency (Great for your MSBA demo!)
            with st.expander("Show AI-Generated SQL"):
                st.code(generated_sql, language="sql")
            
            # 3. Execute the SQL
            try:
                # We use your friend's 'run_query' function
                df_result = run_query(generated_sql)

                if not df_result.empty:
                    st.success("Analysis Complete")
                    
                    # --- NEW: ADDING THE BUSINESS INSIGHT VOICE ---
                    with st.chat_message("assistant"):
                        # We ask Gemini to explain the data in "Easy English"
                        insight_prompt = f"""
                        You are a friendly business coach. Look at this data:
                        {df_result.to_string()}
                        
                        The user asked: "{user_question}"
                        
                        Write a 2-sentence 'Business Insight' in very simple, friendly English.
                        Explain WHAT happened and HOW to fix or improve it.
                        """
                        insight_model = genai.GenerativeModel('gemini-2.5-flash')
                        insight_response = insight_model.generate_content(insight_prompt)
                        st.write(f"**AI Insight:** {insight_response.text}")

                    # Layout results (Your existing Table and Chart)
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.write("#### Data View")
                        st.dataframe(df_result, hide_index=True)
                    
                    with c2:
                        st.write("#### AI Visualization")
                        str_cols = df_result.select_dtypes(include=['object']).columns
                        num_cols = df_result.select_dtypes(include=['number']).columns
                        
                        if len(num_cols) > 0 and len(str_cols) > 0:
                            fig = px.bar(df_result, x=str_cols[0], y=num_cols[0], 
                                         color=str_cols[0], template="plotly_white")
                            fig.update_yaxes(range=[0, df_result[num_cols[0]].max() * 1.2])
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("Results displayed in table format (No numeric data for charting).")
                else:
                    st.warning("No records found for that specific query.")
            
            except Exception as e:
                st.error(f"SQL Execution Error: {e}")

    st.divider()
    st.markdown("#### Hybrid Dashboard Overview")
    st.write(
        "This AI Copilot provides **unstructured** access to the entire schema. "
        "For **structured** monthly reports, please use the numbered tabs above."
    )

with tabs[1]:
    st.subheader("1. Which product categories generate the most revenue?")
    df = run_query(CATEGORY_REVENUE_SQL, params)
    show_metrics(df, "total_revenue", "Category")
    display_table(df)
    if not df.empty:
        fig = px.bar(df, x="category_name", y="total_revenue", title="Revenue by Category", text="total_revenue")
        # --Anagha
        # ADD THIS LINE to force the chart to start at 0
        fig.update_yaxes(range=[0, df["total_revenue"].max() * 1.1])
        #--
        st.plotly_chart(fig, use_container_width=True)
        fig2 = px.pie(df, names="category_name", values="total_revenue", title="Revenue Share by Category")
        st.plotly_chart(fig2, use_container_width=True)
        simple_insight(df, "category_name", "total_revenue", "category")

with tabs[2]:
    st.subheader("2. Which warehouses are performing best or worst?")
    df = run_query(WAREHOUSE_PERFORMANCE_SQL, params)
    show_metrics(df, "total_revenue", "Warehouse")
    display_table(df)
    if not df.empty:
        fig = px.bar(df, x="warehouse_name", y="total_revenue", color="region", title="Revenue by Warehouse", text="total_revenue")
        st.plotly_chart(fig, use_container_width=True)
        simple_insight(df, "warehouse_name", "total_revenue", "warehouse")

with tabs[3]:
    st.subheader("3. Which products are below reorder level?")
    df = run_query(LOW_INVENTORY_SQL, params)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Alerted Items", len(df))
    with c2:
        st.metric("Restock Now", int((df.get("inventory_status", pd.Series(dtype=str)) == "Restock Now").sum()))
    with c3:
        st.metric("Out of Stock", int((df.get("inventory_status", pd.Series(dtype=str)) == "Out of Stock").sum()))
    display_table(df)
    if not df.empty:
        chart_df = df.melt(
            id_vars=["warehouse_name", "product_name"],
            value_vars=["stockquantity", "reorderlevel"],
            var_name="metric",
            value_name="units",
        )
        fig = px.bar(chart_df, x="product_name", y="units", color="metric", barmode="group", title="Stock Quantity vs Reorder Level")
        st.plotly_chart(fig, use_container_width=True)
        st.warning("Items listed here are at or near reorder level and should be reviewed by inventory planners.")

with tabs[4]:
    st.subheader("4. Which warehouse-category combinations are underperforming?")
    df = run_query(WAREHOUSE_CATEGORY_SQL, params)
    show_metrics(df, "category_revenue", "Warehouse-Category")
    display_table(df)
    if not df.empty:
        df["warehouse_category"] = df["warehouse_name"] + " - " + df["category_name"]
        fig = px.bar(df, x="warehouse_category", y="category_revenue", color="region", title="Warehouse-Category Revenue", text="category_revenue")
        st.plotly_chart(fig, use_container_width=True)
        weakest = df.sort_values("category_revenue", ascending=True).iloc[0]
        st.info(
            f"Business insight: {weakest['warehouse_name']} / {weakest['category_name']} is the lowest-performing combination "
            f"in this view ({weakest['category_revenue']:,.2f})."
        )

with tabs[5]:
    st.subheader("5. Which products may need promotional action?")
    
    # PASSING THE PARAMS IS THE KEY TO STOPPING THE ERROR
    df = run_query(PROMOTION_SQL, params)
    show_metrics(df, "stockquantity", "Product")
    
    display_table(df)
    
    if not df.empty:
        fig = px.bar(
            df, 
            x="product_name", 
            y="stockquantity", 
            color="promotion_recommendation", 
            title="Promotion Candidates by Current Stock"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Filtering for candidates based on the labels created in SQL
        flagged = df[df["promotion_recommendation"] != "Healthy Inventory"]
        
        st.metric("Flagged Promotion Candidates", len(flagged))
        
        if not flagged.empty:
            st.warning("Some products are flagged for promotional review based on current stock, sales, and product details.")
        else:
            st.success("No immediate promotion candidates found under the current rule-based logic.")


with st.expander("Admin: Raw Database Inspector"):
    table_to_view = st.selectbox("Select a table to inspect raw data:", 
    ["warehouse", "product", "category", "inventory", "salestransaction", "salestransactionitem", "supplier", "productsupplier"])
    if table_to_view:
        raw_data = run_query(f"SELECT * FROM costco_analytics.{table_to_view} LIMIT 100")
        st.write(f"Showing last 100 records for: {table_to_view}")
        st.dataframe(raw_data)