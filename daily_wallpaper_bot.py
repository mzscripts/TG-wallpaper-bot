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
HTML_FILE = 'wallpapers.html'
CAPTIONS_FILE = 'captions.json'
STATE_DB = 'state.db'

def init_db():
    """Initialize SQLite database and state table."""
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, caption_index INTEGER, drop_counter INTEGER)')
    cursor.execute('INSERT OR IGNORE INTO state (id, caption_index, drop_counter) VALUES (1, 0, 0)')
    conn.commit()
    conn.close()

def load_state():
    """Load caption index and drop counter from SQLite."""
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT caption_index, drop_counter FROM state WHERE id = 1')
    result = cursor.fetchone()
    conn.close()
    return result if result else (0, 0)

def save_state(caption_index, drop_counter):
    """Save caption index and drop counter to SQLite."""
    conn = sqlite3.connect(STATE_DB)
    cursor = conn.cursor()
    cursor.execute('UPDATE state SET caption_index = ?, drop_counter = ? WHERE id = 1', (caption_index, drop_counter))
    conn.commit()
    conn.close()

async def main():
    try:
        # === Step 1: Initialize database ===
        init_db()

        # === Step 2: Load captions from JSON ===
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
            print(f"❌ Invalid JSON format in {CAPTIONS_FILE}.")
            return

        # === Step 3: Load state ===
        caption_index, drop_counter = load_state()
        drop_counter += 1  # Increment drop counter
        caption = captions[caption_index]
        caption_index = (caption_index + 1) % len(captions)  # Cycle through captions
        caption_with_counter = f"#{drop_counter} {caption} "

        # === Step 4: Parse HTML and extract image URLs ===
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml')

        image_tags = soup.find_all('img', src=True)
        wallpaper_links = [img['src'] for img in image_tags]

        if not wallpaper_links:
            print("❌ No wallpapers found in HTML.")
            return

        # Select up to 10 images
        selected_images = wallpaper_links[:10]
        print(f"ℹ️ Selected {len(selected_images)} images")

        # === Step 5: Download images ===
        media_group = []
        image_buffers = []
        for idx, image_url in enumerate(selected_images):
            response = requests.get(image_url)
            if response.status_code != 200:
                print(f"❌ Failed to download image: {image_url} (Status: {response.status_code})")
                continue
            image_buffer = BytesIO(response.content)
            image_buffers.append(image_buffer)
            media_group.append(
                InputMediaPhoto(
                    media=image_buffer,
                    caption=caption_with_counter if idx == 0 else ""
                )
            )

        if not media_group:
            print("❌ No images were successfully downloaded.")
            return

        # === Step 6: Post to Telegram ===
        bot = Bot(token=BOT_TOKEN)
        try:
            await bot.send_media_group(chat_id=CHANNEL_USERNAME, media=media_group)
        except Forbidden as e:
            print(f"❌ Forbidden error: {e}. Ensure the bot is an admin in the channel.")
            return
        except TelegramError as e:
            print(f"❌ Telegram error: {e}")
            return
        finally:
            for buffer in image_buffers:
                buffer.close()

        # === Step 7: Remove used images from HTML ===
        for img in image_tags[:]:
            if img['src'] in selected_images:
                img.decompose()

        with open(HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))

        # === Step 8: Save updated state ===
        save_state(caption_index, drop_counter)

        # === Step 9: Log it ===
        with open("post_log.txt", "a") as log:
            for image_url in selected_images:
                log.write(f"{datetime.now()}: Posted and removed {image_url} with caption '{caption_with_counter}'\n")

        print(f"✅ Posted {len(selected_images)} images with caption: {caption_with_counter}")

    except Exception as e:
        print(f"❌ An error occurred: {e}")

# Run the async main
if __name__ == "__main__":
    asyncio.run(main())