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
st.markdown("Upload your structural portfolio parameters to match current public market equity values against buy limits and take-profit targets.")

# --- SIDEBAR: USER INSTRUCTIONS ---
with st.sidebar:
    st.header("📋 Template Requirements")
    st.markdown("""
    Ensure your uploaded Excel spreadsheet (`.xlsx`) contains the following case-sensitive column headers in the first row:
    * **Ticker** (e.g., `AN`, `PAG`, `LAD`, `MSFT`)
    * **Buy Price** (Your maximum entry target)
    * **Sell Price** (Your minimum profit target)
    """)
    st.write("---")
    st.caption("Data sourced via Yahoo Finance API. Market data delay may vary.")

# --- FILE UPLOADER WIDGET ---
uploaded_file = st.file_uploader("Drag and drop your asset watchlist Excel file here", type=["xlsx"])

if uploaded_file is not None:
    try:
        # Read the Excel sheet
        raw_df = pd.read_excel(uploaded_file)
        
        # Standardize column headers
        raw_df.columns = [str(col).strip().title() for col in raw_df.columns]
        
        required_cols = ['Ticker', 'Buy Price', 'Sell Price']
        if not all(col in raw_df.columns for col in required_cols):
            st.error(f"Mapping Error: Spreadsheet must contain these exact columns: {required_cols}")
        else:
            # Process calculations
            data = []
            buy_alerts = 0
            sell_alerts = 0
            
            with st.spinner("Querying real-time market data..."):
                for _, row in raw_df.iterrows():
                    ticker = str(row['Ticker']).strip().upper()
                    buy_target = float(row['Buy Price'])
                    sell_target = float(row['Sell Price'])
                    
                    try:
                        stock = yf.Ticker(ticker)
                        info = stock.history(period="1d")
                        if not info.empty:
                            current_price = round(info['Close'].iloc[-1], 2)
                            
                            if current_price <= buy_target:
                                status = "🚨 BUY ZONE"
                                buy_alerts += 1
                            elif current_price >= sell_target:
                                status = "💰 PROFIT ZONE"
                                sell_alerts += 1
                            else:
                                status = "Hold / Monitor"
                                
                            data.append({
                                "Ticker": ticker,
                                "Buy Target": buy_target,
                                "Current Market": current_price,
                                "Sell Target": sell_target,
                                "Status": status
                            })
                    except Exception:
                        pass
            
            df_results = pd.DataFrame(data)
            
            # --- RENDER KPI METRIC CARDS ---
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Total Assets Tracked", value=len(df_results))
            with col2:
                st.metric(label="🚨 Buy Targets Triggered", value=buy_alerts)
            with col3:
                st.metric(label="💰 Profit Horizons Reached", value=sell_alerts)
                
            st.write("---")
            
            # --- DATA TABLE FORMATTING & HIGHLIGHTING ---
            def highlight_status(row):
                css_styles = [''] * len(row)
                if row['Status'] == "🚨 BUY ZONE":
                    # Muted emerald green background for buy execution alerts
                    css_styles = ['background-color: rgba(46, 204, 113, 0.15); color: #2ecc71; font-weight: bold;'] * len(row)
                elif row['Status'] == "💰 PROFIT ZONE":
                    # Muted gold background for liquidating/taking profit
                    css_styles = ['background-color: rgba(241, 196, 15, 0.15); color: #f1c40f; font-weight: bold;'] * len(row)
                return css_styles

            # Format the numbers as currency dynamically inside the styled grid
            styled_df = df_results.style.format({
                "Buy Target": "${:,.2f}",
                "Current Market": "${:,.2f}",
                "Sell Target": "${:,.2f}"
            }).apply(highlight_status, axis=1)
            
            # Display responsive dashboard table
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            
    except Exception as e:
        st.error(f"System execution failure: {e}")
else:
    st.info("💡 App is live. Awaiting file execution. Upload your asset tracking workbook to populate live market valuations.")
