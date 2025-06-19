# supabase_io.py
import os
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
BUCKET = "wallpaper-bot"
FILE_PATH = "state.db"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

def download_state():
    url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{FILE_PATH}"
    response = requests.get(url)
    if response.status_code == 200:
        with open(FILE_PATH, "wb") as f:
            f.write(response.content)
        print("✅ Downloaded state.db from Supabase")
    else:
        print("❌ Failed to download state.db:", response.text)

def upload_state():
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{FILE_PATH}"
    with open(FILE_PATH, "rb") as f:
        file_data = f.read()
    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/octet-stream"},
        data=file_data,
        params={"upsert": "true"},
    )
    if response.status_code in [200, 201]:
        print("✅ Uploaded state.db to Supabase")
    else:
        print("❌ Failed to upload state.db:", response.text)
