import os
import base64
from datetime import datetime
import requests
import flet as ft

# Your actual Flask Backend API URL
RENDER_API_URL = os.getenv("RENDER_API_URL", "https://expiry-date-tracker.onrender.com")

def main(page: ft.Page):
    page.title = "Expiry Scanner"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 16

    # --- Inputs & Controls ---
    name_input = ft.TextField(label="Item Name", hint_text="e.g., Whole Milk", expand=True)
    date_input = ft.TextField(label="Expiry Date (YYYY-MM-DD)", hint_text="e.g., 2026-08-15", expand=True)
    threshold_input = ft.TextField(value="3", label="Notify (X) days before expiry", keyboard_type=ft.KeyboardType.NUMBER, width=250)
    items_list_view = ft.ListView(expand=True, spacing=10)
    
    status_label = ft.Text("Ready.", color=ft.Colors.GREY_600)

    # --- OCR Handling ---
    def process_remote_ocr(image_bytes, scan_type):
        b64_str = base64.b64encode(image_bytes).decode("utf-8")
        endpoint = f"{RENDER_API_URL}/ocr/name" if scan_type == "name" else f"{RENDER_API_URL}/ocr/date"
        
        status_label.value = f"Processing {scan_type} via Cloud API..."
        status_label.color = ft.Colors.AMBER_800
        page.update()

        try:
            resp = requests.post(endpoint, json={"image_b64": b64_str}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if scan_type == "name":
                    name_input.value = data.get("name", "")
                    status_label.value = f"Scanned Name: {data.get('name', '')}"
                else:
                    date_input.value = data.get("expiry_date", "")
                    status_label.value = f"Scanned Date: {data.get('expiry_date', '')}"
                status_label.color = ft.Colors.GREEN_700
            else:
                status_label.value = f"Error processing image (Status {resp.status_code})."
                status_label.color = ft.Colors.RED_600
        except Exception as ex:
            status_label.value = f"Fetch Error: {type(ex).__name__} - {ex}"
            status_label.color = ft.Colors.RED_600
        page.update()

    def on_picker_result(e: ft.FilePickerResultEvent, scan_type: str):
        if not e.files or len(e.files) == 0:
            return
        
        uf = e.files[0]
        if hasattr(uf, "bytes") and uf.bytes:
            process_remote_ocr(uf.bytes, scan_type)
        elif hasattr(uf, "path") and uf.path:
            with open(uf.path, "rb") as f:
                process_remote_ocr(f.read(), scan_type)

    file_picker = ft.FilePicker()
    page.services.append(file_picker) if hasattr(page, "services") else None

    async def trigger_scan_name(e):
        file_picker.on_result = lambda res: on_picker_result(res, "name")
        await file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)

    async def trigger_scan_date(e):
        file_picker.on_result = lambda res: on_picker_result(res, "date")
        await file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)

    # --- API Inventory Handlers ---
    def handle_add_item(e):
        item_name = name_input.value.strip() or "Unnamed Item"
        date_str = date_input.value.strip()

        try:
            resp = requests.post(
                f"{RENDER_API_URL}/items",
                json={"name": item_name, "expiry_date": date_str},
                timeout=10
            )
            if resp.status_code == 201:
                name_input.value = ""
                date_input.value = ""
                status_label.value = f"Added '{item_name}'"
                status_label.color = ft.Colors.GREEN_700
                refresh_item_list()
        except Exception as ex:
            status_label.value = f"Failed to add item: {ex}"
            status_label.color = ft.Colors.RED_600
            page.update()

    def handle_delete_item(item_id):
        try:
            requests.delete(f"{RENDER_API_URL}/items/{item_id}", timeout=10)
            refresh_item_list()
        except Exception as ex:
            print(f"Delete error: {ex}")

    def refresh_item_list(e=None):
        items_list_view.controls.clear()
        today = datetime.now().date()
        
        try:
            alert_limit = int(threshold_input.value or "3")
        except ValueError:
            alert_limit = 3

        url = f"{RENDER_API_URL}/items"

        try:
            resp = requests.get(url, timeout=10)
            
            if resp.status_code == 200:
                rows = resp.json()
                for item in rows:
                    item_id = item["id"]
                    name = item["name"]
                    exp_str = item["expiry_date"]
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    days_left = (exp_date - today).days

                    is_urgent = days_left <= alert_limit
                    status_text = f"Expired! ({exp_str})" if days_left < 0 else f"{days_left} days left (Expires: {exp_str})"

                    items_list_view.controls.append(
                        ft.Card(
                            content=ft.Container(
                                padding=12,
                                content=ft.ListTile(
                                    leading=ft.Icon(
                                        ft.Icons.WARNING_ROUNDED if is_urgent else ft.Icons.CHECK_CIRCLE_OUTLINED,
                                        color=ft.Colors.RED_600 if is_urgent else ft.Colors.GREEN_600
                                    ),
                                    title=ft.Text(name, weight=ft.FontWeight.BOLD),
                                    subtitle=ft.Text(status_text),
                                    trailing=ft.Row(
                                        controls=[
                                            ft.Container(
                                                content=ft.Text(f"{days_left}d", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                                                bgcolor=ft.Colors.RED_600 if is_urgent else ft.Colors.TEAL_600,
                                                padding=8,
                                                border_radius=6
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.DELETE_OUTLINED,
                                                icon_color=ft.Colors.RED_400,
                                                on_click=lambda _, i_id=item_id: handle_delete_item(i_id)
                                            )
                                        ],
                                        width=110,
                                        alignment=ft.MainAxisAlignment.END
                                    )
                                )
                            )
                        )
                    )
                status_label.value = f"Loaded {len(rows)} items."
                status_label.color = ft.Colors.GREEN_700
            else:
                status_label.value = f"Server Error {resp.status_code}: {resp.text}"
                status_label.color = ft.Colors.RED_600

        except Exception as ex:
            status_label.value = f"Connection Error: {type(ex).__name__}"
            status_label.color = ft.Colors.RED_600

        page.update()

    scan_name_btn = ft.IconButton(icon=ft.Icons.CAMERA_ALT, tooltip="Scan Item Name", icon_color=ft.Colors.TEAL_600, on_click=trigger_scan_name)
    scan_date_btn = ft.IconButton(icon=ft.Icons.CALENDAR_MONTH, tooltip="Scan Expiry Date", icon_color=ft.Colors.TEAL_600, on_click=trigger_scan_date)
    save_btn = ft.Button(content=ft.Text("➕ SAVE ITEM TO INVENTORY", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), icon=ft.Icons.SAVE, style=ft.ButtonStyle(bgcolor=ft.Colors.TEAL_600, padding=16), on_click=handle_add_item)

    header = ft.Row(
        controls=[
            ft.Text("Expiry Scanner", size=24, weight=ft.FontWeight.BOLD),
            ft.IconButton(icon=ft.Icons.REFRESH, on_click=refresh_item_list)
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
    )

    page.add(
        header,
        ft.Divider(),
        threshold_input,
        ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row([name_input, scan_name_btn]),
                    ft.Row([date_input, scan_date_btn]),
                    status_label,
                    save_btn
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            padding=20,
            bgcolor=ft.Colors.GREY_100,
            border_radius=10
        ),
        ft.Text("Tracked Inventory", size=18, weight=ft.FontWeight.W_600),
        items_list_view
    )

    # Initial data load trigger
    refresh_item_list()

# Correct Flet ASGI export syntax
app = ft.app(target=main, export_asgi_app=True,
    web_renderer="html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    ft.run(main, view=ft.AppView.WEB_BROWSER, host="127.0.0.1", port=port)