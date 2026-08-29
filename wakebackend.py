import time

def wake_and_load_inventory(max_retries=10, delay_seconds=5):
    """Pings the Render backend to wake it from sleep and loads inventory."""
    url = f"{RENDER_API_URL}/items"
    
    with st.spinner("Waking up backend server... This may take up to 30 seconds on cold start."):
        for attempt in range(1, max_retries + 1):
            try:
                # Short 5-second timeout per ping attempt
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    st.session_state["inventory_items"] = resp.json()
                    return True
            except requests.exceptions.RequestException:
                # Backend is still booting up; wait before retrying
                pass
            
            time.sleep(delay_seconds)
            
    st.error("Backend server took too long to wake up. Please click 'Refresh' to try again.")
    return False
