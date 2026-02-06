import os
import requests
from flask import Flask, request, jsonify
import telebot
from telebot import types
from datetime import datetime
from groq import Groq

app = Flask(__name__)

# --- CONFIG ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
DASHBOARD_PASSWORD = os.environ.get('DASHBOARD_PASSWORD')

bot = telebot.TeleBot(TOKEN, threaded=False)
groq_client = Groq(api_key=GROQ_API_KEY)

# --- DATABASE HELPERS ---
def run_query(endpoint, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    return requests.get(url, headers=headers, params=params)

def save_expense(item, amount, category="Uncategorized"):
    url = f"{SUPABASE_URL}/rest/v1/expenses"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    # AI Categorization
    if category == "Uncategorized":
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": f"Categorize this expense item into one word (e.g., Food, Transport, Tech). Output ONLY the word: '{item}'"}],
                model="llama-3.3-70b-versatile",
            )
            # Cleanup AI response to get just the word
            ai_cat = chat_completion.choices[0].message.content.strip().split()[0].replace(".", "")
            if ai_cat:
                category = ai_cat
        except Exception as e:
            print(f"AI Error: {e}")

    payload = {"item": item, "amount": amount, "category": category}
    requests.post(url, json=payload, headers=headers)
    return category

def ask_ai(prompt):
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"My brain hurts: {e}"

# --- DASHBOARD API (Secure Proxy) ---
@app.route('/api/stats', methods=['GET'])
def get_dashboard_stats():
    # 1. Security Check
    auth_header = request.headers.get('X-Dashboard-Password')
    if auth_header != DASHBOARD_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    # 2. Fetch Data
    cat_res = run_query("expenses?select=category,amount")
    hist_res = run_query("expenses?select=item,amount,created_at&order=created_at.desc&limit=10")
    
    if cat_res.status_code != 200 or hist_res.status_code != 200:
        return jsonify({"error": "Database Error"}), 500

    # 3. Process Data
    expenses = cat_res.json()
    category_totals = {}
    for ex in expenses:
        cat = ex['category'] or "Uncategorized"
        category_totals[cat] = category_totals.get(cat, 0) + float(ex['amount'])

    return jsonify({
        "categories": category_totals,
        "history": hist_res.json(),
        "total_spent": sum(category_totals.values())
    })

# --- UNIFIED ROUTE (The Fix for Vercel) ---
# This single function handles BOTH the website (GET) and the bot (POST)
@app.route('/', methods=['GET', 'POST'])
def handle_root():
    # 1. If Browser -> Show Dashboard
    if request.method == 'GET':
        base_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(base_dir, '../public/index.html')
        try:
            with open(html_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return "Error: Dashboard file not found.", 404

    # 2. If Telegram -> Run Bot
    elif request.method == 'POST':
        if not TOKEN: return 'Error', 500
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'OK', 200

# --- BOT COMMAND HANDLERS ---
# (We need these so the bot knows what to do!)

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('💰 Total', '🏆 Highest')
    markup.row('📜 History', '🧠 Analyze')
    markup.row('❓ Help')
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.send_message(message.chat.id, "🤖 **ContabilBOT CFO**\nReady to judge your spending.", parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == '💰 Total')
@bot.message_handler(commands=['total'])
def show_total(message):
    res = run_query("expenses?select=amount")
    if res.status_code == 200:
        total = sum([float(x['amount']) for x in res.json()])
        bot.reply_to(message, f"💰 Total: {total:,.2f} MDL", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == '🏆 Highest')
@bot.message_handler(commands=['highest'])
def show_highest(message):
    res = run_query("expenses?select=item,amount&order=amount.desc&limit=1")
    if res.status_code == 200 and len(res.json()) > 0:
        top = res.json()[0]
        bot.reply_to(message, f"🏆 Highest: {top['amount']} on {top['item']}", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == '📜 History')
@bot.message_handler(commands=['history'])
def show_history(message):
    res = run_query("expenses?select=item,amount,category,created_at&order=created_at.desc&limit=5")
    if res.status_code == 200:
        text = "📜 **Recent:**\n"
        for ex in res.json():
            date_str = datetime.fromisoformat(ex['created_at'].replace('Z', '+00:00')).strftime("%d/%m")
            text += f"`{date_str}`: {ex['amount']} - {ex['item']}\n"
        bot.reply_to(message, text, parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == '🧠 Analyze')
@bot.message_handler(commands=['analyze'])
def run_analysis(message):
    bot.send_chat_action(message.chat.id, 'typing')
    res = run_query("expenses?select=item,amount,category&order=created_at.desc&limit=20")
    if not res.json():
        bot.reply_to(message, "No data to analyze.")
        return
    
    expense_list = "\n".join([f"- {x['amount']} on {x['item']} ({x['category']})" for x in res.json()])
    prompt = f"Last 20 expenses:\n{expense_list}\nRoast this user's spending habits. Be rude. Short verdict."
    analysis = ask_ai(prompt)
    bot.reply_to(message, f"🧠 **Verdict:**\n{analysis}", parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: True)
def handle_expense(message):
    try:
        parts = message.text.strip().split()
        if len(parts) < 2: return
        amount = float(parts[0])
        item = ' '.join(parts[1:])
        category = save_expense(item, amount)
        bot.reply_to(message, f"💸 Saved: {amount} for {item}.\n📂 {category}", reply_markup=get_main_menu())
    except Exception:
        pass