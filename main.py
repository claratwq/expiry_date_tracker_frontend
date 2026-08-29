import os
import base64
from datetime import datetime
import requests
import streamlit as st
import streamlit.components.v1 as components

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
if "camera_key" not in st.session_state:
    st.session_state["camera_key"] = 0

# --- Settings & Threshold ---
alert_limit = st.number_input("Notify (X) days before date", min_value=0, value=3, step=1)
st.divider()

# --- Section 2: Scan & Add Item ---
st.subheader("Add New Item")

# Dynamic Key Forces Camera Viewfinder to Reset After Each Snapshot


# Injected HTML/JS to stream back camera directly
def back_camera_input(key=None):
    html_code = """
    <div style="display: flex; flex-direction: column; align-items: center; gap: 10px; font-family: sans-serif;">
        <video id="video" autoplay playsinline style="width: 100%; max-width: 380px; border-radius: 10px; border: 2px solid #333; background: #000;"></video>
        <button id="snap-btn" style="width: 100%; max-width: 380px; padding: 12px; font-size: 16px; font-weight: bold; color: white; background-color: #FF4B4B; border: none; border-radius: 8px; cursor: pointer;">
            📸 Snap Photo (Rear Camera)
        </button>
        <canvas id="canvas" style="display:none;"></canvas>
    </div>

    <script>
        const video = document.getElementById('video');
        const canvas = document.getElementById('canvas');
        const snapBtn = document.getElementById('snap-btn');

        // Request Rear/Environment Camera
        navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
            audio: false
        }).then(stream => {
            video.srcObject = stream;
        }).catch(err => {
            console.error("Camera access error:", err);
        });

        // Function to notify Streamlit of new component value
        function sendToStreamlit(value) {
            window.parent.postMessage({
                isStreamlitMessage: true,
                type: "streamlit:setComponentValue",
                value: value
            }, "*");
        }

        snapBtn.addEventListener('click', () => {
            const context = canvas.getContext('2d');
            canvas.width = video.videoWidth || 640;
            canvas.height = video.videoHeight || 480;
            context.drawImage(video, 0, 0, canvas.width, canvas.height);
            
            // Get base64 string (without the data:image/jpeg;base64, prefix)
            const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
            const rawB64 = dataUrl.split(',')[1];
            
            sendToStreamlit(rawB64);
        });
    </script>
    """
    return components.html(html_code, height=320)

# --- Section 2: Scan & Add Item ---
st.subheader("Add New Item")

# Render custom back-camera component
camera_data_b64 = back_camera_input(key=f"cam_{st.session_state['camera_key']}")

# When a photo is snapped, camera_data_b64 will contain the raw base64 string
if camera_data_b64 is not None:
    # Decode base64 directly into raw bytes
    img_bytes = base64.b64decode(camera_data_b64)
    
    # Add bytes to queue and increment camera_key to reset video stream state
    st.session_state["captured_photos"].append(img_bytes)
    st.session_state["camera_key"] += 1
    st.toast(f"Photo added to queue! Total: {len(st.session_state['captured_photos'])}", icon="📸")
    st.rerun()

# Photo Queue & Action Buttons
# Render small 100px thumbnails in a scannable row
if st.session_state["captured_photos"]:
    st.markdown(f"**Captured Photos Queue ({len(st.session_state['captured_photos'])}):**")
    
    # Create up to 6 small thumbnail columns
    thumb_cols = st.columns(6)
    for idx, photo in enumerate(st.session_state["captured_photos"]):
        with thumb_cols[idx % 6]:
            st.image(photo, width=100) # Sets explicit width in pixels

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