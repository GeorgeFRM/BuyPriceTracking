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
    st.caption("Data sourced via Yahoo Finance API. Tracking consecutive historical days closed below target.")

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
            data = []
            buy_alerts = 0
            sell_alerts = 0
            
            with st.spinner("Querying real-time and historical market data..."):
                for _, row in raw_df.iterrows():
                    ticker = str(row['Ticker']).strip().upper()
                    buy_target = float(row['Buy Price'])
                    sell_target = float(row['Sell Price'])
                    
                    try:
                        stock = yf.Ticker(ticker)
                        
                        # Fetch up to 6 months of historical daily close data to calculate the streak length
                        hist = stock.history(period="6mo")
                        
                        if not hist.empty:
                            # Current market price is the latest closing price
                            current_price = round(hist['Close'].iloc[-1], 2)
                            
                            # --- CALCULATE CONSECUTIVE DAYS BELOW BUY TARGET ---
                            days_below = 0
                            if current_price <= buy_target:
                                # Reverse the historical list to count backward from today
                                historical_closes = hist['Close'].iloc[::-1]
                                for close_price in historical_closes:
                                    if close_price <= buy_target:
                                        days_below += 1
                                    else:
                                        break # Streak is broken if it was above target on that day
                            
                            # Determine Action Status and formatting output strings
                            if current_price <= buy_target:
                                status = "Buy"
                                buy_alerts += 1
                                days_display = f"{days_below} days" if days_below > 1 else "1 day"
                            elif current_price >= sell_target:
                                status = "Profit Zone"
                                sell_alerts += 1
                                days_display = "" # Leave blank if above buy price
                            else:
                                status = "Hold / Monitor"
                                days_display = "" # Leave blank if above buy price
                                
                            data.append({
                                "Ticker": ticker,
                                "Buy Target": buy_target,
                                "Current Market": current_price,
                                "Sell Target": sell_target,
                                "Status": status,
                                "Days Below Buy Target": days_display
                            })
                    except Exception:
                        pass
            
            df_results = pd.DataFrame(data)
            
            # --- RENDER KPI METRIC CARDS ---
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Total Assets Tracked", value=len(df_results))
            with col2:
                st.metric(label="Buy Targets Triggered", value=buy_alerts)
            with col3:
                st.metric(label="Profit Horizons Reached", value=sell_alerts)
                
            st.write("---")
            
            # --- DATA TABLE FORMATTING & HIGHLIGHTING ---
            def highlight_status(row):
                css_styles = [''] * len(row)
                if row['Status'] == "Buy":
                    # Clean emerald green background applied strictly to "Buy" rows
                    css_styles = ['background-color: rgba(46, 204, 113, 0.18); color: #2ecc71; font-weight: bold;'] * len(row)
                return css_styles

            # Format the numeric values as currency inside the grid layout
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
