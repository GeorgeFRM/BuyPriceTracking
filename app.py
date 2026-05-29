import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import re
from sqlalchemy import text

# Set up clean page configuration
st.set_page_config(
    page_title="Institutional Watchlist Tracker",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Stock Target Monitor & Execution Dashboard")
st.markdown("Dynamic execution platform. Sandbox environment powered by a Cloud PostgreSQL Database Connection layer.")

# --- NEW: PRODUCTION-GRADE SQL ENGINE CONNECTION ---
# Leverages Streamlit's native relational SQL driver (Zero local machine footprint)
try:
    conn = st.connection("supabase_db", type="sql", driver="psycopg2")
except Exception as e:
    st.error(f"Critical System Fault: Unable to bind secure cloud data pipeline. Verify secrets. {e}")
    st.stop()

def fetch_watchlist_from_db():
    """Queries the centralized SQL database for tracked assets."""
    try:
        df = conn.query("SELECT ticker, buy_price AS \"Buy Price\", sell_price AS \"Sell Price\", last_updated AS \"Last Updated\" FROM watchlist;", ttl=0)
        if df is not None and not df.empty:
            df["Ticker"] = df["Ticker"].astype(str).str.upper()
            df["Buy Price"] = df["Buy Price"].astype(float)
            df["Sell Price"] = df["Sell Price"].astype(float)
            df["Last Updated"] = df["Last Updated"].fillna("").astype(str)
            return df
    except Exception as e:
        st.error(f"Database Read Fault: {e}")
    return pd.DataFrame(columns=["Ticker", "Buy Price", "Sell Price", "Last Updated"])

# --- SESSION STATE INITIALIZATION ---
if 'market_cache' not in st.session_state:
    st.session_state.market_cache = {}
if 'cache_timestamp' not in st.session_state:
    st.session_state.cache_timestamp = None

# Pull fresh core dataframe straight from the network SQL layer
raw_portfolio_df = fetch_watchlist_from_db()

# --- SIDEBAR: USER INTERACTION PANEL ---
with st.sidebar:
    st.header("📋 Data Management")
    
    st.subheader("➕ Add Single Asset")
    with st.form("single_ticker_form", clear_on_submit=True):
        new_ticker = st.text_input("Ticker Symbol (e.g., AAPL)").strip().upper()
        new_buy = st.number_input("Buy Target Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_sell = st.number_input("Sell Profit Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_updated = st.text_input("Last Updated (yyyy/mm/dd)", placeholder="2026/05/29")
        submit_button = st.form_submit_button("Add to Watchlist")
        
        if submit_button:
            if not new_ticker or not re.match(r'^[A-Z0-9\.\-=]{1,10}$', new_ticker) or new_buy <= 0 or new_sell <= 0:
                st.error("Invalid Input Data: Ensure ticker follows standard asset naming constraints.")
            else:
                clean_date = re.sub(r'[^0-9/:-]', '', new_updated).strip()
                try:
                    with conn.session as session:
                        # SQL UPSERT: Inserts new asset or updates pricing if ticker exists
                        session.execute(
                            """
                            INSERT INTO watchlist (ticker, buy_price, sell_price, last_updated) 
                            VALUES (:tk, :buy, :sell, :dt)
                            ON CONFLICT (ticker) 
                            DO UPDATE SET buy_price = EXCLUDED.buy_price, sell_price = EXCLUDED.sell_price, last_updated = EXCLUDED.last_updated;
                            """,
                            {"tk": new_ticker, "buy": float(new_buy), "sell": float(new_sell), "dt": clean_date}
                        )
                        session.commit()
                    st.success(f"Added/Updated {new_ticker} successfully inside Cloud Database!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Write aborted by cloud security rules: {e}")

    st.write("---")
    st.header("⚙️ Settings & System")
    
    if st.button("🗑️ Clear Entire Database Portfolio", use_container_width=True):
        try:
            with conn.session as session:
                session.execute(text("TRUNCATE TABLE watchlist;"))
                session.commit()
            st.session_state.market_cache = {}
            st.session_state.cache_timestamp = None
            st.cache_data.clear()
            st.success("Cloud database successfully cleared!")
            st.rerun()
        except Exception as e:
            st.error(f"Flush sequence denied: {e}")
        
    if st.button("🔄 Force Refresh Market Data", use_container_width=True):
        st.session_state.cache_timestamp = None
        st.cache_data.clear()
        st.rerun()

# --- ONE-TIME EXCEL INITIALIZATION SEED ---
if raw_portfolio_df.empty:
    uploaded_file = st.file_uploader("Drag and drop your 600+ asset watchlist Excel file here to initialize database tables", type=["xlsx"], key="excel_uploader")

    if uploaded_file is not None:
        try:
            raw_df = pd.read_excel(uploaded_file)
            raw_df.columns = [str(col).strip().title() for col in raw_df.columns]
            
            required_cols = ['Ticker', 'Buy Price', 'Sell Price', 'Last Updated']
            if not all(col in raw_df.columns for col in required_cols):
                st.error(f"Mapping Error: Spreadsheet must contain these exact columns: {required_cols}")
            else:
                with conn.session as session:
                    # Clear any hanging records before bulk execution
                    session.execute(text("TRUNCATE TABLE watchlist;"))
                    
                    for _, row in raw_df.iterrows():
                        dt = row['Last Updated']
                        formatted_date = dt.strftime("%Y/%m/%d") if pd.notna(dt) and hasattr(dt, 'strftime') else str(dt).strip() if pd.notna(dt) else ""
                        clean_tick = str(row['Ticker']).strip().upper()
                        
                        if re.match(r'^[A-Z0-9\.\-=]{1,10}$', clean_tick):
                            session.execute(text(
                                "INSERT INTO watchlist (ticker, buy_price, sell_price, last_updated) VALUES (:tk, :buy, :sell, :dt);",
                                {
                                    "tk": clean_tick, 
                                    "buy": float(row['Buy Price']), 
                                    "sell": float(row['Sell Price']), 
                                    "dt": re.sub(r'[^0-9/:-]', '', formatted_date).strip()
                                }
                            ))
                    session.commit()
                st.success("Cloud Database successfully populated from spreadsheet parsing array!")
                st.rerun()
        except Exception as e:
            st.error(f"Error compiling Excel matrix into database statements: {e}")

# --- HIGH-SPEED SAFE BATCH DOWNLOADER ---
@st.cache_data(ttl=86400)
def fetch_daily_market_snapshots(tickers_tuple):
    market_snapshots = {}
    if not tickers_tuple:
        return market_snapshots
        
    try:
        data = yf.download(list(tickers_tuple), period="2y", group_by='ticker', progress=False)
        
        for ticker in tickers_tuple:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker in data.columns.levels[0]:
                        hist = data[ticker].dropna(subset=['Close'])
                    else:
                        continue
                else:
                    hist = data.dropna(subset=['Close'])
                
                if not hist.empty:
                    current_price = round(float(hist['Close'].iloc[-1]), 2)
                    price_90d_ago = round(float(hist['Close'].iloc[-64]), 2) if len(hist) >= 64 else round(float(hist['Close'].iloc[0]), 2)
                    price_1w_ago = round(float(hist['Close'].iloc[-6]), 2) if len(hist) >= 6 else round(float(hist['Close'].iloc[0]), 2)
                    
                    market_snapshots[ticker] = {
                        "current_price": current_price,
                        "historical_closes": [round(float(x), 2) for x in hist['Close'].iloc[::-1].tolist()],
                        "price_1w_ago": price_1w_ago,
                        "price_90d_ago": price_90d_ago
                    }
            except Exception:
                pass 
    except Exception as e:
        st.error(f"Failed to fetch market batch update: {e}")
        
    return market_snapshots

# --- APPLICATION LOGIC ---
if not raw_portfolio_df.empty:
    active_tickers = tuple(raw_portfolio_df['Ticker'].unique())
    
    # Check Level-2 Memory Caching layer (8 hours)
    now = datetime.datetime.now()
    if (st.session_state.cache_timestamp and 
        (now - st.session_state.cache_timestamp).total_seconds() < 28800 and 
        st.session_state.market_cache):
        daily_data = st.session_state.market_cache
    else:
        daily_data = fetch_daily_market_snapshots(active_tickers)
        st.session_state.market_cache = daily_data
        st.session_state.cache_timestamp = now
    
    processed_data, top_drops_data, macro_drops_data = [], [], []
    buy_alerts, sell_alerts = 0, 0
    
    for _, row in raw_portfolio_df.iterrows():
        ticker, buy_target, sell_target, last_updated = row['Ticker'], row['Buy Price'], row['Sell Price'], row['Last Updated']
        
        if ticker in daily_data and daily_data[ticker]:
            current_price = daily_data[ticker]["current_price"]
            closes_backward = daily_data[ticker]["historical_closes"]
            
            p_1w = daily_data[ticker]["price_1w_ago"]
            p_90d = daily_data[ticker]["price_90d_ago"]
            
            weekly_perf = ((current_price - p_1w) / p_1w) * 100 if p_1w > 0 else 0.0
            macro_perf = ((current_price - p_90d) / p_90d) * 100 if p_90d > 0 else 0.0
            
            days_below = 0
            if current_price <= buy_target:
                status = "Buy"
                buy_alerts += 1
                for p in closes_backward:
                    if p <= buy_target: days_below += 1
                    else: break
                days_display = int(days_below)
            elif current_price >= sell_target:
                status, days_display = "Profit Zone", None
                sell_alerts += 1
            else:
                status, days_display = "Hold / Monitor", None
                
            top_drops_data.append({
                "Ticker": ticker, "Buy Price": buy_target, "Current Market": current_price, 
                "Weekly Change %": weekly_perf, "Last Updated": last_updated
            })
            
            macro_drops_data.append({
                "Ticker": ticker, "Buy Price": buy_target, "Current Market": current_price, 
                "90-Day Decline": macro_perf, "Last Updated": last_updated
            })
        else:
            current_price, status, days_display = 0.0, "Data Offline", None
            
        processed_data.append({
            "Ticker": ticker, "Buy Price": buy_target, "Current Market": current_price,
            "Sell Price": sell_target, "Status": status, "Days Below Buy Target": days_display, "Last Updated": last_updated
        })
        
    df_results = pd.DataFrame(processed_data)
    
    if not df_results.empty:
        df_results = df_results.iloc[
            df_results['Days Below Buy Target'].fillna(-1).sort_values(ascending=False).index
        ].reset_index(drop=True)
        
    if top_drops_data:
        df_all_drops = pd.DataFrame(top_drops_data)
        df_top_10_drops = df_all_drops[df_all_drops['Weekly Change %'] <= -10.0].sort_values(by="Weekly Change %").head(10)
    else:
        df_top_10_drops = pd.DataFrame(columns=["Ticker", "Buy Price", "Current Market", "Weekly Change %", "Last Updated"])

    if macro_drops_data:
        df_all_macro = pd.DataFrame(macro_drops_data)
        df_top_90d_drops = df_all_macro[df_all_macro['90-Day Decline'] <= -25.0].sort_values(by="90-Day Decline").head(25)
    else:
        df_top_90d_drops = pd.DataFrame(columns=["Ticker", "Buy Price", "Current Market", "90-Day Decline", "Last Updated"])

    # KPI Layout Ribbon Panel
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Assets Tracked", len(df_results))
    with col2:
        st.metric("Buy Targets Triggered", buy_alerts)
    with col3:
        st.metric("Profit Horizons Reached", sell_alerts)
    st.write("---")
    
    # --- TABULAR FOCUS CONSOLE ---
    st.subheader("📉 Structural Market Drawdown Anomalies")
    tab1, tab2 = st.tabs(["⚠️ Declines of 25% or More (Trailing 90 Days)", "⏱️ Top Weekly Declines (Worse than -10%)"])
    
    with tab1:
        if not df_top_90d_drops.empty:
            st.dataframe(df_top_90d_drops.style.format({
                "Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "90-Day Decline": "{:+.2f}%"
            }), use_container_width=True, hide_index=True, height=280)
        else:
            st.info("No tracking assets have declined by 25% or more over the trailing 90 days.")
            
    with tab2:
        if not df_top_10_drops.empty:
            st.dataframe(df_top_10_drops.style.format({
                "Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "Weekly Change %": "{:+.2f}%"
            }), use_container_width=True, hide_index=True, height=280)
        else:
            st.info("No tracking assets have declined by more than 10% over the trailing week.")

    st.write("---")
    
    # --- MAIN WATCHLIST GRID WITH CONDITIONAL COLOR MATRIX ---
    def style_matrix_rows(row):
        if row['Status'] == "Buy":
            return ['background-color: rgba(46, 204, 113, 0.14); color: #2ecc71; font-weight: bold;'] * len(row)
        elif row['Status'] == "Profit Zone":
            return ['background-color: rgba(41, 128, 185, 0.12); color: #3498db; font-weight: bold;'] * len(row)
        elif row['Status'] == "Data Offline":
            return ['color: #7f8c8d; font-style: italic;'] * len(row)
        return [''] * len(row)

    styled_df = df_results.style.format({"Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "Sell Price": "${:,.2f}"}).apply(
        style_matrix_rows, axis=1
    )
    
    st.subheader("📊 Live Watchlist Execution Grid")
    response_editor = st.data_editor(
        styled_df,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", disabled=True, width="medium"), 
            "Buy Price": st.column_config.NumberColumn("Buy Price (Edit)", min_value=0.0, format="$%.2f", width="medium"),
            "Current Market": st.column_config.NumberColumn("Current Market", disabled=True, format="$%.2f", width="medium"),
            "Sell Price": st.column_config.NumberColumn("Sell Price (Edit)", min_value=0.0, format="$%.2f", width="medium"),
            "Status": st.column_config.TextColumn("Status", disabled=True, width="medium"),
            "Days Below Buy Target": st.column_config.NumberColumn("Streak", disabled=True, format="%d days", width="small"),
            "Last Updated": st.column_config.TextColumn("Last Updated")
        },
        use_container_width=True, hide_index=False, num_rows="dynamic", key="unified_portfolio_editor"
    )
    
    # Grid Synchronizer SQL Writer Logic
    grid_state = st.session_state.unified_portfolio_editor
    has_changed = False
    
    if grid_state.get("deleted_rows"):
        deleted_tickers = df_results.iloc[grid_state["deleted_rows"]]['Ticker'].tolist()
        try:
            with conn.session as session:
                for tk in deleted_tickers:
                    session.execute("DELETE FROM watchlist WHERE ticker = :tk;", {"tk": tk})
                session.commit()
            has_changed = True
        except Exception as e:
            st.error(f"Write back rejected by remote server: {e}")
            
    elif grid_state.get("edited_rows"):
        try:
            with conn.session as session:
                for str_idx, changes in grid_state["edited_rows"].items():
                    idx = int(str_idx)
                    if idx < len(df_results):
                        target_ticker = df_results.at[idx, 'Ticker']
                        
                        # Map out edits dynamically and parse down parameterized UPDATE queries
                        if "Buy Price" in changes:
                            session.execute("UPDATE watchlist SET buy_price = :val WHERE ticker = :tk;", {"val": float(changes["Buy Price"]), "tk": target_ticker})
                        if "Sell Price" in changes:
                            session.execute("UPDATE watchlist SET sell_price = :val WHERE ticker = :tk;", {"val": float(changes["Sell Price"]), "tk": target_ticker})
                        if "Last Updated" in changes:
                            session.execute("UPDATE watchlist SET last_updated = :val WHERE ticker = :tk;", {"val": str(changes["Last Updated"]).strip(), "tk": target_ticker})
                session.commit()
            has_changed = True
        except Exception as e:
            st.error(f"Data mutation execution failed on remote server: {e}")
                
    if has_changed:
        st.rerun()
else:
    st.info("💡 App database is currently empty. Drag and drop your asset watchlist Excel file above to initialize data.")
