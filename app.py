import streamlit as st
import yfinance as yf
import pandas as pd
import datetime

# Set up clean page configuration
st.set_page_config(
    page_title="Institutional Watchlist Tracker",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Stock Target Monitor & Execution Dashboard")
st.markdown("Dynamic execution platform. Manage assets via the unified grid, sidebar utilities, or initial Excel seeding.")

# --- SESSION STATE INITIALIZATION ---
if 'raw_portfolio' not in st.session_state:
    st.session_state.raw_portfolio = None
# NEW: Initialize tracking fields for our Level-2 session cache
if 'market_cache' not in st.session_state:
    st.session_state.market_cache = {}
if 'cache_timestamp' not in st.session_state:
    st.session_state.cache_timestamp = None

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
                    "Ticker": new_ticker, "Buy Price": float(new_buy),
                    "Sell Price": float(new_sell), "Last Updated": str(new_updated).strip()
                }])
                if st.session_state.raw_portfolio is not None:
                    st.session_state.raw_portfolio = st.session_state.raw_portfolio[st.session_state.raw_portfolio['Ticker'] != new_ticker]
                    st.session_state.raw_portfolio = pd.concat([st.session_state.raw_portfolio, new_row], ignore_index=True)
                else:
                    st.session_state.raw_portfolio = new_row
                
                # NEW: Clear timestamp when a new stock is added so it updates instantly
                st.session_state.cache_timestamp = None
                st.success(f"Added {new_ticker} successfully!")
                st.rerun()

    st.write("---")
    st.header("⚙️ Settings & System")
    st.caption("To delete a stock: Select the checkbox next to the ticker in the main grid and press 'Delete' on your keyboard, or use the trash icon.")
    
    if st.button("🗑️ Clear Entire Portfolio Database", use_container_width=True):
        st.session_state.raw_portfolio = None
        st.session_state.market_cache = {}
        st.session_state.cache_timestamp = None
        st.cache_data.clear()
        st.rerun()
        
    if st.button("🔄 Force Refresh Market Data", use_container_width=True):
        # NEW: Resetting the timestamp forces an immediate redownload from Yahoo Finance
        st.session_state.cache_timestamp = None
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
                    initial_data.
