import os
import base64
from datetime import datetime
import requests
import streamlit as st

RENDER_API_URL = os.getenv("RENDER_API_URL", "https://expiry-date-tracker.onrender.com")

st.set_page_config(page_title="Expiry Scanner", page_icon="🏷️", layout="centered")
st.title("🏷️ Expiry Scanner")

# --- Initialize Session State ---
if "scanned_name" not in st.session_state:
    st.session_state["scanned_name"] = ""
if "scanned_date_type" not in st.session_state:
    st.session_state["scanned_date_type"] = "Expiry"
if "scanned_date" not in st.session_state:
    st.session_state["scanned_date"] = ""
if "captured_photos" not in st.session_state:
    st.session_state["captured_photos"] = []
if "inventory_items" not in st.session_state:
    st.session_state["inventory_items"] = None
if "camera_key" not in st.session_state:
    st.session_state["camera_key"] = 0

def load_inventory():
    try:
        resp = requests.get(f"{RENDER_API_URL}/items", timeout=10)
        if resp.status_code == 200:
            st.session_state["inventory_items"] = resp.json()
    except Exception as ex:
        st.error(f"Failed to fetch inventory: {ex}")

# Fetch inventory once on startup
if st.session_state["inventory_items"] is None:
    load_inventory()

# --- Settings & Threshold ---
alert_limit = st.number_input("Notify (X) days before date", min_value=0, value=3, step=1)
st.divider()

# --- Section 2: Scan & Add Item ---
st.subheader("Add New Item")

# Inject JS override to enforce environment (rear) camera facing mode on st.camera_input

# 1. Custom JS/HTML Live Camera Component
camera_html = """
<div style="text-align: center; font-family: sans-serif;">
    <video id="webcam" autoplay playsinline style="width: 100%; max-width: 500px; border-radius: 10px; background: #000;"></video>
    <br>
    <button id="snap" style="margin-top: 10px; padding: 10px 20px; font-size: 16px; background-color: #ff4b4b; color: white; border: none; border-radius: 5px; cursor: pointer; width: 100%; max-width: 500px;">
        📸 Snap Photo
    </button>
    <canvas id="canvas" style="display:none;"></canvas>
</div>

<script>
    const video = document.getElementById('webcam');
    const canvas = document.getElementById('canvas');
    const snapBtn = document.getElementById('snap');

    // Request continuous rear camera stream
    navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: { ideal: "environment" } } 
    })
    .then(stream => {
        video.srcObject = stream;
    })
    .catch(err => {
        console.error("Camera access error:", err);
    });

    snapBtn.addEventListener('click', () => {
        const context = canvas.getContext('2d');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, video.videoWidth, video.videoHeight);
        
        // Convert captured frame to base64 JPEG
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        
        // Post frame to Streamlit's internal iframe listener
        window.parent.postMessage({
            type: 'streamlit:setComponentValue',
            value: dataUrl
        }, '*');
    });
</script>
"""

# Render custom live camera widget
captured_b64 = st.components.v1.html(camera_html, height=360)

# Process snap event without reloading/resetting the camera stream
if captured_b64:
    # Remove metadata header (e.g. "data:image/jpeg;base64,")
    if "," in captured_b64:
        header, encoded = captured_b64.split(",", 1)
        img_bytes = base64.b64decode(encoded)
    else:
        img_bytes = base64.b64decode(captured_b64)
        
    # Append unique frame to queue
    if "last_snap" not in st.session_state or st.session_state["last_snap"] != captured_b64:
        st.session_state["captured_photos"].append(img_bytes)
        st.session_state["last_snap"] = captured_b64
        st.toast(f"Photo added to queue! Total: {len(st.session_state['captured_photos'])}", icon="📸")
        st.rerun()

# 2. Photo Queue & Action Buttons
if st.session_state["captured_photos"]:
    st.markdown(f"**Captured Photos Queue ({len(st.session_state['captured_photos'])}):**")
    
    thumb_cols = st.columns(6)
    for idx, photo in enumerate(st.session_state["captured_photos"]):
        with thumb_cols[idx % 6]:
            st.image(photo, width=100)

    btn_col1, btn_col2 = st.columns([3, 1])
    with btn_col1:
        if st.button("🤖 Analyze Queue with LLM", use_container_width=True, type="secondary"):
            images_b64 = [base64.b64encode(img).decode("utf-8") for img in st.session_state["captured_photos"]]
            try:
                with st.spinner("Analyzing photos with Gemini LLM..."):
                    resp = requests.post(f"{RENDER_API_URL}/analyze-label", json={"images_b64": images_b64}, timeout=30)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state["scanned_name"] = data.get("item_name", "")
                        st.session_state["scanned_date_type"] = data.get("date_type", "Expiry")
                        st.session_state["scanned_date"] = data.get("expiry_date", "") or ""
                        st.toast("Label analyzed successfully!", icon="✨")
                    elif resp.status_code == 429:
                        st.error("Rate limit reached. Please wait a few seconds.")
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
date_type_val = st.radio("Date Type", ["Expiry", "Best Before"], index=0 if st.session_state["scanned_date_type"] == "Expiry" else 1, horizontal=True)
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
                st.session_state["scanned_date_type"] = "Expiry"
                st.session_state["scanned_date"] = ""
                st.session_state["captured_photos"] = []
                load_inventory()
                st.rerun()
            elif resp.status_code == 429:
                st.error("Too Many Requests: Wait 5 seconds before trying again.")
            else:
                st.error(f"Failed to add item ({resp.status_code}): {resp.text}")
        except Exception as ex:
            st.error(f"Connection error: {ex}")

st.divider()

# --- Section 3: Tracked Inventory ---
col_inv_header, col_inv_ref = st.columns([4, 1])
with col_inv_header:
    st.subheader("Tracked Inventory")
with col_inv_ref:
    if st.button("🔄 Refresh"):
        load_inventory()
        st.rerun()

rows = st.session_state.get("inventory_items")

if rows is not None:
    today = datetime.now().date()

    if not rows:
        st.info("No items in inventory.")
    else:
        for item in rows:
            item_id = item["id"]
            name = item["name"]
            d_type = item.get("date_type") or "Expiry"
            exp_str = item.get("expiry_date", "")
            
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                days_left = (exp_date - today).days
            except (ValueError, TypeError):
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
                        try:
                            del_resp = requests.delete(f"{RENDER_API_URL}/items/{item_id}", timeout=10)
                            if del_resp.status_code in (200, 204):
                                st.toast(f"Deleted {name}", icon="🗑️")
                                load_inventory()
                                st.rerun()
                        except Exception as ex:
                            st.error(f"Delete error: {ex}")
else:
    st.info("Loading inventory...")