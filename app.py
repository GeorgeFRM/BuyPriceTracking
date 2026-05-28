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
            hist = stock.history(period="6mo")
            if not hist.empty:
                current_price = round(hist['Close'].iloc[-1], 2)
                price_90d_ago = round(hist['Close'].iloc[-64], 2) if len(hist) >= 64 else round(hist['Close'].iloc[0], 2)
                
                market_snapshots[ticker] = {
                    "current_price": current_price,
                    "historical
