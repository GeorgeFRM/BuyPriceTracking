import streamlit as st
import yfinance as yf
import pandas as pd

# Set up clean page configuration
st.set_page_config(
    page_title="Institutional Watchlist Tracker",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Stock Target Monitor & Execution Dashboard")
st.markdown("Upload an Excel file once to seed your database, then manage assets dynamically via the grid and sidebar panels.")

# --- SESSION STATE INITIALIZATION ---
if 'raw_portfolio' not in st.session_state:
    st.session_state.raw_portfolio = None

# --- SIDEBAR: USER INTERACTION PANEL ---
with st.sidebar:
    st.header("📋 Data Management")
    
    st.subheader("➕ Add Single Asset")
    with st.form("single_ticker_form", clear_on_submit=True):
        new_ticker = st.text_input("Ticker Symbol (e.g., AAPL)").strip().upper()
        new_buy = st.number_input("Buy Target Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_sell = st.number_input("Sell Profit Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_updated = st.text_input("Last Updated (yyyy/mm/dd)", placeholder="2026/05/28")
        submit_button = st.form_submit_button("Add to Watchlist")
        
        if submit_button:
            if not new_ticker or new_buy <= 0 or new_sell <= 0:
                st.error("Please enter a valid ticker symbol and prices greater than $0.00.")
            else:
                new_row = pd.DataFrame([{
                    "Ticker": new_ticker,
                    "Buy Price": float(new_buy),
                    "Sell Price": float(new_sell),
                    "Last Updated": str(new_updated).strip()
                }])
                if st.session_state.raw_portfolio is not None:
                    st.session_state.raw_portfolio = st.session_state.raw_portfolio[st.session_state.raw_portfolio['Ticker'] != new_ticker]
                    st.session_state.raw_portfolio = pd.concat([st.session_state.raw_portfolio, new_row], ignore_index=True)
                else:
                    st.session_state.raw_portfolio = new_row
                st.success(f"Added {new_ticker} successfully!")
                st.rerun()

    st.write("---")
    st.header("⚙️ Settings & System")
    st.caption("To delete a stock: Select the checkbox next to the ticker in the main grid and press 'Delete' on your keyboard, or use the trash icon.")
    
    if st.button("🗑️ Clear Entire Portfolio Database"):
        st.session_state.raw_portfolio = None
        st.cache_data.clear()
        st.rerun()
        
    if st.button("🔄 Force Refresh Market Data"):
        st.cache_data.clear()
        st.rerun()

# --- ONE-TIME EXCEL INITIALIZATION SEED ---
if st.session_state.raw_portfolio is None:
    uploaded_file = st.file_uploader("Drag and drop your asset watchlist Excel file here to initialize data", type=["xlsx"], key="excel_uploader")

    if uploaded_file is not None:
        try:
            raw_df = pd.read_excel(uploaded_file)
            raw_df.columns = [str(col).strip().title() for col in raw_df.columns]
            
            required_cols = ['Ticker', 'Buy Price', 'Sell Price', 'Last Updated']
            if not all(col in raw_df.columns for col in required_cols):
                st.error(f"Mapping Error: Spreadsheet must contain these exact columns: {required_cols}")
            else:
                initial_data = []
                for _, row in raw_df.iterrows():
                    dt = row['Last Updated']
                    formatted_date = dt.strftime("%Y/%m/%d") if pd.notna(dt) and hasattr(dt, 'strftime') else str(dt).strip() if pd.notna(dt) else ""
                    initial_data.append({
                        "Ticker": str(row['Ticker']).strip().upper(),
                        "Buy Price": float(row['Buy Price']),
                        "Sell Price": float(row['Sell Price']),
                        "Last Updated": formatted_date
                    })
                st.session_state.raw_portfolio = pd.DataFrame(initial_data)
                st.success("Watchlist database successfully initialized from Excel!")
                st.rerun()
        except Exception as e:
            st.error(f"Error parsing uploaded file: {e}")

# --- HIGH-PERFORMANCE DAILY CACHED ENGINE ---
@st.cache_data(ttl=86400)
def fetch_daily_market_snapshots(tickers_tuple):
    market_snapshots = {}
    if not tickers_tuple:
        return market_snapshots
    for ticker in tickers_tuple:
        try:
            stock = yf.Ticker(ticker)
            # FIXED: Expanded lookup range from '6mo' to '1y' for deep historical tracking
            hist = stock.history(period="1y")
            if not hist.empty:
                current_price = round(hist['Close'].iloc[-1], 2)
                price_90d_ago = round(hist['Close'].iloc[-64], 2) if len(hist) >= 64 else round(hist['Close'].iloc[0], 2)
                
                market_snapshots[ticker] = {
                    "current_price": current_price,
                    "historical_closes": [round(x, 2) for x in hist['Close'].iloc[::-1].tolist()],
                    "price_1w_ago": round(hist['Close'].iloc[-6], 2) if len(hist) >= 6 else round(hist['Close'].iloc[0], 2),
                    "price_90d_ago": price_90d_ago
                }
        except Exception:
            pass
    return market_snapshots

# --- APPLICATION LOGIC ---
if st.session_state.raw_portfolio is not None:
    active_tickers = tuple(st.session_state.raw_portfolio['Ticker'].unique())
    daily_data = fetch_daily_market_snapshots(active_tickers)
    
    processed_data, top_drops_data, macro_drops_data = [], [], []
    buy_alerts, sell_alerts = 0, 0
    
    for _, row in st.session_state.raw_portfolio.iterrows():
        ticker, buy_target, sell_target, last_updated = row['Ticker'], row['Buy Price'], row['Sell Price'], row['Last Updated']
        
        if ticker in daily_data:
            current_price = daily_data[ticker]["current_price"]
            closes_backward = daily_data[ticker]["historical_closes"]
            weekly_perf = ((current_price - daily_data[ticker]["price_1w_ago"]) / daily_data[ticker]["price_1w_ago"]) * 100
            macro_perf = ((current_price - daily_data[ticker]["price_90d_ago"]) / daily_data[ticker]["price_90d_ago"]) * 100
            
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
    
    # Sort execution grid based on days below target (highest consecutive count descending)
    if not df_results.empty:
        df_results = df_results.iloc[
            df_results['Days Below Buy Target'].fillna(-1).sort_values(ascending=False).index
        ].reset_index(drop=True)
        
    # Generate Top Weekly Drops Data (Worse than -10%, max 10)
    if top_drops_data:
        df_all_drops = pd.DataFrame(top_drops_data)
        df_top_10_drops = df_all_drops[df_all_drops['Weekly Change %'] <= -10.0].sort_values(by="Weekly Change %").head(10)
    else:
        df_top_10_drops = pd.DataFrame(columns=["Ticker", "Buy Price", "Current Market", "Weekly Change %", "Last Updated"])

    # Generate 90-Day Macro Drops Data (Worse than -25%, max 25)
    if macro_drops_data:
        df_all_macro = pd.DataFrame(macro_drops_data)
        df_top_90d_drops = df_all_macro[df_all_macro['90-Day Decline'] <= -25.0].sort_values(by="90-Day Decline").head(25)
    else:
        df_top_90d_drops = pd.DataFrame(columns=["Ticker", "Buy Price", "Current Market", "90-Day Decline", "Last Updated"])

    # KPI Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Assets Tracked", len(df_results))
    col2.metric("Buy Targets Triggered", buy_alerts)
    col3.metric("Profit Horizons Reached", sell_alerts)
    st.write("---")
    
    # --- SPLIT PANEL DISPLAY ---
    layout_left, layout_right = st.columns([1, 1])
    
    with layout_left:
        st.subheader("📉 Top Weekly Declines")
        if not df_top_10_drops.empty:
            st.dataframe(df_top_10_drops.style.format({
                "Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "Weekly Change %": "{:+.2f}%"
            }), use_container_width=True, hide_index=True)
        else:
            st.info("No tracking assets have declined by more than 10% over the trailing week.")
            
    with layout_right:
        st.subheader("📉 Declines of 25% or More")
        if not df_top_90d_drops.empty:
            st.dataframe(df_top_90d_drops.style.format({
                "Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "90-Day Decline": "{:+.2f}%"
            }), use_container_width=True, hide_index=True)
        else:
            st.info("No tracking assets have declined by 25% or more over the trailing 90 days.")

    st.write("---")
    
    # Main Watchlist Grid Layout Configuration
    styled_df = df_results.style.format({"Buy Price": "${:,.2f}", "Current Market": "${:,.2f}", "Sell Price": "${:,.2f}"}).apply(
        lambda r: ['background-color: rgba(46, 204, 113, 0.18); color: #2ecc71; font-weight: bold;'] * len(r) if r['Status'] == "Buy" else [''] * len(r), axis=1
    )
    
    st.subheader("📊 Live Watchlist Execution Grid")
    response_editor = st.data_editor(
        styled_df,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", disabled=True), 
            "Buy Price": st.column_config.NumberColumn("Buy Price (Double-Click to Edit)", min_value=0.0, format="$%.2f"),
            "Current Market": st.column_config.NumberColumn("Current Market", disabled=True, format="$%.2f"),
            "Sell Price": st.column_config.NumberColumn("Sell Price (Double-Click to Edit)", min_value=0.0, format="$%.2f"),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Days Below Buy Target": st.column_config.NumberColumn("Days Below Buy Target", disabled=True, format="%d days"),
            "Last Updated": st.column_config.TextColumn("Last Updated (Double-Click to Edit)")
        },
        use_container_width=True, hide_index=False, num_rows="dynamic", key="unified_portfolio_editor"
    )
    
    # Grid Synchronizer Logic
    grid_state = st.session_state.unified_portfolio_editor
    has_changed = False
    
    if grid_state.get("deleted_rows"):
        deleted_tickers = df_results.iloc[grid_state["deleted_rows"]]['Ticker'].tolist()
        st.session_state.raw_portfolio = st.session_state.raw_portfolio[
            ~st.session_state.raw_portfolio['Ticker'].isin(deleted_tickers)
        ].reset_index(drop=True)
        has_changed = True
    elif grid_state.get("edited_rows"):
        for str_idx, changes in grid_state["edited_rows"].items():
            idx = int(str_idx)
            if idx < len(df_results):
                target_ticker = df_results.at[idx, 'Ticker']
                master_idx = st.session_state.raw_portfolio[st.session_state.raw_portfolio['Ticker'] == target_ticker].index[0]
                for col, val in changes.items():
                    st.session_state.raw_portfolio.at[master_idx, col] = float(val) if "Price" in col else str(val).strip()
                has_changed = True
                
    if has_changed:
        st.rerun()
else:
    st.info("💡 App database is currently empty. Drag and drop your asset watchlist Excel file above to initialize data.")
