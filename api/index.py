import os
import requests # <--- The simple way
from flask import Flask, request, jsonify
import telebot

app = Flask(__name__)

# Config
TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

bot = telebot.TeleBot(TOKEN, threaded=False)

def save_to_supabase(item, amount):
    # We construct the URL manually: https://your-project.supabase.co/rest/v1/expenses
    url = f"{SUPABASE_URL}/rest/v1/expenses"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    payload = {
        "item": item,
        "amount": amount,
        "category": "Uncategorized"
    }
    
    # Send it!
    response = requests.post(url, json=payload, headers=headers)
    return response.status_code == 201

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        text = message.text.strip()
        parts = text.split()

        # Debug command
        if text.lower() == "version":
            bot.reply_to(message, "✅ v3.0 (Requests Mode) is ONLINE!")
            return

        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Format: 50 Pizza")
            return

        amount = float(parts[0])
        item = ' '.join(parts[1:])

        success = save_to_supabase(item, amount)
        
        if success:
            bot.reply_to(message, f"💸 Saved: {amount} for {item}.")
        else:
            bot.reply_to(message, "❌ Database Error (Check Supabase Logs)")

    except Exception as e:
        bot.reply_to(message, f"🔥 Error: {str(e)}")

@app.route('/', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200