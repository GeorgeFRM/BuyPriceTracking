import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import re
from sqlalchemy import text

# --- SYSTEM CONFIGURATION ---
st.set_page_config(
    page_title="Institutional Watchlist Tracker",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Watchlist Tracker")

# --- DATABASE CONNECTION ---
try:
    conn = st.connection("supabase_db", type="sql", driver="psycopg2")
except Exception as e:
    st.error(f"Database Connection Error: Verify your secrets config. Details: {e}")
    st.stop()

def fetch_watchlist_from_db():
    """Queries the centralized SQL database for tracked assets."""
    try:
        df = conn.query('SELECT "Ticker", "Buy Price", "Sell Price", "Last Updated", "Group" FROM watchlist;', ttl=0)
        if df is not None and not df.empty:
            df["Ticker"] = df["Ticker"].astype(str).str.upper()
            df["Buy Price"] = df["Buy Price"].astype(float)
            df["Sell Price"] = df["Sell Price"].astype(float)
            df["Last Updated"] = df["Last Updated"].fillna("").astype(str)
            df["Group"] = df["Group"].fillna("Wishlist").astype(str).str.strip()
            return df
    except Exception as e:
        st.error(f"Database Read Error: {e}")
    return pd.DataFrame(columns=["Ticker", "Buy Price", "Sell Price", "Last Updated", "Group"])

def get_table_height(df, max_height=400):
    """Dynamically calculates table height to eliminate unnecessary scrolling for short datasets."""
    if df.empty:
        return 100
    calculated_height = (len(df) * 35) + 45
    return min(calculated_height, max_height)

# --- SESSION STATE INITIALIZATION ---
if 'market_cache' not in st.session_state:
    st.session_state.market_cache = {}
if 'cache_timestamp' not in st.session_state:
    st.session_state.cache_timestamp = None

# Fresh pull from database on refresh
raw_portfolio_df = fetch_watchlist_from_db()

# --- SIDEBAR: INTERACTION CONSOLE ---
with st.sidebar:
    st.header("📋 Data Management")
    
    st.subheader("➕ Add Single Asset")
    with st.form("single_ticker_form", clear_on_submit=True):
        new_ticker = st.text_input("Ticker Symbol (e.g., AAPL)").strip().upper()
        new_buy = st.number_input("Buy Target Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_sell = st.number_input("Sell Profit Price ($)", min_value=0.0, step=0.01, format="%.2f")
        
        new_updated_date = st.date_input("Last Updated", datetime.date.today())
        new_group = st.selectbox("Strategic Group Category", ["Target", "Holding", "Wishlist"])
        
        submit_button = st.form_submit_button("Add to Watchlist", use_container_width=True)
        
        if submit_button:
            if not new_ticker or not re.match(r'^[A-Z0-9\.\-=]{1,10}$', new_ticker) or new_buy <= 0 or new_sell <= 0:
                st.error("Invalid Input: Verify asset constraints and pricing data.")
            else:
                clean_date = new_updated_date.strftime("%Y/%m/%d")
                try:
                    with conn.session as session:
                        session.execute(
                            text("""
                            INSERT INTO watchlist ("Ticker", "Buy Price", "Sell Price", "Last Updated", "Group") 
                            VALUES (:tk, :buy, :sell, :dt, :gp)
                            ON CONFLICT ("Ticker") 
                            DO UPDATE SET "Buy Price" = EXCLUDED."Buy Price", "Sell Price" = EXCLUDED."Sell Price", "Last Updated" = EXCLUDED."Last Updated", "Group" = EXCLUDED."Group";
                            """),
                            {"tk": new_ticker, "buy": float(new_buy), "sell": float(new_sell), "dt": clean_date, "gp": new_group}
                        )
                        session.commit()
                    st.success(f"Successfully processed {new_ticker}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Database Write Denied: {e}")

    st.write("---")
    st.header("⚙️ System Control")
    
    if st.button("Clear Entire Portfolio", use_container_width=True, type="secondary"):
        try:
            with conn.session as session:
                session.execute(text("DELETE FROM watchlist;"))
                session.commit()
            st.session_state.market_cache = {}
            st.session_state.cache_timestamp = None
            st.cache_data.clear()
            st.success("Watchlist database cleared!")
            st.rerun()
        except Exception as e:
            st.error(f"Flush sequence denied: {e}")
        
    if st.button("Force Refresh Market Data", use_container_width=True, type="primary"):
        st.session_state.cache_timestamp = None
        st.cache_data.clear()
        st.rerun()

# --- MARKET DATA DOWNLOADER ---
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
        st.error(f"Failed to fetch market metrics from Yahoo Finance: {e}")
        
    return market_snapshots

# --- MAIN APPLICATION LOGIC ---
if not raw_portfolio_df.empty:
    active_tickers = tuple(raw_portfolio_df['Ticker'].unique())
    
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
                status = "Buy Zone"
                buy_alerts += 1
                for p in closes_backward:
                    if p <= buy_target: days_below += 1
                    else: break
                days_display = int(days_below)
            elif current_price >= sell_target:
                status = "Sell Zone"
                sell_alerts += 1
                days_display = None
            else:
                status = "Hold / Monitor"
                days_display = None
                
            top_drops_data.append({
                "Ticker": ticker, "Group": group_cat, "Buy Price": buy_target, "Current Market": current_price, 
                "Weekly Change %": weekly_perf, "Last Updated": last_updated
            })
            
            macro_drops_data.append({
                "Ticker": ticker, "Group": group_cat, "Buy Price": buy_target, "Current Market": current_price, 
                "90-Day Decline": macro_perf, "Last Updated": last_updated
            })
        else:
            current_price, status, days_display = 0.0, "Offline", None
            
        processed_data.append({
            "Ticker": ticker, "Group": group_cat, "Buy Price": buy_target, "Current Market": current_price,
            "Sell Price": sell_target, "Status": status, "Days Below Buy Target": days_display, "Last Updated": last_updated
        })
        
    df_results = pd.DataFrame(processed_data)
        
    df_top_10_drops = pd.DataFrame(top_drops_data) if top_drops_data else pd.DataFrame()
    if not df_top_10_drops.empty:
        df_top_10_drops = df_top_10_drops[df_top_10_drops['Weekly Change %'] <= -10.0].sort_values(by="Weekly Change %").head(10)
        
    df_top_90d_drops = pd.DataFrame(macro_drops_data) if macro_drops_data else pd.DataFrame()
    if not df_top_90d_drops.empty:
        df_top_90d_drops = df_top_90d_drops[df_top_90d_drops['90-Day Decline'] <= -25.0].sort_values(by="90-Day Decline").head(25)

    # --- KPI HEADER RIBBON ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Assets Tracked", len(df_results))
    with col2:
        st.metric("Buy Targets Triggered", buy_alerts, delta=f"{buy_alerts} Active" if buy_alerts > 0 else None, delta_color="inverse")
    with col3:
        st.metric("Profit Horizons Reached", sell_alerts, delta=f"{sell_alerts} Active" if sell_alerts > 0 else None)
        
    st.write("---")

    # --- TABBED INTERFACE ---
    tab1, tab2, tab3 = st.tabs(["📊 Live Watchlist Grid", "🚨 Target Execution Zones", "📉 Portfolio Anomalies"])

    with tab1:
        st.subheader("Unified Execution Engine")
        
        # Format display status values
        df_results_viz = df_results.copy()
        def get_clean_status(status):
            if "Buy" in status: return "Buy Zone"
            if "Sell" in status: return "Sell Zone"
            return "Hold / Monitor"
        df_results_viz["Status"] = df_results_viz["Status"].apply(get_clean_status)

        # --- PROGRAMMATIC SORT ENGINE CONTROLLERS ---
        col_sort1, col_sort2 = st.columns([2, 1])
        with col_sort1:
            sort_selection = st.selectbox(
                "Sort Table By Column:",
                options=["Streak", "Ticker", "Group", "Buy Price", "Current Market", "Sell Price", "Status", "Last Sync Date"],
                index=0
            )
        with col_sort2:
            sort_direction = st.radio("Order Direction:", options=["Descending", "Ascending"], horizontal=True, index=0)

        # Map display names back to raw dataframe columns
        sort_mapping = {
            "Streak": "Days Below Buy Target",
            "Ticker": "Ticker",
            "Group": "Group",
            "Buy Price": "Buy Price",
            "Current Market": "Current Market",
            "Sell Price": "Sell Price",
            "Status": "Status",
            "Last Sync Date": "Last Updated"
        }
        
        # Sort values cleanly before parsing to layout editor
        df_results_viz = df_results_viz.sort_values(
            by=sort_mapping[sort_selection],
            ascending=(sort_direction == "Ascending"),
            na_position="last"
        ).reset_index(drop=True)

        response_editor = st.data_editor(
            df_results_viz,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", disabled=True, width="small"), 
                "Group": st.column_config.SelectboxColumn("Group (Edit)", options=["Target", "Holding", "Wishlist"], required=True, width="medium"),
                "Buy Price": st.column_config.NumberColumn("Buy Price (Edit)", min_value=0.0, format="$%.2f", width="medium"),
                "Current Market": st.column_config.NumberColumn("Current Market", disabled=True, format="$%.2f", width="medium"),
                "Sell Price": st.column_config.NumberColumn("Sell Price (Edit)", min_value=0.0, format="$%.2f", width="medium"),
                "Status": st.column_config.TextColumn("System Status", disabled=True, width="medium"),
                "Days Below Buy Target": st.column_config.NumberColumn("Streak", disabled=True, format="%d Days", width="small"),
                "Last Updated": st.column_config.TextColumn("Last Sync Date")
            },
            use_container_width=True, 
            hide_index=True, 
            num_rows="dynamic", 
            height=get_table_height(df_results_viz, max_height=500),
            key="unified_portfolio_editor"
        )
        
        # Grid Synchronizer Logic
        grid_state = st.session_state.unified_portfolio_editor
        has_changed = False
        
        if grid_state.get("deleted_rows"):
            deleted_tickers = df_results_viz.iloc[grid_state["deleted_rows"]]['Ticker'].tolist()
            try:
                with conn.session as session:
                    for tk in deleted_tickers:
                        session.execute(text('DELETE FROM watchlist WHERE "Ticker" = :tk;'), {"tk": tk})
                    session.commit()
                has_changed = True
            except Exception as e:
                st.error(f"Write-back failure: {e}")
                
        elif grid_state.get("edited_rows"):
            try:
                with conn.session as session:
                    for str_idx, changes in grid_state["edited_rows"].items():
                        idx = int(str_idx)
                        if idx < len(df_results_viz):
                            target_ticker = df_results_viz.at[idx, 'Ticker']
                            
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
                st.error(f"Data mutation execution failed: {e}")
                    
        if has_changed:
            st.rerun()

    with tab2:
        st.subheader("Core Execution Allocations")
        df_holding = df_results[df_results["Group"] == "Holding"].copy()
        col_h1, col_h2 = st.columns(2)
        
        with col_h1:
            st.markdown("#### Buy Zone Allocation")
            buy_zone = df_holding[df_holding["Current Market"] <= (df_holding["Buy Price"] * 1.05)].copy()
            
            if not buy_zone.empty:
                buy_zone["Distance"] = buy_zone["Current Market"] - buy_zone["Buy Price"]
                buy_zone = buy_zone.sort_values(by="Distance")
                buy_zone["Action"] = buy_zone.apply(
                    lambda x: "Triggering Buy" if x["Current Market"] <= x["Buy Price"] 
                    else f"{((x['Current Market']/x['Buy Price'])-1)*100:.1f}% Above Target", axis=1
                )
                
                st.dataframe(
                    buy_zone[["Ticker", "Current Market", "Buy Price", "Action"]], 
                    column_config={
                        "Current Market": st.column_config.NumberColumn("Market Price", format="$%.2f"),
                        "Buy Price": st.column_config.NumberColumn("Target Price", format="$%.2f"),
                        "Action": st.column_config.TextColumn("Signal Context")
                    },
                    use_container_width=True, 
                    hide_index=True, 
                    height=get_table_height(buy_zone, max_height=350)
                )
            else:
                st.info("No corporate holdings currently occupying the Entry Value Matrix.")
        
        with col_h2:
            st.markdown("#### Profit Horizon Allocation")
            profit_zone = df_holding[df_holding["Current Market"] >= (df_holding["Sell Price"] * 0.95)].copy()
            
            if not profit_zone.empty:
                profit_zone["Distance"] = profit_zone["Sell Price"] - profit_zone["Current Market"]
                profit_zone = profit_zone.sort_values(by="Distance")
                profit_zone["Status"] = profit_zone.apply(
                    lambda x: "Target Profit Met" if x["Current Market"] >= x["Sell Price"] 
                    else f"{((1-(x['Current Market']/x['Sell Price'])))*100:.1f}% Below Target", axis=1
                )
                
                st.dataframe(
                    profit_zone[["Ticker", "Current Market", "Sell Price", "Status"]], 
                    column_config={
                        "Current Market": st.column_config.NumberColumn("Market Price", format="$%.2f"),
                        "Sell Price": st.column_config.NumberColumn("Target Profit", format="$%.2f"),
                        "Status": st.column_config.TextColumn("Signal Context")
                    },
                    use_container_width=True, 
                    hide_index=True, 
                    height=get_table_height(profit_zone, max_height=350)
                )
            else:
                st.info("No corporate holdings currently occupying the Liquidation Horizon Matrix.")

    with tab3:
        st.subheader("Extreme Variance Trackers")
        
        df_wishlist = df_results[df_results["Group"] == "Wishlist"]
        df_target = df_results[df_results["Group"] == "Target"]

        col_w1, col_w2 = st.columns(2)
        
        with col_w1:
            st.markdown("#### Wishlist Standouts")
            wish_macro = df_top_90d_drops[df_top_90d_drops["Ticker"].isin(df_wishlist["Ticker"])] if not df_top_90d_drops.empty else pd.DataFrame()
            if not wish_macro.empty:
                st.caption("Macro Real Estate Drops (90-Day Drop >= 25%)")
                st.dataframe(
                    wish_macro[["Ticker", "Buy Price", "Current Market", "90-Day Decline"]],
                    column_config={
                        "Buy Price": st.column_config.NumberColumn(format="$%.2f"),
                        "Current Market": st.column_config.NumberColumn(format="$%.2f"),
                        "90-Day Decline": st.column_config.NumberColumn(format="%.2f%%")
                    },
                    use_container_width=True, hide_index=True, height=get_table_height(wish_macro, max_height=200)
                )
            
            wish_weekly = df_top_10_drops[df_top_10_drops["Ticker"].isin(df_wishlist["Ticker"])] if not df_top_10_drops.empty else pd.DataFrame()
            if not wish_weekly.empty:
                st.caption("High Velocity Selloffs (Weekly Change <= -10%)")
                st.dataframe(
                    wish_weekly[["Ticker", "Buy Price", "Current Market", "Weekly Change %"]],
                    column_config={
                        "Buy Price": st.column_config.NumberColumn(format="$%.2f"),
                        "Current Market": st.column_config.NumberColumn(format="$%.2f"),
                        "Weekly Change %": st.column_config.NumberColumn(format="%.2f%%")
                    },
                    use_container_width=True, hide_index=True, height=get_table_height(wish_weekly, max_height=200)
                )
            if wish_macro.empty and wish_weekly.empty:
                st.info("Zero anomalous downside volume shifts identified inside Wishlist assets.")

        with col_w2:
            st.markdown("#### Target Standouts")
            target_macro = df_top_90d_drops[df_top_90d_drops["Ticker"].isin(df_target["Ticker"])] if not df_top_90d_drops.empty else pd.DataFrame()
            if not target_macro.empty:
                st.caption("Macro Real Estate Drops (90-Day Drop >= 25%)")
                st.dataframe(
                    target_macro[["Ticker", "Buy Price", "Current Market", "90-Day Decline"]],
                    column_config={
                        "Buy Price": st.column_config.NumberColumn(format="$%.2f"),
                        "Current Market": st.column_config.NumberColumn(format="$%.2f"),
                        "90-Day Decline": st.column_config.NumberColumn(format="%.2f%%")
                    },
                    use_container_width=True, hide_index=True, height=get_table_height(target_macro, max_height=200)
                )
                
            target_weekly = df_top_10_drops[df_top_10_drops["Ticker"].isin(df_target["Ticker"])] if not df_top_10_drops.empty else pd.DataFrame()
            if not target_weekly.empty:
                st.caption("High Velocity Selloffs (Weekly Change <= -10%)")
                st.dataframe(
                    target_weekly[["Ticker", "Buy Price", "Current Market", "Weekly Change %"]],
                    column_config={
                        "Buy Price": st.column_config.NumberColumn(format="$%.2f"),
                        "Current Market": st.column_config.NumberColumn(format="$%.2f"),
                        "Weekly Change %": st.column_config.NumberColumn(format="%.2f%%")
                    },
                    use_container_width=True, hide_index=True, height=get_table_height(target_weekly, max_height=200)
                )
            if target_macro.empty and target_weekly.empty:
                st.info("Zero anomalous downside volume shifts identified inside active Core Target assets.")
else:
    st.info("App database is currently empty. Populate items through the sidebar to initialize your dashboards.")
