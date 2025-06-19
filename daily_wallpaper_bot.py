import requests
import asyncio
import json
from telegram import Bot, InputMediaPhoto
from telegram.error import Forbidden, TelegramError
from io import BytesIO
from datetime import datetime
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import sys

# === Set UTF-8 encoding for console output ===
sys.stdout.reconfigure(encoding='utf-8')

# === Load environment variables ===
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')

HTML_FILE = 'wallpapers.html'
CAPTIONS_FILE = 'captions.json'

# === Main Bot Logic ===
async def main():
    try:
        # Step 1: Load captions
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

        # Step 2: Select the first caption
        caption = captions[0] + " "  # Use first caption, add trailing space
        print(f"🔢 Using caption: {caption}")

        # Step 3: Parse HTML
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml')
        image_tags = soup.find_all('img', src=True)
        wallpaper_links = [img['src'] for img in image_tags]

        if not wallpaper_links:
            print("❌ No wallpapers found in HTML.")
            return

        selected_images = wallpaper_links[:10]
        print(f"ℹ️ Selected {len(selected_images)} images")

        # Step 4: Download images
        media_group = []
        image_buffers = []
        for idx, image_url in enumerate(selected_images):
            response = requests.get(image_url)
            if response.status_code != 200:
                print(f"❌ Failed to download {image_url} (Status: {response.status_code})")
                continue
            buffer = BytesIO(response.content)
            image_buffers.append(buffer)
            media_group.append(InputMediaPhoto(media=buffer, caption=caption if idx == 0 else ""))

        if not media_group:
            print("❌ No images downloaded successfully.")
            return

        # Step 5: Send to Telegram
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

        # Step 6: Remove used images
        for img in image_tags[:]:
            if img['src'] in selected_images:
                img.decompose()
        with open(HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))

        # Step 7: Log
        with open("post_log.txt", "a", encoding='utf-8') as log:
            for image_url in selected_images:
                log.write(f"{datetime.now()}: Posted {image_url} with caption '{caption}'\n")

        print(f"✅ Posted {len(selected_images)} images with caption: {caption}")

    except Exception as e:
        print(f"❌ Error occurred: {e}")

# === Run the Bot ===
if __name__ == "__main__":
    asyncio.run(main())