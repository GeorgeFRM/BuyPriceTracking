import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# Set up clean page configuration
st.set_page_config(
    page_title="Institutional Watchlist Tracker",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Stock Target Monitor & Execution Dashboard")
st.markdown("Upload your asset watchlist Excel file or edit targets directly in the table below. Market prices refresh once per day.")

# --- SIDEBAR: USER INSTRUCTIONS ---
with st.sidebar:
    st.header("📋 Template Requirements")
    st.markdown("""
    If uploading a file (`.xlsx`), ensure it contains these headers in the first row:
    * **Ticker** * **Buy Price** * **Sell Price** """)
    st.write("---")
    st.caption("Data cached daily for performance. Edits to targets will update your statuses and timestamps instantly.")
    
    # Optional Manual Override Button to pull brand new data if ever needed
    if st.button("🔄 Force Refresh Market Data"):
        st.cache_data.clear()
        st.rerun()

# --- FILE UPLOADER WIDGET ---
uploaded_file = st.file_uploader("Drag and drop your asset watchlist Excel file here to initialize data", type=["xlsx"])

# --- SESSION STATE INITIALIZATION ---
if 'raw_portfolio' not in st.session_state:
    st.session_state.raw_portfolio = None

if uploaded_file is not None:
    try:
        raw_df = pd.read_excel(uploaded_file)
        raw_df.columns = [str(col).strip().title() for col in raw_df.columns]
        
        required_cols = ['Ticker', 'Buy Price', 'Sell Price']
        if not all(col in raw_df.columns for col in required_cols):
            st.error(f"Mapping Error: Spreadsheet must contain these exact columns: {required_cols}")
        else:
            initial_data = []
            for _, row in raw_df.iterrows():
                initial_data.append({
                    "Ticker": str(row['Ticker']).strip().upper(),
                    "Buy Price": float(row['Buy Price']),
                    "Sell Price": float(row['Sell Price']),
                    "Last Updated": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
            st.session_state.raw_portfolio = pd.DataFrame(initial_data)
    except Exception as e:
        st.error(f"Error parsing uploaded file: {e}")


# --- HIGH-PERFORMANCE DAILY CACHED ENGINE ---
# This function queries the internet exactly ONCE every 24 hours.
# It stores the current price and historical close array for every ticker.
@st.cache_data(ttl=86400)
def fetch_daily_market_snapshots(tickers_tuple):
    market_snapshots = {}
    for ticker in tickers_tuple:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            if not hist.empty:
                current_price = round(hist['Close'].iloc[-1], 2)
                # Keep historical closes as a plain list of floats for clean caching
                historical_closes = [round(x, 2) for x in hist['Close'].iloc[::-1].tolist()]
                
                market_snapshots[ticker] = {
                    "current_price": current_price,
                    "historical_closes": historical_closes
                }
        except Exception:
            pass
    return market_snapshots


# --- APPLICATION LOGIC ---
if st.session_state.raw_portfolio is not None:
    
    # 1. Gather all active tickers to feed into our daily cache engine
    active_tickers = tuple(st.session_state.raw_portfolio['Ticker'].unique())
    
    # This call is instant if run within the same 24-hour window
    daily_data = fetch_daily_market_snapshots(active_tickers)
    
    # 2. Process metrics using the fast, local daily snapshot
    processed_data = []
    buy_alerts = 0
    sell_alerts = 0
    
    for _, row in st.session_state.raw_portfolio.iterrows():
        ticker = row['Ticker']
        buy_target = row['Buy Price']
        sell_target = row['Sell Price']
        last_updated = row['Last Updated']
        
        if ticker in daily_data:
            current_price = daily_data[ticker]["current_price"]
            closes_backward = daily_data[ticker]["historical_closes"]
            
            # Compute days below limit using cached history
            days_below = 0
            if current_price <= buy_target:
                for close_price in closes_backward:
                    if close_price <= buy_target:
                        days_below += 1
                    else:
                        break
            
            # Structural Status Assignments
            if current_price <= buy_target:
                status = "Buy"
                buy_alerts += 1
                days_display = f"{days_below} days" if days_below > 1 else "1 day"
            elif current_price >= sell_target:
                status = "Profit Zone"
                sell_alerts += 1
                days_display = ""
            else:
                status = "Hold / Monitor"
                days_display = ""
        else:
            # Fallback for data fetch issues
            current_price = 0.0
            status = "Data Offline"
            days_display = ""
            
        processed_data.append({
            "Ticker": ticker,
            "Buy Price": buy_target,
            "Current Market": current_price,
            "Sell Price": sell_target,
            "Status": status,
            "Days Below Buy Target": days_display,
            "Last Updated": last_updated
        })
        
    df_results = pd.DataFrame(processed_data)
    
    # 3. Render Dashboard Metric Cards
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Assets Tracked", value=len(df_results))
    with col2:
        st.metric(label="Buy Targets Triggered", value=buy_alerts)
    with col3:
        st.metric(label="Profit Horizons Reached", value=sell_alerts)
    st.write("---")
    
    # 4. Styling Layer: Highlights "Buy" rows clean green with no emoji
    def highlight_status(row):
        css_styles = [''] * len(row)
        if row['Status'] == "Buy":
            css_styles = ['background-color: rgba(46, 204, 113, 0.18); color: #2ecc71; font-weight: bold;'] * len(row)
        return css_styles

    styled_df = df_results.style.format({
        "Buy Price": "${:,.2f}",
        "Current Market": "${:,.2f}",
        "Sell Price": "${:,.2f}"
    }).apply(highlight_status, axis=1)
    
    # 5. Render Unified Editable Grid
    st.subheader("📊 Live Watchlist Execution Grid")
    response_editor = st.data_editor(
        styled_df,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
            "Buy Price": st.column_config.NumberColumn("Buy Price (Double-Click to Edit)", min_value=0.0, format="$%.2f"),
            "Current Market": st.column_config.NumberColumn("Current Market", disabled=True, format="$%.2f"),
            "Sell Price": st.column_config.NumberColumn("Sell Price (Double-Click to Edit)", min_value=0.0, format="$%.2f"),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Days Below Buy Target": st.column_config.TextColumn("Days Below Buy Target", disabled=True),
            "Last Updated": st.column_config.TextColumn("Last Updated", disabled=True)
        },
        use_container_width=True,
        hide_index=True,
        key="unified_portfolio_editor"
    )
    
    # 6. Capture updates seamlessly from local memory 
    current_raw = st.session_state.raw_portfolio.copy()
    has_changed = False
    
    for idx in range(len(response_editor)):
        edited_buy = response_editor.iloc[idx]['Buy Price']
        edited_sell = response_editor.iloc[idx]['Sell Price']
        
        if (edited_buy != current_raw.at[idx, 'Buy Price']) or (edited_sell != current_raw.at[idx, 'Sell Price']):
            current_raw.at[idx, 'Buy Price'] = edited_buy
            current_raw.at[idx, 'Sell Price'] = edited_sell
            current_raw.at[idx, 'Last Updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            has_changed = True
            
    if has_changed:
        st.session_state.raw_portfolio = current_raw
        st.rerun()

else:
    st.info("💡 App is live. Awaiting file execution. Upload your asset tracking workbook to populate live market valuations.")
