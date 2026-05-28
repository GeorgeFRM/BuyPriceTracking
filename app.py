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
st.markdown("Upload your asset watchlist Excel file, or edit targets directly in the table below. Changes are saved for your current session.")

# --- SIDEBAR: USER INSTRUCTIONS ---
with st.sidebar:
    st.header("📋 Template Requirements")
    st.markdown("""
    If uploading a file (`.xlsx`), ensure it contains these headers in the first row:
    * **Ticker** * **Buy Price** * **Sell Price** """)
    st.write("---")
    st.caption("Double-click any cell in the 'Buy Price' or 'Sell Price' columns to update targets instantly on-screen.")

# --- FILE UPLOADER WIDGET ---
uploaded_file = st.file_uploader("Drag and drop your asset watchlist Excel file here to initialize data", type=["xlsx"])

# --- SESSION STATE INITIALIZATION ---
# This holds the active dataset in memory so user edits persist
if 'master_df' not in st.session_state:
    st.session_state.master_df = None

# If a new file is uploaded, parse it and build the initial session state dataframe
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
            # Save initialized data to session memory
            st.session_state.master_df = pd.DataFrame(initial_data)
    except Exception as e:
        st.error(f"Error parsing uploaded file: {e}")

# --- CORE PROCESSING AND INTERACTIVE GRID ---
if st.session_state.master_df is not None:
    
    # 1. Capture direct screen edits from the data editor widget
    # We display a temporary editor UI and freeze editing on non-editable columns
    edited_df = st.data_editor(
        st.session_state.master_df,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
            "Buy Price": st.column_config.NumberColumn("Buy Price (Edit)", min_value=0.0, format="$%.2f"),
            "Sell Price": st.column_config.NumberColumn("Sell Price (Edit)", min_value=0.0, format="$%.2f"),
            "Last Updated": st.column_config.TextColumn("Last Updated", disabled=True)
        },
        use_container_width=True,
        hide_index=True,
        key="watchlist_editor"
    )

    # 2. Check if the user changed a cell. If yes, update timestamps and save back to Master memory
    if not edited_df.equals(st.session_state.master_df):
        # Identify which row index was modified
        for i in range(len(edited_df)):
            old_row = st.session_state.master_df.iloc[i]
            new_row = edited_df.iloc[i]
            if (old_row['Buy Price'] != new_row['Buy Price']) or (old_row['Sell Price'] != new_row['Sell Price']):
                edited_df.at[i, 'Last Updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        st.session_state.master_df = edited_df
        st.rerun()

    # 3. Calculate Live Market Metrics based on the active Master memory
    processed_data = []
    buy_alerts = 0
    sell_alerts = 0
    
    with st.spinner("Recalculating public market valuations..."):
        for _, row in st.session_state.master_df.iterrows():
            ticker = row['Ticker']
            buy_target = row['Buy Price']
            sell_target = row['Sell Price']
            last_updated = row['Last Updated']
            
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="6mo")
                
                if not hist.empty:
                    current_price = round(hist['Close'].iloc[-1], 2)
                    
                    # Calculate streak duration for buy targets
                    days_below = 0
                    if current_price <= buy_target:
                        historical_closes = hist['Close'].iloc[::-1]
                        for close_price in historical_closes:
                            if close_price <= buy_target:
                                days_below += 1
                            else:
                                break
                    
                    # Map structural logic flags
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
                        "Buy Target": buy_target,
                        "Current Market": current_price,
                        "Sell Target": sell_target,
                        "Status": status,
                        "Days Below Buy Target": days_display,
                        "Last Updated": last_updated
                    })
            except Exception:
                # Fallback if a ticker fails to fetch
                processed_data.append({
                    "Ticker": ticker, "Buy Target": buy_target, "Current Market": 0.0,
                    "Sell Target": sell_target, "Status": "Error Fetching Data", "Days Below Buy Target": "", "Last Updated": last_updated
                })

    df_results = pd.DataFrame(processed_data)
    
    # 4. Render Metric Summary Overview
    st.write("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Assets Tracked", value=len(df_results))
    with col2:
        st.metric(label="Buy Targets Triggered", value=buy_alerts)
    with col3:
        st.metric(label="Profit Horizons Reached", value=sell_alerts)
    st.write("---")
    
    # 5. Styling Layer: Highlights "Buy" rows clean green with no emoji
    def highlight_status(row):
        css_styles = [''] * len(row)
        if row['Status'] == "Buy":
            css_styles = ['background-color: rgba(46, 204, 113, 0.18); color: #2ecc71; font-weight: bold;'] * len(row)
        return css_styles

    styled_df = df_results.style.format({
        "Buy Target": "${:,.2f}",
        "Current Market": "${:,.2f}",
        "Sell Target": "${:,.2f}"
    }).apply(highlight_status, axis=1)
    
    # Render final evaluation matrix dashboard
    st.subheader("📊 Output Valuation Grid")
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

else:
    st.info("💡 App is live. Awaiting file execution. Upload your asset tracking workbook to populate live market valuations.")
