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
        new_updated = st.text_input("Last Updated (yyyy/mm/dd)", placeholder="2026/05/28")
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
    st.caption("To delete a stock: Select the checkbox next to the ticker in the main grid and press 'Delete' on your keyboard, or use the trash icon.")
    
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
                raw_date_val = row['Last Updated']
                formatted_date_str = ""
                
                if pd.notna(raw_date_val):
                    try:
                        if hasattr(raw_date_val, 'strftime'):
                            formatted_date_str = raw_date_val.strftime("%Y/%m/%d")
                        else:
                            parsed_date = pd.to_datetime(raw_date_val)
                            formatted_date_str = parsed_date.strftime("%Y/%m/%d")
                    except Exception:
                        formatted_date_str = str(raw_date_
