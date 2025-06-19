import requests
import asyncio
import json
from supabase import create_client, Client
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
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
HTML_FILE = 'wallpapers.html'
CAPTIONS_FILE = 'captions.json'

# === Initialize Supabase client ===
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# === State Management with Supabase ===
def load_state():
    """Load caption index and drop counter from Supabase."""
    try:
        response = supabase.table('state').select('caption_index, drop_counter').eq('id', 1).execute()
        if response.data:
            return response.data[0]['caption_index'], response.data[0]['drop_counter']
        print("⚠️ No state found. Initializing with caption_index=0, drop_counter=0.")
        return 0, 0
    except Exception as e:
        print(f"❌ Error loading state: {e}")
        return 0, 0

def save_state(caption_index, drop_counter):
    """Save caption index and drop counter to Supabase."""
    try:
        supabase.table('state').update({
            'caption_index': caption_index,
            'drop_counter': drop_counter
        }).eq('id', 1).execute()
    except Exception as e:
        print(f"❌ Error saving state: {e}")

def get_used_images():
    """Retrieve set of used image URLs from Supabase."""
    try:
        response = supabase.table('used_images').select('image_url').execute()
        return {row['image_url'] for row in response.data}
    except Exception as e:
        print(f"❌ Error loading used images: {e}")
        return set()

def save_used_images(image_urls):
    """Save used image URLs to Supabase."""
    try:
        data = [{'image_url': url} for url in image_urls]
        supabase.table('used_images').insert(data).execute()
    except Exception as e:
        print(f"❌ Error saving used images: {e}")

# === Main Bot Logic ===
async def main():
    try:
        # === Step 1: Load captions from JSON ===
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

        # === Step 2: Load state ===
        caption_index, drop_counter = load_state()
        print(f"🔢 Loaded state: caption_index={caption_index}, drop_counter={drop_counter}")
        drop_counter += 1  # Increment drop counter
        caption = captions[caption_index]
        caption_index = (caption_index + 1) % len(captions)  # Cycle through captions
        caption_with_counter = f"#{drop_counter} {caption} "
        print(f"Debug caption: {repr(caption_with_counter)}")

        # === Step 3: Parse HTML and extract image URLs ===
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml')
        image_tags = soup.find_all('img', src=True)
        wallpaper_links = [img['src'] for img in image_tags]
        if not wallpaper_links:
            print("❌ No wallpapers found in HTML.")
            return

        # === Step 4: Filter out used images ===
        used_images = get_used_images()
        available_images = [url for url in wallpaper_links if url not in used_images]
        selected_images = available_images[:10]
        print(f"ℹ️ Selected {len(selected_images)} images: {selected_images}")
        if not selected_images:
            print("❌ No new images available to post.")
            return

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

        # === Step 7: Save used images to Supabase ===
        save_used_images(selected_images)

        # === Step 8: Save updated state ===
        save_state(caption_index, drop_counter)

        # === Step 9: Log it ===
        with open("post_log.txt", "a", encoding='utf-8') as log:
            for image_url in selected_images:
                log.write(f"{datetime.now()}: Posted {image_url} with caption '{caption_with_counter}'\n")

        print(f"✅ Posted {len(selected_images)} images with caption: {caption_with_counter}")

    except Exception as e:
        print(f"❌ An error occurred: {e}")

# === Run the Bot ===
if __name__ == "__main__":
    asyncio.run(main())