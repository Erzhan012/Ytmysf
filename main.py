#!/usr/bin/env python3
import os
import asyncio
import hashlib
import html
import logging
import shutil
import re
from pathlib import Path
from typing import List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import (
    BOT_TOKEN,
    SEARCH_SOURCES,
    MAX_RESULTS_TOTAL,
    PAGE_SIZE,
    SEARCH_CACHE_TTL,
    TEMP_DIR,
    ADMIN_ID,
)
from cache import TTLCache
from utils import sanitize_title, format_duration
import music_downloader

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set. Put it into environment variables or .env")

# In-memory search cache
search_cache = TTLCache(ttl=SEARCH_CACHE_TTL)

# Simple URL regex to detect links in messages
URL_RE = re.compile(r"https?://\S+")

# Limit concurrent downloads to avoid overload
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2"))
_download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


def _cache_key_for_query(query: str) -> str:
    h = hashlib.sha256()
    h.update(query.strip().lower().encode("utf-8"))
    return h.hexdigest()


def build_keyboard(cache_key: str, page: int, total_pages: int, entries: List[dict]) -> InlineKeyboardMarkup:
    buttons = []
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, len(entries))
    for idx in range(start, end):
        title = entries[idx].get("title") or "Unknown"
        title = sanitize_title(title)
        cb = f"play:{cache_key}:{idx}"
        buttons.append([InlineKeyboardButton(text=f"{idx - start + 1}. {title[:50]}", callback_data=cb)])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{cache_key}:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{cache_key}:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("Закрыть", callback_data=f"close:{cache_key}")])
    return InlineKeyboardMarkup(buttons)


async def _run_search(query: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, music_downloader.search_combined, query, SEARCH_SOURCES, MAX_RESULTS_TOTAL)


async def _run_fetch_info(url: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, music_downloader.fetch_info, url)


async def _run_download(url: str, out_dir: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, music_downloader.download_to_mp3, url, out_dir)


async def send_admin_message(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not ADMIN_ID:
        return
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text)
    except Exception as e:
        logger.exception("Failed to send admin message: %s", e)


# Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Отправь название песни или ссылку на трек, либо используй команду /search <запрос>.\n"
        "Я покажу результаты постранично (по 10). Нажми кнопку — я скачаю MP3 и пришлю. Панель останется доступной."
    )


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        query = " ".join(context.args).strip()
    else:
        await update.message.reply_text("Укажите запрос, например: /search Billie Jean")
        return
    await do_search_and_send(update, query)


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return
    m = URL_RE.search(text)
    if m:
        url = m.group(0)
        await do_fetch_and_send(update, url)
        return
    await do_search_and_send(update, text)


