import os
import random
import requests
from flask import Flask, request
import telebot

app = Flask(__name__)

# --- CONFIGURATION ---
# These come from Vercel Settings -> Environment Variables
TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

# Initialize Bot
bot = telebot.TeleBot(TOKEN, threaded=False)

# --- THE JUDGEMENT ENGINE ---
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
    "The ATM just ghosted you."
]

# --- SUPABASE HELPER (The "Safe" Way) ---
# Uses standard HTTP requests to avoid library version conflicts
def save_to_supabase(item, amount):
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
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        # 201 means "Created" (Success)
        return response.status_code == 201
    except Exception as e:
        print(f"Supabase Connection Error: {e}")
        return False

# --- TELEGRAM HANDLERS ---

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        text = message.text.strip()
        parts = text.split()

        # 1. Debug Command
        if text.lower() == "version":
            bot.reply_to(message, "✅ v3.1 (Judgy Mode) is ONLINE!")
            return

        # 2. Validation
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Wrong format!\nUse: [Amount] [Item]\nExample: 50 Pizza")
            return

        # 3. Parse Data
        try:
            amount = float(parts[0])
        except ValueError:
            bot.reply_to(message, "⚠️ That is not a number. Try: 50 Pizza")
            return
            
        item = ' '.join(parts[1:])

        # 4. Save to Database
        success = save_to_supabase(item, amount)
        
        # 5. Reply
        if success:
            roast = random.choice(INSULTS)
            bot.reply_to(message, f"💸 Saved: {amount} for {item}.\n\n🤖 {roast}")
        else:
            bot.reply_to(message, "❌ Database Error. (Check Vercel Logs)")

    except Exception as e:
        bot.reply_to(message, f"🔥 Critical Error: {str(e)}")

# --- WEBHOOK ENTRY POINT ---
@app.route('/', methods=['POST'])
def webhook():
    if not TOKEN:
        return 'Bot token not found', 500
        
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'OK', 200
    except Exception as e:
        return str(e), 500