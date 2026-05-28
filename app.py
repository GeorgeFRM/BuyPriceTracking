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
st.markdown("Upload your asset watchlist Excel file or edit targets directly in the table below. Changes update live.")

# --- SIDEBAR: USER INSTRUCTIONS ---
with st.sidebar:
    st.header("📋 Template Requirements")
    st.markdown("""
    If uploading a file (`.xlsx`), ensure it contains these headers in the first row:
    * **Ticker** * **Buy Price** * **Sell Price** """)
    st.write("---")
    st.caption("Double-click any cell in 'Buy Price' or 'Sell Price' to update targets. The tracking status and 'Days Below' calculation will update instantly.")

# --- FILE UPLOADER WIDGET ---
uploaded_file = st.file_uploader("Drag and drop your asset watchlist Excel file here to initialize data", type=["xlsx"])

# --- SESSION STATE INITIALIZATION ---
# Holds the structural raw parameters (Ticker, Buy Price, Sell Price, Last Updated)
if 'raw_portfolio' not in st.session_state:
    st.session_state.raw_portfolio = None

# Process an incoming Excel upload
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

# --- CALCULATION ENGINE ---
# Whenever the user modifies prices, this runs to pull market data and compute the metrics
def compute_live_dashboard(portfolio_df):
    processed_data = []
    buy_alerts = 0
    sell_alerts = 0
    
    for _, row in portfolio_df.iterrows():
        ticker = row['Ticker']
        buy_target = row['Buy Price']
        sell_target = row['Sell Price']
        last_updated = row['Last Updated']
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            
            if not hist.empty:
                current_price = round(hist['Close'].iloc[-1], 2)
                
                # Calculate consecutive historical streak duration
                days_below = 0
                if current_price <= buy_target:
                    historical_closes = hist['Close'].iloc[::-1]
                    for close_price in historical_closes:
                        if close_price <= buy_target:
                            days_below += 1
                        else:
                            break
                
                # Assign core status indicators
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
                    
                processed_data.append({
                    "Ticker": ticker,
                    "Buy Price": buy_target,
                    "Current Market": current_price,
                    "Sell Price": sell_target,
                    "Status": status,
                    "Days Below Buy Target": days_display,
                    "Last Updated": last_updated
                })
        except Exception:
            processed_data.append({
                "Ticker": ticker, "Buy Price": buy_target, "Current Market": 0.0,
                "Sell Price": sell_target, "Status": "Data Error", "Days Below Buy Target": "", "Last Updated": last_updated
            })
            
    return pd.DataFrame(processed_data), buy_alerts, sell_alerts


# --- RENDER INTERACTIVE UI PANEL ---
if st.session_state.raw_portfolio is not None:
    
    # 1. Run live analytics calculations on our master dataset
    with st.spinner("Querying real-time public market valuations..."):
        computed_df, total_buys, total_sells = compute_live_dashboard(st.session_state.raw_portfolio)
    
    # 2. Render summary performance cards
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Assets Tracked", value=len(computed_df))
    with col2:
        st.metric(label="Buy Targets Triggered", value=total_buys)
    with col3:
        st.metric(label="Profit Horizons Reached", value=total_sells)
    st.write("---")
    
    # 3. Apply style formatting configurations for layout display
    def highlight_status(row):
        css_styles = [''] * len(row)
        if row['Status'] == "Buy":
            css_styles = ['background-color: rgba(46, 204, 113, 0.18); color: #2ecc71; font-weight: bold;'] * len(row)
        return css_styles

    styled_df = computed_df.style.format({
        "Buy Price": "${:,.2f}",
        "Current Market": "${:,.2f}",
        "Sell Price": "${:,.2f}"
    }).apply(highlight_status, axis=1)
    
    # 4. Render the Unified Interactive Data Grid
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
    
    # 5. Handle user edits back to the raw source data structures
    # If the user changed a cell value, update the timestamp and run a rerun to force data recalculation
    current_raw = st.session_state.raw_portfolio.copy()
    has_changed = False
    
    for idx in range(len(response_editor)):
        # Read what's currently in the interactive layout
        edited_buy = response_editor.iloc[idx]['Buy Price']
        edited_sell = response_editor.iloc[idx]['Sell Price']
        
        # Match it against our backup raw list
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
