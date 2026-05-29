import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import re
from sqlalchemy import text

# --- SYSTEM STAGE CONFIGURATION ---
st.set_page_config(
    page_title="Institutional Watchlist Tracker",
    page_icon="📈",
    layout="wide"
)

st.title("Watchlist Tracker")

# --- PRODUCTION-GRADE SQL ENGINE CONNECTION ---
try:
    conn = st.connection("supabase_db", type="sql", driver="psycopg2")
except Exception as e:
    st.error(f"Critical System Fault: Unable to bind secure cloud data pipeline. Verify secrets. {e}")
    st.stop()

def fetch_watchlist_from_db():
    """Queries the centralized SQL database for tracked assets."""
    try:
        # Pull core metrics including the customized Group field mapping
        df = conn.query('SELECT "Ticker", "Buy Price", "Sell Price", "Last Updated", "Group" FROM watchlist;', ttl=0)
        if df is not None and not df.empty:
            df["Ticker"] = df["Ticker"].astype(str).str.upper()
            df["Buy Price"] = df["Buy Price"].astype(float)
            df["Sell Price"] = df["Sell Price"].astype(float)
            df["Last Updated"] = df["Last Updated"].fillna("").astype(str)
            df["Group"] = df["Group"].fillna("Wishlist").astype(str).str.strip()
            return df
    except Exception as e:
        st.error(f"Database Read Fault: {e}")
    return pd.DataFrame(columns=["Ticker", "Buy Price", "Sell Price", "Last Updated", "Group"])

# --- SESSION STATE INITIALIZATION ---
if 'market_cache' not in st.session_state:
    st.session_state.market_cache = {}
if 'cache_timestamp' not in st.session_state:
    st.session_state.cache_timestamp = None

# Pull fresh core data straight from the network SQL layer on frame refresh
raw_portfolio_df = fetch_watchlist_from_db()