async def do_fetch_and_send(update: Update, url: str):
    key = _cache_key_for_query(url)
    cached = search_cache.get(key)
    if cached:
        entries = cached
    else:
        info_msg = await update.message.reply_text("Извлекаю информацию о ссылке...")
        try:
            info = await _run_fetch_info(url)
        finally:
            try:
                await info_msg.delete()
            except Exception:
                pass
        if not info:
            await update.message.reply_text("Не удалось извлечь информацию по ссылке.")
            return
        entries = [info]
        search_cache.set(key, entries)

    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
    page = 0
    keyboard = build_keyboard(key, page, total_pages, entries)
    e = entries[0]
    dur = e.get("duration")
    dur_str = f" [{format_duration(dur)}]" if dur else ""
    text = f"Найден трек: {html.escape(e.get('title') or 'Unknown')}{dur_str}"
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def do_search_and_send(update: Update, query: str):
    key = _cache_key_for_query(query)
    cached = search_cache.get(key)
    if cached:
        entries = cached
    else:
        searching_msg = await update.message.reply_text(f"Ищу: {html.escape(query)} ...")
        try:
            entries = await _run_search(query)
        finally:
            try:
                await searching_msg.delete()
            except Exception:
                pass
        search_cache.set(key, entries)

    if not entries:
        await update.message.reply_text("❌ Ничего не найдено. Попробуйте изменить запрос.")
        return

    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
    page = 0
    keyboard = build_keyboard(key, page, total_pages, entries)
    first_chunk = entries[0: min(PAGE_SIZE, len(entries))]
    text_lines = [f"Результаты поиска: {html.escape(query)} (всего: {len(entries)})"]
    for i, e in enumerate(first_chunk, start=1):
        dur = e.get("duration")
        dur_str = f" [{format_duration(dur)}]" if dur else ""
        t = sanitize_title(e.get("title") or "Unknown")
        text_lines.append(f"{i}. {t}{dur_str}")
    text = "\n".join(text_lines)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # remove loading state
    data = query.data or ""

    try:
        if data.startswith("page:"):
            _, cache_key, page_s = data.split(":", 2)
            page = int(page_s)
            entries = search_cache.get(cache_key)
            if not entries:
                await query.message.reply_text("Кэш просрочен. Повторите поиск.")
                return
            total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
            keyboard = build_keyboard(cache_key, page, total_pages, entries)
            try:
                await query.message.edit_reply_markup(reply_markup=keyboard)
            except Exception:
                # редактирование могло быть запрещено (например, старое сообщение) — отправим новую клавиатуру
                await query.message.reply_text("Обновление страницы...", reply_markup=keyboard)
            return

        if data.startswith("play:"):
            _, cache_key, idx_s = data.split(":", 2)
            idx = int(idx_s)
            entries = search_cache.get(cache_key)
            if not entries:
                await query.message.reply_text("Кэш просрочен. Повторите поиск.")
                return
            if idx < 0 or idx >= len(entries):
                await query.message.reply_text("Неверный индекс трека.")
                return
            entry = entries[idx]

            # notify user that download will start
            await query.answer(text="Начинаю загрузку, подожди...")

            # prepare temp dir
            os.makedirs(TEMP_DIR, exist_ok=True)
            out_dir = Path(TEMP_DIR) / f"{cache_key}_{idx}"
            if out_dir.exists():
                shutil.rmtree(out_dir, ignore_errors=True)
            out_dir.mkdir(parents=True, exist_ok=True)

            # determine url for download
            url = entry.get("webpage_url") or entry.get("_raw", {}).get("url") or entry.get("id")
            if not url:
                await query.message.reply_text("Не удалось определить URL для скачивания.")
                try:
                    shutil.rmtree(out_dir, ignore_errors=True)
                except Exception:
                    pass
                return

            # limit concurrent downloads
            async with _download_semaphore:
                mp3_path: Optional[str] = None
                try:
                    mp3_path = await _run_download(url, str(out_dir))
                except Exception as e:
                    logger.exception("Download exception: %s", e)
                    await query.message.reply_text("Ошибка при скачивании трека.")
                    # notify admin about repeated errors if needed
                    try:
                        await send_admin_message(context, f"Ошибка скачивания {url}: {e}")
                    except Exception:
                        pass
                if not mp3_path:
                    await query.message.reply_text("Ошибка при скачивании трека или трек недоступен.")
                    try:
                        shutil.rmtree(out_dir, ignore_errors=True)
                    except Exception:
                        pass
                    return

                # send audio as separate message (keeps original keyboard)
                title = entry.get("title") or "Track"
                performer = entry.get("uploader") or None
                try:
                    with open(mp3_path, "rb") as audio_file:
                        await context.bot.send_audio(
                            chat_id=query.message.chat_id,
                            audio=audio_file,
                            title=title[:64],
                            performer=performer,
                        )
                except Exception as e:
                    logger.exception("Failed to send audio: %s", e)
                    await query.message.reply_text("Ошибка при отправке аудио: " + str(e))
                    try:
                        await send_admin_message(context, f"Ошибка отправки аудио: {e}")
                    except Exception:
                        pass
                finally:
                    try:
                        shutil.rmtree(out_dir, ignore_errors=True)
                    except Exception:
                        pass
            return

        if data.startswith("close:"):
            _, cache_key = data.split(":", 1)
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

    except Exception as e:
        logger.exception("Error handling callback: %s", e)
        await query.message.reply_text("Внутренняя ошибка при обработке запроса.")
        try:
            await send_admin_message(context, f"Callback handler error: {e}")
        except Exception:
            pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Centralized error handler for the dispatcher
    logger.exception("Update caused error: %s", context.error)
    # attempt to notify admin
    try:
        await send_admin_message(context, f"Error in bot: {context.error}")
    except Exception:
        logger.exception("Failed sending admin notification")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_error_handler(error_handler)

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=None)  # blocking


if __name__ == "__main__":
    main()
