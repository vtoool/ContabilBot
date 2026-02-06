import os
import json
import random
from datetime import datetime
from flask import Flask, request, jsonify
import telebot
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SHEET_NAME = os.environ.get("SHEET_NAME", "Budget")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON")

if TELEGRAM_TOKEN:
    bot = telebot.TeleBot(TELEGRAM_TOKEN)

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


def get_gspread_client():
    if not GOOGLE_CREDS_JSON:
        return None
    try:
        creds_data = json.loads(GOOGLE_CREDS_JSON)
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"Error creating gspread client: {e}")
        return None


def append_expense_to_sheet(item, amount):
    client = get_gspread_client()
    if not client:
        return False
    try:
        spreadsheet = client.open(SHEET_NAME)
        worksheet = spreadsheet.get_worksheet(0)
        date = datetime.now().strftime("%Y-%m-%d")
        worksheet.append_row([date, item, amount, "Uncategorized"])
        return True
    except Exception as e:
        print(f"Error appending to sheet: {e}")
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
        if append_expense_to_sheet(item, amount):
            insult = random.choice(INSULTS)
            bot.reply_to(message, f"Recorded: {amount} lei for {item}. {insult}")
        else:
            bot.reply_to(message, "Failed to save expense. Check logs.")
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
