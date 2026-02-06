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
    text = message.text.strip()
    parts = text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Wrong format! Use: [Amount] [Item]\nExample: 50 Coffee")
        return
    try:
        amount = float(parts[0])
        item = " ".join(parts[1:])
        if insert_expense(item, amount):
            insult = random.choice(INSULTS)
            bot.reply_to(message, f"Recorded: {amount} lei for {item}. {insult}")
        else:
            bot.reply_to(
                message, "Database error. Your spending wasn't tracked. Lucky you?"
            )
    except ValueError:
        bot.reply_to(message, "Invalid amount. Use numbers only.\nExample: 50 Coffee")


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
