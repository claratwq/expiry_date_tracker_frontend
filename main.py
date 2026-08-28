import os
import base64
from datetime import datetime
import requests
import streamlit as st

# Backend API Configuration
RENDER_API_URL = os.getenv("RENDER_API_URL", "https://expiry-date-tracker.onrender.com")

st.set_page_config(page_title="Expiry Scanner", page_icon="🏷️", layout="centered")

st.title("🏷️ Expiry Scanner")

# Initialize Session State Variables
if "scanned_name" not in st.session_state:
    st.session_state["scanned_name"] = ""
if "scanned_date" not in st.session_state:
    st.session_state["scanned_date"] = ""

# --- Helper Functions ---
def process_ocr(image_bytes, scan_type):
    b64_str = base64.b64encode(image_bytes).decode("utf-8")
    endpoint = f"{RENDER_API_URL}/ocr/name" if scan_type == "name" else f"{RENDER_API_URL}/ocr/date"
    
    try:
        with st.spinner(f"Processing {scan_type} via OCR..."):
            resp = requests.post(endpoint, json={"image_b64": b64_str}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if scan_type == "name":
                    st.session_state["scanned_name"] = data.get("name", "")
                    st.toast(f"Scanned Name: {st.session_state['scanned_name']}", icon="✅")
                else:
                    st.session_state["scanned_date"] = data.get("expiry_date", "")
                    st.toast(f"Scanned Date: {st.session_state['scanned_date']}", icon="✅")
            else:
                st.error(f"OCR Error ({resp.status_code}): Could not process image.")
    except Exception as ex:
        st.error(f"OCR Request Failed: {ex}")

# --- Section 1: Settings & Threshold ---
alert_limit = st.number_input("Notify (X) days before expiry", min_value=0, value=3, step=1)

st.divider()

# --- Section 2: Scan & Add Item ---
st.subheader("Add New Item")

# Camera / Image Input
camera_file = st.camera_input("Snap label or expiry date")

if camera_file:
    col_ocr1, col_ocr2 = st.columns(2)
    img_bytes = camera_file.getvalue()
    
    with col_ocr1:
        if st.button("🔍 Scan Name from Photo", use_container_width=True):
            process_ocr(img_bytes, "name")
            
    with col_ocr2:
        if st.button("📅 Scan Date from Photo", use_container_width=True):
            process_ocr(img_bytes, "date")

# Item Entry Form
name_val = st.text_input("Item Name", value=st.session_state["scanned_name"], placeholder="e.g., Whole Milk")
date_val = st.text_input("Expiry Date (YYYY-MM-DD)", value=st.session_state["scanned_date"], placeholder="e.g., 2026-08-15")

if st.button("➕ SAVE ITEM TO INVENTORY", type="primary", use_container_width=True):
    if not name_val or not date_val:
        st.warning("Please provide both item name and expiry date.")
    else:
        try:
            resp = requests.post(
                f"{RENDER_API_URL}/items",
                json={"name": name_val.strip(), "expiry_date": date_val.strip()},
                timeout=10
            )
            if resp.status_code == 201:
                st.success(f"Added '{name_val}' successfully!")
                # Reset inputs
                st.session_state["scanned_name"] = ""
                st.session_state["scanned_date"] = ""
                st.rerun()
            else:
                st.error(f"Failed to add item ({resp.status_code}): {resp.text}")
        except Exception as ex:
            st.error(f"Connection error: {ex}")

st.divider()

# --- Section 3: Tracked Inventory ---
st.subheader("Tracked Inventory")

try:
    resp = requests.get(f"{RENDER_API_URL}/items", timeout=10)
    if resp.status_code == 200:
        rows = resp.json()
        today = datetime.now().date()

        if not rows:
            st.info("No items in inventory.")
        else:
            for item in rows:
                item_id = item["id"]
                name = item["name"]
                exp_str = item["expiry_date"]
                
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    days_left = (exp_date - today).days
                except ValueError:
                    days_left = 0

                is_urgent = days_left <= alert_limit
                
                # Card Container
                with st.container(border=True):
                    c1, c2, c3 = st.columns([1, 4, 1])
                    
                    with c1:
                        if is_urgent:
                            st.markdown("⚠️")
                        else:
                            st.markdown("✅")
                            
                    with c2:
                        st.markdown(f"**{name}**")
                        if days_left < 0:
                            st.caption(f"🚨 Expired! ({exp_str})")
                        else:
                            st.caption(f"{days_left} days left (Expires: {exp_str})")
                            
                    with c3:
                        if st.button("🗑️", key=f"del_{item_id}"):
                            try:
                                del_resp = requests.delete(f"{RENDER_API_URL}/items/{item_id}", timeout=10)
                                if del_resp.status_code == 200:
                                    st.toast(f"Deleted {name}", icon="🗑️")
                                    st.rerun()
                            except Exception as ex:
                                st.error(f"Delete error: {ex}")
    else:
        st.error(f"Failed to load items. Server returned status {resp.status_code}")
except Exception as ex:
        st.error(f"Could not connect to backend API: {ex}")