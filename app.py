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
st.markdown("Upload your asset watchlist Excel file or edit targets directly in the table below. Market prices refresh once per day.")

# --- SESSION STATE INITIALIZATION ---
if 'raw_portfolio' not in st.session_state:
    st.session_state.raw_portfolio = None

# --- SIDEBAR: USER INTERACTION PANEL ---
with st.sidebar:
    st.header("📋 Data Management")
    
    # Section A: Add a Single Stock
    st.subheader("➕ Add Single Asset")
    with st.form("single_ticker_form", clear_on_submit=True):
        new_ticker = st.text_input("Ticker Symbol (e.g., AAPL)").strip().upper()
        new_buy = st.number_input("Buy Target Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_sell = st.number_input("Sell Profit Price ($)", min_value=0.0, step=0.01, format="%.2f")
        new_updated = st.text_input("Last Updated Note/Date (e.g., 2026-05-28)")
        submit_button = st.form_submit_button("Add to Watchlist")
        
        if submit_button:
            if not new_ticker:
                st.error("Please enter a valid ticker symbol.")
            elif new_buy <= 0 or new_sell <= 0:
                st.error("Prices must be greater than $0.00.")
            else:
                new_row = pd.DataFrame([{
                    "Ticker": new_ticker,
                    "Buy Price": float(new_buy),
                    "Sell Price": float(new_sell),
                    "Last Updated": str(new_updated).strip()
                }])
                
                if st.session_state.raw_portfolio is None:
                    st.session_state.raw_portfolio = new_row
                else:
                    if new_ticker in st.session_state.raw_portfolio['Ticker'].values:
                        st.session_state.raw_portfolio = st.session_state.raw_portfolio[st.session_state.raw_portfolio['Ticker'] != new_ticker]
                    st.session_state.raw_portfolio = pd.concat([st.session_state.raw_portfolio, new_row], ignore_index=True)
                
                st.success(f"Added {new_ticker} successfully!")
                st.rerun()

    st.write("---")
    st.header("⚙️ Settings & System")
    st.caption("Double-click any cell in 'Buy Price', 'Sell Price', or 'Last Updated' to make inline adjustments.")
    
    if st.button("🔄 Force Refresh Market Data"):
        st.cache_data.clear()
        st.rerun()

# --- FILE UPLOADER WIDGET ---
uploaded_file = st.file_uploader("Drag and drop your asset watchlist Excel file here to initialize data", type=["xlsx"])

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
                initial_data.append({
                    "Ticker": str(row['Ticker']).strip().upper(),
                    "Buy Price": float(row['Buy Price']),
                    "Sell Price": float(row['Sell Price']),
                    "Last Updated": str(row['Last Updated']).strip() if pd.notna(row['Last Updated']) else ""
                })
            st.session_state.raw_portfolio = pd.DataFrame(initial_data)
    except Exception as e:
        st.error(f"Error parsing uploaded file: {e}")


# --- HIGH-PERFORMANCE DAILY CACHED ENGINE ---
@st.cache_data(ttl=86400)
def fetch_daily_market_snapshots(tickers_tuple):
    market_snapshots = {}
    for ticker in tickers_tuple:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            if not hist.empty:
                current_price = round(hist['Close'].iloc[-1], 2)
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
    
    active_tickers = tuple(st.session_state.raw_portfolio['Ticker'].unique())
    daily_data = fetch_daily_market_snapshots(active_tickers)
    
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
            
            days_below = 0
            if current_price <= buy_target:
                for close_price in closes_backward:
                    if close_price <= buy_target:
                        days_below += 1
                    else:
                        break
            
            if current_price <= buy_target:
                status = "Buy"
                buy_alerts += 1
                # FIXED: Keep this as a raw number/integer so the data table sorts it correctly
                days_display = int(days_below) 
            elif current_price >= sell_target:
                status = "Profit Zone"
                sell_alerts += 1
                days_display = None # Use None instead of a blank string for numbers
            else:
                status = "Hold / Monitor"
                days_display = None
        else:
            current_price = 0.0
            status = "Data Offline"
            days_display = None
            
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
    
    # Render Dashboard Metric Cards
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Assets Tracked", value=len(df_results))
    with col2:
        st.metric(label="Buy Targets Triggered", value=buy_alerts)
    with col3:
        st.metric(label="Profit Horizons Reached", value=sell_alerts)
    st.write("---")
    
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
    
    # Render Unified Editable Grid
    st.subheader("📊 Live Watchlist Execution Grid")
    response_editor = st.data_editor(
        styled_df,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
            "Buy Price": st.column_config.NumberColumn("Buy Price (Double-Click to Edit)", min_value=0.0, format="$%.2f"),
            "Current Market": st.column_config.NumberColumn("Current Market", disabled=True, format="$%.2f"),
            "Sell Price": st.column_config.NumberColumn("Sell Price (Double-Click to Edit)", min_value=0.0, format="$%.2f"),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            # FIXED: Configured as a NumberColumn with a custom display format string ending in " days"
            "Days Below Buy Target": st.column_config.NumberColumn("Days Below Buy Target", disabled=True, format="%d days"),
            "Last Updated": st.column_config.TextColumn("Last Updated (Double-Click to Edit)", disabled=False)
        },
        use_container_width=True,
        hide_index=True,
        key="unified_portfolio_editor"
    )
    
    # Capture grid edits made to manual parameters
    current_raw = st.session_state.raw_portfolio.copy()
    has_changed = False
    
    for idx in range(len(response_editor)):
        edited_buy = response_editor.iloc[idx]['Buy Price']
        edited_sell = response_editor.iloc[idx]['Sell Price']
        edited_updated = response_editor.iloc[idx]['Last Updated']
        
        if (edited_buy != current_raw.at[idx, 'Buy Price']) or \
           (edited_sell != current_raw.at[idx, 'Sell Price']) or \
           (str(edited_updated) != str(current_raw.at[idx, 'Last Updated'])):
            
            current_raw.at[idx, 'Buy Price'] = edited_buy
            current_raw.at[idx, 'Sell Price'] = edited_sell
            current_raw.at[idx, 'Last Updated'] = str(edited_updated).strip()
            has_changed = True
            
    if has_changed:
        st.session_state.raw_portfolio = current_raw
        st.rerun()

else:
    st.info("💡 App is live. Awaiting file execution. Upload an Excel workbook containing 'Ticker', 'Buy Price', 'Sell Price', and 'Last Updated' columns to begin.")