# --- SIDEBAR: INTERACTION CONSOLE ---
with st.sidebar:
    st.header("📋 Data Management")
    
    st.subheader("➕ Add Single Asset")
    with st.form("single_ticker_form", clear_on_submit=True):
        new_ticker = st.text_input("Ticker Symbol (e.g., AAPL)").strip().upper()
        new_buy = st.number_input("Buy Target Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_sell = st.number_input("Sell Profit Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_updated = st.text_input("Last Updated (yyyy/mm/dd)", placeholder=datetime.date.today().strftime("%Y/%m/%d"))
        
        # Group Dropdown selector utilizing your explicit operational categories
        new_group = st.selectbox("Strategic Group Category", ["Target", "Holding", "Wishlist"])
        
        submit_button = st.form_submit_button("Add to Watchlist")
        
        if submit_button:
            if not new_ticker or not re.match(r'^[A-Z0-9\.\-=]{1,10}$', new_ticker) or new_buy <= 0 or new_sell <= 0:
                st.error("Invalid Input Data: Ensure ticker follows standard asset naming constraints.")
            else:
                clean_date = re.sub(r'[^0-9/:-]', '', new_updated).strip()
                if not clean_date:
                    clean_date = datetime.date.today().strftime("%Y/%m/%d")
                try:
                    with conn.session as session:
                        # SQL UPSERT: Inserts new asset or updates data if ticker already exists
                        session.execute(
                            text("""
                            INSERT INTO watchlist (ticker, buy_price, sell_price, last_updated, "group") 
                            VALUES (:tk, :buy, :sell, :dt, :gp)
                            ON CONFLICT (ticker) 
                            DO UPDATE SET buy_price = EXCLUDED.buy_price, sell_price = EXCLUDED.sell_price, last_updated = EXCLUDED.last_updated, "group" = EXCLUDED."group";
                            """),
                            {"tk": new_ticker, "buy": float(new_buy), "sell": float(new_sell), "dt": clean_date, "gp": new_group}
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
                session.execute(text("DELETE FROM watchlist;"))
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
        ticker, buy_target, sell_target, last_updated, group_cat = row['Ticker'], row['Buy Price'], row['Sell Price'], row['Last Updated'], row['Group']
        
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
                "Ticker": ticker, "Group": group_cat, "Buy Price": buy_target, "Current Market": current_price, 
                "Weekly Change %": weekly_perf, "Last Updated": last_updated
            })
            
            macro_drops_data.append({
                "Ticker": ticker, "Group": group_cat, "Buy Price": buy_target, "Current Market": current_price, 
                "90-Day Decline": macro_perf, "Last Updated": last_updated
            })
        else:
            current_price, status, days_display = 0.0, "Data Offline", None
            
        processed_data.append({
            "Ticker": ticker, "Group": group_cat, "Buy Price": buy_target, "Current Market": current_price,
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
        df_top_10_drops = pd.DataFrame(columns=["Ticker", "Group", "Buy Price", "Current Market", "Weekly Change %", "Last Updated"])

    if macro_drops_data:
        df_all_macro = pd.DataFrame(macro_drops_data)
        df_top_90d_drops = df_all_macro[df_all_macro['90-Day Decline'] <= -25.0].sort_values(by="90-Day Decline").head(25)
    else:
        df_top_90d_drops = pd.DataFrame(columns=["Ticker", "Group", "Buy Price", "Current Market", "90-Day Decline", "Last Updated"])

    # KPI Layout Ribbon Panel
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Assets Tracked", len(df_results))
    with col2:
        st.metric("Buy Targets Triggered", buy_alerts)
    with col3:
        st.metric("Profit Horizons Reached", sell_alerts)
    st.write("---")

# --- SECTION 0: HOLDING (Side-by-Side Execution Zones) ---
    st.markdown("### Holding Group At or Near Targets")
    df_holding = df_results[df_results["Group"] == "Holding"].copy()
    col_h1, col_h2 = st.columns(2)

    with col_h1:
        st.caption("Buy Zone (Below Buy Price or < 5% Over)")
        buy_zone = df_holding[df_holding["Current Market"] <= (df_holding["Buy Price"] * 1.05)].copy()
        
        # Calculate distance to Buy for sorting (Negative = better/more urgent)
        buy_zone["Distance"] = buy_zone["Current Market"] - buy_zone["Buy Price"]
        buy_zone = buy_zone.sort_values(by="Distance")
        
        buy_zone["Action"] = buy_zone.apply(
            lambda x: "Buy" if x["Current Market"] <= x["Buy Price"] 
            else f"{((x['Current Market']/x['Buy Price'])-1)*100:.1f}% above our Buy", axis=1
        )
        if not buy_zone.empty:
            # Set height to 200px and hide unnecessary index
            st.dataframe(buy_zone[["Ticker", "Current Market", "Buy Price", "Action"]], 
                         use_container_width=True, hide_index=True, height=200)
        else:
            st.info("No Holding assets in Buy zone.")

    with col_h2:
        st.caption("Sell Zone (Above Sell Price or Below by <5% Under)")
        profit_zone = df_holding[df_holding["Current Market"] >= (df_holding["Sell Price"] * 0.95)].copy()
        
        # Calculate distance to Sell for sorting (Closer to/Over Sell = more urgent)
        profit_zone["Distance"] = profit_zone["Sell Price"] - profit_zone["Current Market"]
        profit_zone = profit_zone.sort_values(by="Distance")
        
        profit_zone["Status"] = profit_zone.apply(
            lambda x: "Sell" if x["Current Market"] >= x["Sell Price"] 
            else f"{((1-(x['Current Market']/x['Sell Price'])))*100:.1f}% below Sell", axis=1
        )
        if not profit_zone.empty:
            st.dataframe(profit_zone[["Ticker", "Current Market", "Sell Price", "Status"]], 
                         use_container_width=True, hide_index=True, height=200)
        else:
            st.info("No Holding assets in Sell zone.")
    st.write("---")
    
   # --- SPLIT FOCUS CONSOLE: WISHLIST VS TARGET ---
    st.subheader("Market Anomalies by Portfolio Group")

    # Filter dataframes for specific groups
    df_wishlist = df_results[df_results["Group"] == "Wishlist"]
    df_target = df_results[df_results["Group"] == "Target"]

    # --- SECTION 1: WISHLIST (Side-by-Side Anomalies) ---
    st.markdown("### Wishlist Group Standouts")
    col_w1, col_w2 = st.columns(2)
    
    with col_w1:
        st.caption("Declines of 25%+ (90 Days)")
        wish_macro = df_top_90d_drops[df_top_90d_drops["Ticker"].isin(df_wishlist["Ticker"])]
        if not wish_macro.empty:
            st.dataframe(wish_macro.style.format({"Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "90-Day Decline": "{:+.2f}%"}), use_container_width=True, hide_index=True, height=200)
        else:
            st.info("No Wishlist assets meet criteria.")

    with col_w2:
        st.caption("Weekly Declines (Worse than -10%)")
        wish_weekly = df_top_10_drops[df_top_10_drops["Ticker"].isin(df_wishlist["Ticker"])]
        if not wish_weekly.empty:
            st.dataframe(wish_weekly.style.format({"Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "Weekly Change %": "{:+.2f}%"}), use_container_width=True, hide_index=True, height=200)
        else:
            st.info("No Wishlist assets meet criteria.")

    st.write("---")

    # --- SECTION 2: TARGET (Side-by-Side Anomalies) ---
    st.markdown("### Target Group Standouts")
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        st.caption("Declines of 25%+ (90 Days)")
        target_macro = df_top_90d_drops[df_top_90d_drops["Ticker"].isin(df_target["Ticker"])]
        if not target_macro.empty:
            st.dataframe(target_macro.style.format({"Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "90-Day Decline": "{:+.2f}%"}), use_container_width=True, hide_index=True, height=200)
        else:
            st.info("No Target assets meet criteria.")

    with col_t2:
        st.caption("Weekly Declines (Worse than -10%)")
        target_weekly = df_top_10_drops[df_top_10_drops["Ticker"].isin(df_target["Ticker"])]
        if not target_weekly.empty:
            st.dataframe(target_weekly.style.format({"Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "Weekly Change %": "{:+.2f}%"}), use_container_width=True, hide_index=True, height=200)
        else:
            st.info("No Target assets meet criteria.")
    
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
            "Ticker": st.column_config.TextColumn("Ticker", disabled=True, width="small"), 
            "Group": st.column_config.SelectboxColumn("Group (Edit)", options=["Target", "Holding", "Wishlist"], required=True, width="medium"),
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
                    # Enforce double quotes around "Ticker"
                    session.execute(text('DELETE FROM watchlist WHERE "Ticker" = :tk;'), {"tk": tk})
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
                        
                        # Enforce exact database column name casing in the UPDATE blocks
                        if "Buy Price" in changes:
                            session.execute(text('UPDATE watchlist SET "Buy Price" = :val WHERE "Ticker" = :tk;'), {"val": float(changes["Buy Price"]), "tk": target_ticker})
                        if "Sell Price" in changes:
                            session.execute(text('UPDATE watchlist SET "Sell Price" = :val WHERE "Ticker" = :tk;'), {"val": float(changes["Sell Price"]), "tk": target_ticker})
                        if "Last Updated" in changes:
                            session.execute(text('UPDATE watchlist SET "Last Updated" = :val WHERE "Ticker" = :tk;'), {"val": str(changes["Last Updated"]).strip(), "tk": target_ticker})
                        if "Group" in changes:
                            session.execute(text('UPDATE watchlist SET "Group" = :val WHERE "Ticker" = :tk;'), {"val": str(changes["Group"]).strip(), "tk": target_ticker})
                session.commit()
            has_changed = True
        except Exception as e:
            st.error(f"Data mutation execution failed on remote server: {e}")
                
    if has_changed:
        st.rerun()
else:
    st.info("💡 App database is currently empty. Use the Supabase dashboard or the sidebar form panel to seed tickers.")
