import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="INF2003 Dashboard", layout="wide")
st.title("INF2003 Database Dashboard")
st.markdown("### MongoDB Revenue Analytics")

FLASK_BASE_URL = "http://127.0.0.1:5000/api"

def fetch_and_display(url, success_message):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data:
                st.success(success_message)
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Query executed successfully, but no matching documents were found.")
        else:
            st.error(f"API Error. Status Code: {response.status_code}")
    except Exception as e:
        st.error(f"Could not connect to the Flask API. Is your backend running?\nError: {e}")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("1. View Raw JSON Data"):
        fetch_and_display(f"{FLASK_BASE_URL}/nosql/revenue", "Raw data fetched successfully!")

with col2:
    if st.button("2. Revenue by Country"):
        fetch_and_display(f"{FLASK_BASE_URL}/revenue/country", "Country aggregation executed successfully!")

with col3:
    # Match your actual creator_tier value ('large')
    selected_tier = st.selectbox("Select Creator Tier:", ["large", "medium", "small"])
    if st.button("3. Filter by Creator Tier"):
        fetch_and_display(f"{FLASK_BASE_URL}/videos/tier/{selected_tier}", f"Filtered by tier '{selected_tier}' successfully!")

with col4:
    if st.button("4. Category Breakdown"):
        fetch_and_display(f"{FLASK_BASE_URL}/analytics/categories", "Category breakdown calculated successfully!")