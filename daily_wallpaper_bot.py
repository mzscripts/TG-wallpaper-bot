import requests
import asyncio
import json
import sqlite3
from telegram import Bot, InputMediaPhoto
from telegram.error import Forbidden, TelegramError
from io import BytesIO
from datetime import datetime
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

HTML_FILE = 'wallpapers.html'
CAPTIONS_FILE = 'captions.json'
STATE_DB = 'state.db'
SUPABASE_BUCKET = "wallpaper-bot"

# === Supabase I/O functions ===
def download_state():
    url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{STATE_DB}"
    response = requests.get(url)
    if response.status_code == 200:
        with open(STATE_DB, "wb") as f:
            f.write(response.content)
        print("✅ Downloaded state.db from Supabase")
    else:
        print("⚠️ Could not download state.db from Supabase. It might not exist yet.")

def upload_state():
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{STATE_DB}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/octet-stream"
    }
    with open(STATE_DB, "rb") as f:
        file_data = f.read()
    response = requests.post(url, headers=headers, data=file_data, params={"upsert": "true"})
    if response.status_code in [200, 201]:
        print("✅ Uploaded state.db to Supabase")
    else:
        print("❌ Failed to upload state.db:", response.text)

# === SQLite DB utilities ===
def init_db():
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, caption_index INTEGER, drop_counter INTEGER)')
    cursor.execute('INSERT OR IGNORE INTO state (id, caption_index, drop_counter) VALUES (1, 0, 0)')
    conn.commit()
    conn.close()

def load_state():
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT caption_index, drop_counter FROM state WHERE id = 1')
    result = cursor.fetchone()
    conn.close()
    return result if result else (0, 0)

def save_state(caption_index, drop_counter):
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    cursor.execute('UPDATE state SET caption_index = ?, drop_counter = ? WHERE id = 1', (caption_index, drop_counter))
    conn.commit()
    conn.close()

# === Main Async Logic ===
async def main():
    try:
        # Step 1: Download state from Supabase and initialize DB
        download_state()
        init_db()

        # Step 2: Load captions
        try:
            with open(CAPTIONS_FILE, 'r', encoding='utf-8') as f:
                captions_data = json.load(f)
                captions = captions_data.get('captions', [])
            if not captions:
                print(f"❌ No captions found in {CAPTIONS_FILE}.")
                return
        except FileNotFoundError:
            print(f"❌ {CAPTIONS_FILE} not found.")
            return
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in {CAPTIONS_FILE}.")
            return

        # Step 3: Load state
        caption_index, drop_counter = load_state()
        drop_counter += 1
        caption = captions[caption_index]
        caption_index = (caption_index + 1) % len(captions)
        caption_with_counter = f"#{drop_counter} {caption} "

        # Step 4: Load images from HTML
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml')
        image_tags = soup.find_all('img', src=True)
        wallpaper_links = [img['src'] for img in image_tags]

        if not wallpaper_links:
            print("❌ No wallpapers found in HTML.")
            return

        selected_images = wallpaper_links[:10]
        print(f"ℹ️ Selected {len(selected_images)} images")

        # Step 5: Download images
        media_group = []
        image_buffers = []
        for idx, image_url in enumerate(selected_images):
            response = requests.get(image_url)
            if response.status_code != 200:
                print(f"❌ Failed to download {image_url} (Status: {response.status_code})")
                continue
            buffer = BytesIO(response.content)
            image_buffers.append(buffer)
            media_group.append(InputMediaPhoto(media=buffer, caption=caption_with_counter if idx == 0 else ""))

        if not media_group:
            print("❌ No images downloaded successfully.")
            return

        # Step 6: Post to Telegram
        bot = Bot(token=BOT_TOKEN)
        try:
            await bot.send_media_group(chat_id=CHANNEL_USERNAME, media=media_group)
        except Forbidden as e:
            print(f"❌ Forbidden: {e}. Make sure the bot is an admin.")
            return
        except TelegramError as e:
            print(f"❌ Telegram error: {e}")
            return
        finally:
            for buffer in image_buffers:
                buffer.close()

        # Step 7: Remove posted images from HTML
        for img in image_tags[:]:
            if img['src'] in selected_images:
                img.decompose()
        with open(HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))

        # Step 8: Save state and upload
        save_state(caption_index, drop_counter)
        upload_state()

        # Step 9: Log posting
        with open("post_log.txt", "a") as log:
            for image_url in selected_images:
                log.write(f"{datetime.now()}: Posted {image_url} with caption '{caption_with_counter}'\n")

        print(f"✅ Posted {len(selected_images)} images with caption: {caption_with_counter}")

    except Exception as e:
        print(f"❌ Error occurred: {e}")

# Run the async bot
if __name__ == "__main__":
    asyncio.run(main())
