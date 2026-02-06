import os
import requests
from flask import Flask, request
import telebot
from telebot import types # <--- Needed for buttons
from datetime import datetime
from groq import Groq

app = Flask(__name__)

# --- CONFIG ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

# Initialize Bot & AI
bot = telebot.TeleBot(TOKEN, threaded=False)
groq_client = Groq(api_key=GROQ_API_KEY)

# --- KEYBOARD MENU ---
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_total = types.KeyboardButton('💰 Total')
    btn_highest = types.KeyboardButton('🏆 Highest')
    btn_history = types.KeyboardButton('📜 History')
    btn_analyze = types.KeyboardButton('🧠 Analyze')
    btn_help = types.KeyboardButton('❓ Help')
    markup.add(btn_total, btn_highest, btn_history, btn_analyze, btn_help)
    return markup

# --- AI BRAIN (GROQ) ---
def ask_ai(prompt):
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"My brain hurts: {e}"

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
        ai_cat = ask_ai(f"Categorize this expense item into one word (e.g., Food, Transport, Tech). Output ONLY the word: '{item}'")
        if ai_cat:
            category = ai_cat.strip().split()[0].replace(".", "")

    payload = {"item": item, "amount": amount, "category": category}
    requests.post(url, json=payload, headers=headers)
    return category

# --- HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
    🤖 **ContabilBOT Command Guide**
    
    **1. How to add an expense:**
    Just type the amount and the item.
    • `50 Pizza`
    • `120 Taxi to airport`
    • `15.50 Coffee`
    
    **2. The Buttons:**
    Use the menu below to check your stats.
    
    **3. Analysis:**
    Tap '🧠 Analyze' to get a roast of your spending habits.
    """
    bot.reply_to(message, help_text, parse_mode="Markdown", reply_markup=get_main_menu())

# --- BUTTON HANDLERS (Matching Text) ---

@bot.message_handler(func=lambda m: m.text == '💰 Total')
def show_total(message):
    res = run_query("expenses?select=amount")
    if res.status_code == 200:
        data = res.json()
        total = sum([float(x['amount']) for x in data])
        bot.reply_to(message, f"💰 **Total Spent:** {total:,.2f} MDL", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Database error.")

@bot.message_handler(func=lambda m: m.text == '🏆 Highest')
def show_highest(message):
    res = run_query("expenses?select=item,amount&order=amount.desc&limit=1")
    if res.status_code == 200 and len(res.json()) > 0:
        top = res.json()[0]
        bot.reply_to(message, f"🏆 **Highest Expense:**\n{top['amount']} on *{top['item']}*", parse_mode="Markdown")
    else:
        bot.reply_to(message, "No expenses found.")

@bot.message_handler(func=lambda m: m.text == '📜 History')
def show_history(message):
    res = run_query("expenses?select=item,amount,category,created_at&order=created_at.desc&limit=5")
    if res.status_code == 200:
        expenses = res.json()
        text = "📜 **Last 5 Expenses:**\n"
        for ex in expenses:
            date_obj = datetime.fromisoformat(ex['created_at'].replace('Z', '+00:00'))
            date_str = date_obj.strftime("%d/%m")
            text += f"`{date_str}`: {ex['amount']} - {ex['item']} ({ex['category']})\n"
        bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '🧠 Analyze')
def analyze_finances(message):
    bot.send_chat_action(message.chat.id, 'typing')
    res = run_query("expenses?select=item,amount,category&order=created_at.desc&limit=20")
    data = res.json()
    
    if not data:
        bot.reply_to(message, "You have no expenses to analyze.")
        return

    expense_list = "\n".join([f"- {x['amount']} on {x['item']} ({x['category']})" for x in data])
    prompt = f"Here are my last 20 expenses:\n{expense_list}\nAct as a rude, sarcastic financial advisor. Summarize habits, point out the stupidest purchase, and give harsh advice. Keep it under 100 words."
    
    analysis = ask_ai(prompt)
    bot.reply_to(message, f"🧠 **The Verdict:**\n\n{analysis}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '❓ Help')
def help_btn(message):
    send_welcome(message)

# --- EXPENSE LISTENER (Catches everything else) ---
@bot.message_handler(func=lambda message: True)
def handle_expense(message):
    try:
        text = message.text.strip()
        parts = text.split()
        
        if len(parts) < 2:
            return # Ignore random chat
            
        amount = float(parts[0])
        item = ' '.join(parts[1:])
        
        category = save_expense(item, amount)
        
        # Confirm with the menu visible
        bot.reply_to(message, f"💸 Saved: {amount} for {item}.\n📂 Category: {category}", reply_markup=get_main_menu())

    except ValueError:
        bot.reply_to(message, "⚠️ Numbers first! Example: `50 Pizza`", reply_markup=get_main_menu())
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

# --- WEBHOOK ---
@app.route('/', methods=['POST'])
def webhook():
    if not TOKEN: return 'Error', 500
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200