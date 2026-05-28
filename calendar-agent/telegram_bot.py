#!/usr/bin/env python3
"""
Telegram bot that forwards messages to Make.com webhook → Google Calendar
Usage: set BOT_TOKEN env var, run this script, send any message to the bot.
"""

import os
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

WEBHOOK_URL = os.environ.get(
    "MAKE_WEBHOOK_URL",
    "https://hook.eu2.make.com/8auy6xgtibylsxktv50jl69tah1dsqdz",
)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    if not text:
        return

    await update.message.reply_text("⏳ 일정 등록 중...")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(WEBHOOK_URL, json={"message": text})
            resp.raise_for_status()

        await update.message.reply_text(
            f"✅ 캘린더에 등록했어요!\n\n📅 '{text}'\n\nGoogle Calendar를 확인해보세요."
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ 등록 실패: {e}\n\nMake.com 시나리오가 활성화되어 있는지 확인해주세요."
        )


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN 환경변수를 설정해주세요.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("텔레그램 봇 시작됨. Ctrl+C로 종료.")
    app.run_polling()


if __name__ == "__main__":
    main()
