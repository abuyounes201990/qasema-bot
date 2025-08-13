#!/usr/bin/env python3
import os
import logging
from typing import List, Dict

from parser_utils import parse_bet_slip, normalize_pair, decode_1xbet_coupon
from storage import Storage

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8420817174:AAElcz5j78pco3h7-luFZAzHYBX2TRvNQsI"

DEFAULT_EXPIRE_DAYS = int(os.getenv("EXPIRE_DAYS", "2"))
storage = Storage(db_path=os.getenv("DB_PATH", "data/bot.db"), expire_days=DEFAULT_EXPIRE_DAYS)

WELCOME = (
    "أهلاً يا زعيم 👋\n\n"
    "ابعتلي القسيمة كنص، كل ماتش في سطر لو سمحت، أو استخدم الأمر /decode <كود_1xBet> لفك قسيمة 1xBet Global.\n\n"
    "أمثلة: /decode DTWP3J7B\n"
)

HELP = (
    "🛠️ طريقة الاستخدام:\n"
    "ابعت القسيمة نصًا أو استخدم:\n"
    "/decode <كود_1xBet> — يفك القسيمة من 1xBet ويعرض الماتشات\n"
    "/expiredays — عرض أو ضبط مدة انتهاء صلاحية الماتشات (أيام). مثال: /expiredays 2\n"
    "/help — عرض هذه الرسالة.\n"
)

def format_table(rows: List[Dict]) -> str:
    header = f"{ '#':<2} {'الماتش':<36} {'مكرر':<6} {'ظهر قبل؟':<9}"
    sep = "—" * 60
    lines = [f"<pre>{header}\n{sep}"]
    for idx, r in enumerate(rows, start=1):
        match_name = f"{r['team_a']} vs {r['team_b']}"
        dup_flag = "✅" if r['dup_in_slip'] else "❌"
        seen_flag = "📂" if r['seen_before'] else "—"
        if len(match_name) > 34:
            match_name = match_name[:33] + "…"
        lines.append(f"{idx:<2} {match_name:<36} {dup_flag:<6} {seen_flag:<9}")
    lines.append("</pre>")
    return "\n".join(lines)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP)

async def cmd_expiredays(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        try:
            days = int(context.args[0])
            storage.set_expire_days(days)
            await update.message.reply_text(f"⏳ تم ضبط مدة انتهاء صلاحية الماتشات إلى {days} يوم.")
        except ValueError:
            await update.message.reply_text("من فضلك اكتب رقم صحيح. مثال: /expiredays 2")
    else:
        await update.message.reply_text(f"⏳ المدة الحالية: {storage.expire_days} يوم.\nاستخدم: /expiredays 2 لتغييرها.")

async def cmd_decode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("اكتب الكود بعد الأمر. مثال: /decode DTWP3J7B")
        return
    code = context.args[0].strip()
    await update.message.reply_text(f"🔎 بحاول أفك القسيمة للكود: {code} ...")
    try:
        matches = decode_1xbet_coupon(code)
    except Exception as e:
        logger.exception("decode error")
        await update.message.reply_text(f"حصل خطأ وأنا أحاول أفك القسيمة: {e}")
        return
    if not matches:
        await update.message.reply_text("ماقدرتش أجيب أي ماتشات من الكود ده — ممكن يكون الكود غلط أو الموقع منع الوصول.") 
        return

    text = "\n".join([f"{a} vs {b}" for a,b in matches])
    storage.expire_old_matches()

    norm_lines = [f"{normalize_pair(a,b)}" for a,b in matches]
    slip_fingerprint = Storage.fingerprint(norm_lines)
    identical_seen = storage.slip_fingerprint_exists(slip_fingerprint)

    seen_set = set()
    rows = []
    dup_in_slip_any = False
    seen_before_any = False

    for a, b in matches:
        norm = normalize_pair(a, b)
        dup_in_slip = norm in seen_set
        if dup_in_slip:
            dup_in_slip_any = True
        seen_set.add(norm)

        seen_before = storage.pair_exists_active(norm)
        if seen_before:
            seen_before_any = True

        rows.append({
            "team_a": a,
            "team_b": b,
            "dup_in_slip": dup_in_slip,
            "seen_before": seen_before,
        })

    slip_id = storage.save_slip(
        user_id=update.effective_user.id if update.effective_user else 0,
        raw_text=text,
        fingerprint=slip_fingerprint,
    )
    storage.save_matches(slip_id, [normalize_pair(a,b) for a,b in matches])

    title_lines = []
    if identical_seen:
        title_lines.append("🔁 القسيمة دي اتبعت قبل كده (مكررة تمامًا).")
    if dup_in_slip_any:
        title_lines.append("⚠️ فيه ماتش/ماتشات مكررة داخل القسيمة!")
    if seen_before_any:
        title_lines.append("📂 فيه ماتشات ظهرت في قسايم نشطة قبل كده.")

    if not title_lines:
        title_lines.append("✅ القسيمة اتسجلت واتفلترت من غير مشاكل واضحة.")

    table_text = format_table(rows)
    await update.message.reply_text("\n".join(title_lines) + "\n" + table_text, parse_mode=ParseMode.HTML)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return
    if len(text) <= 12 and text.isalnum():
        context.args = [text]
        await cmd_decode(update, context)
        return

    storage.expire_old_matches()

    matches = parse_bet_slip(text)
    if not matches:
        await update.message.reply_text(
            "مش قادر أفهم القسيمة 🤔\nاكتب كل ماتش في سطر بالشكل: Team A vs Team B"
        )
        return

    norm_lines = [f"{normalize_pair(a,b)}" for a,b in matches]
    slip_fingerprint = Storage.fingerprint(norm_lines)
    identical_seen = storage.slip_fingerprint_exists(slip_fingerprint)

    seen_set = set()
    rows = []
    dup_in_slip_any = False
    seen_before_any = False

    for a, b in matches:
        norm = normalize_pair(a, b)
        dup_in_slip = norm in seen_set
        if dup_in_slip:
            dup_in_slip_any = True
        seen_set.add(norm)

        seen_before = storage.pair_exists_active(norm)
        if seen_before:
            seen_before_any = True

        rows.append({
            "team_a": a,
            "team_b": b,
            "dup_in_slip": dup_in_slip,
            "seen_before": seen_before,
        })

    slip_id = storage.save_slip(
        user_id=update.effective_user.id if update.effective_user else 0,
        raw_text=text,
        fingerprint=slip_fingerprint,
    )
    storage.save_matches(slip_id, [normalize_pair(a,b) for a,b in matches])

    title_lines = []
    if identical_seen:
        title_lines.append("🔁 القسيمة دي اتبعت قبل كده (مكررة تمامًا).")
    if dup_in_slip_any:
        title_lines.append("⚠️ فيه ماتش/ماتشات مكررة داخل القسيمة!")
    if seen_before_any:
        title_lines.append("📂 فيه ماتشات ظهرت في قسايم نشطة قبل كده.")

    if not title_lines:
        title_lines.append("✅ القسيمة اتسجلت واتفلترت من غير مشاكل واضحة.")

    table_text = format_table(rows)
    await update.message.reply_text("\n".join(title_lines) + "\n" + table_text, parse_mode=ParseMode.HTML)

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("expiredays", cmd_expiredays))
    app.add_handler(CommandHandler("decode", cmd_decode))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
