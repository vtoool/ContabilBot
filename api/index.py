import os
import json
import random
from datetime import datetime
from flask import Flask, request, jsonify
import telebot
from supabase import create_client, Client

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if TELEGRAM_TOKEN:
    bot = telebot.TeleBot(TELEGRAM_TOKEN)

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

INSULTS = [
    "Your wallet is crying. Loudly.",
    "Do you really need that? Really?",
    "I'm telling your mother about this.",
    "Another expense? Bold strategy.",
    "Your bank account just filed for emotional distress.",
    "Nice job emptying your pockets.",
    "Congratulations, you now own less stuff than before.",
    "I expected better from you. Actually, I didn't.",
    "That purchase just killed your weekend plans.",
    "RIP your savings account.",
    "Was that worth the eventual regret?",
    "Your future self is disappointed.",
    "Another day, another hole in your wallet.",
    "You've officially been served a receipt of shame.",
    "The ATM just ghosted you.",
]


def insert_expense(item, amount):
    if not supabase:
        return False
    try:
        data = {"item": item, "amount": float(amount), "category": "Uncategorized"}
        response = supabase.table("expenses").insert(data).execute()
        return True
    except Exception as e:
        print(f"Supabase insert error: {e}")
        return False


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        text = message.text.strip()
        parts = text.split()
        
        # --- DEBUG MODE: Reply with what the bot sees ---
        # This will prove if the new code is running!
        if text.lower() == "version":
            bot.reply_to(message, "✅ v2.0 (Supabase) is RUNNING!")
            return

        if len(parts) < 2:
            # Show the user exactly what failed
            bot.reply_to(message, f"⚠️ Error: I see '{text}'. I found {len(parts)} parts. I need 2.\nTry: 50 Pizza")
            return

        amount = float(parts[0])
        item = ' '.join(parts[1:])

        # Insert into Supabase
        data = {"item": item, "amount": amount, "category": "Uncategorized"}
        result = supabase.table("expenses").insert(data).execute()
        
        bot.reply_to(message, f"💸 Saved: {amount} for {item}.\n(Saved to Database!)")

    except Exception as e:
        # If it crashes, tell us WHY
        bot.reply_to(message, f"🔥 CRITICAL ERROR:\n{str(e)}")


@app.route("/", methods=["POST"])
def webhook():
    if not TELEGRAM_TOKEN:
        return jsonify({"error": "TELEGRAM_TOKEN not configured"}), 500
    try:
        update = telebot.types.Update.de_json(request.get_json())
        bot.process_new_updates([update])
        return "", 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
