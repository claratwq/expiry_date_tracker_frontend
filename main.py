import os
import base64
from datetime import datetime
import requests
import streamlit as st

RENDER_API_URL = os.getenv("RENDER_API_URL", "https://expiry-date-tracker.onrender.com")

st.set_page_config(page_title="Expiry Scanner", page_icon="🏷️", layout="centered")
st.title("🏷️ Expiry Scanner")

if "scanned_name" not in st.session_state:
    st.session_state["scanned_name"] = ""
if "scanned_date_type" not in st.session_state:
    st.session_state["scanned_date_type"] = "Best Before"
if "scanned_date" not in st.session_state:
    st.session_state["scanned_date"] = ""

def process_llm_vision(files):
    images_b64 = [base64.b64encode(f.getvalue()).decode("utf-8") for f in files]
    
    try:
        with st.spinner("Analyzing photos with Gemini LLM..."):
            resp = requests.post(f"{RENDER_API_URL}/analyze-label", json={"images_b64": images_b64}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                st.session_state["scanned_name"] = data.get("item_name", "")
                st.session_state["scanned_date_type"] = data.get("date_type", "Best Before")
                st.session_state["scanned_date"] = data.get("expiry_date", "") or ""
                st.toast("Label analyzed successfully!", icon="✨")
            else:
                st.error(f"Analysis failed (Status {resp.status_code})")
    except Exception as ex:
        st.error(f"Request failed: {ex}")

# --- Settings & Threshold ---
alert_limit = st.number_input("Notify (X) days before date", min_value=0, value=3, step=1)
st.divider()

# --- Section 2: Scan & Add Item ---
# --- Initialize Session State for Captured Queue ---
if "captured_photos" not in st.session_state:
    st.session_state["captured_photos"] = []

st.subheader("Add New Item")

# Live Camera Viewfinder
camera_photo = st.camera_input("Take a photo of product or label")

if camera_photo:
    img_bytes = camera_photo.getvalue()
    # Prevent duplicate appends when Streamlit re-executes
    if not st.session_state["captured_photos"] or st.session_state["captured_photos"][-1] != img_bytes:
        st.session_state["captured_photos"].append(img_bytes)
        st.toast(f"Photo captured! Total photos: {len(st.session_state['captured_photos'])}", icon="📸")

# Photo Queue & Action Buttons
if st.session_state["captured_photos"]:
    st.markdown(f"**Captured Photos Queue ({len(st.session_state['captured_photos'])}):**")
    
    # Render thumbnails in a grid
    cols = st.columns(min(len(st.session_state["captured_photos"]), 4))
    for idx, photo in enumerate(st.session_state["captured_photos"]):
        with cols[idx % 4]:
            st.image(photo, use_container_width=True)

    btn_col1, btn_col2 = st.columns([3, 1])
    with btn_col1:
        if st.button("🤖 Analyze Queue with LLM", use_container_width=True, type="secondary"):
            # Pass list of byte arrays to process function
            images_b64 = [base64.b64encode(img).decode("utf-8") for img in st.session_state["captured_photos"]]
            try:
                with st.spinner("Analyzing photos with Gemini LLM..."):
                    resp = requests.post(f"{RENDER_API_URL}/analyze-label", json={"images_b64": images_b64}, timeout=30)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state["scanned_name"] = data.get("item_name", "")
                        st.session_state["scanned_date_type"] = data.get("date_type", "Best Before")
                        st.session_state["scanned_date"] = data.get("expiry_date", "") or ""
                        st.toast("Label analyzed successfully!", icon="✨")
                    else:
                        st.error(f"Analysis failed (Status {resp.status_code})")
            except Exception as ex:
                st.error(f"Request failed: {ex}")
                
    with btn_col2:
        if st.button("🗑️ Clear Queue", use_container_width=True):
            st.session_state["captured_photos"] = []
            st.rerun()

# Item Entry Form
name_val = st.text_input("Item Name", value=st.session_state["scanned_name"], placeholder="e.g., HL Chocolate Milk")
date_type_val = st.radio("Date Type", ["Best Before", "Expiry"], index=0 if st.session_state["scanned_date_type"] == "Best Before" else 1, horizontal=True)
date_val = st.text_input("Date (YYYY-MM-DD)", value=st.session_state["scanned_date"], placeholder="e.g., 2026-08-15")

if st.button("➕ SAVE ITEM TO INVENTORY", type="primary", use_container_width=True):
    if not name_val or not date_val:
        st.warning("Please provide both item name and date.")
    else:
        try:
            resp = requests.post(
                f"{RENDER_API_URL}/items",
                json={
                    "name": name_val.strip(),
                    "date_type": date_type_val,
                    "expiry_date": date_val.strip()
                },
                timeout=10
            )
            if resp.status_code == 201:
                st.success(f"Added '{name_val}' successfully!")
                st.session_state["scanned_name"] = ""
                st.session_state["scanned_date_type"] = "Best Before"
                st.session_state["scanned_date"] = ""
                st.session_state["captured_photos"] = []  # Clear photo queue on save
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"Failed to add item: {resp.text}")
        except Exception as ex:
            st.error(f"Connection error: {ex}")
st.divider()

# --- Section 3: Tracked Inventory ---
@st.cache_data(ttl=60)
def fetch_inventory_items(api_url):
    resp = requests.get(f"{api_url}/items", timeout=10)
    return resp.status_code, resp.json() if resp.status_code == 200 else resp.text

col_inv_header, col_inv_ref = st.columns([4, 1])
with col_inv_header:
    st.subheader("Tracked Inventory")
with col_inv_ref:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

try:
    status_code, response_data = fetch_inventory_items(RENDER_API_URL)
    
    if status_code == 200:
        rows = response_data
        today = datetime.now().date()

        if not rows:
            st.info("No items in inventory.")
        else:
            for item in rows:
                item_id = item["id"]
                name = item["name"]
                d_type = item.get("date_type", "Best Before")
                exp_str = item["expiry_date"]
                
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    days_left = (exp_date - today).days
                except ValueError:
                    days_left = 0

                is_urgent = days_left <= alert_limit
                
                with st.container(border=True):
                    c1, c2, c3 = st.columns([1, 4, 1])
                    with c1:
                        st.markdown("⚠️" if is_urgent else "✅")
                    with c2:
                        st.markdown(f"**{name}**")
                        lbl = "Expired!" if days_left < 0 else f"{days_left} days left"
                        st.caption(f"{lbl} ({d_type}: {exp_str})")
                    with c3:
                        if st.button("🗑️", key=f"del_{item_id}"):
                            del_resp = requests.delete(f"{RENDER_API_URL}/items/{item_id}", timeout=10)
                            if del_resp.status_code in (200, 204):
                                st.toast(f"Deleted {name}", icon="🗑️")
                                st.cache_data.clear()
                                st.rerun()
except Exception as ex:
    st.error(f"Could not connect to backend API: {ex}")