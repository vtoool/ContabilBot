import os
import requests
from flask import Flask, request
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

bot = telebot.TeleBot(TOKEN, threaded=False)
groq_client = Groq(api_key=GROQ_API_KEY)

# --- THE KEYBOARD (The Fix) ---
def get_main_menu():
    # We removed 'is_persistent' because older Telegram clients glitch with it.
    # Instead, we just re-send it often.
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.row('💰 Total', '🏆 Highest')
    markup.row('📜 History', '🧠 Analyze')
    markup.row('❓ Help')
    return markup

# --- AI & DB HELPERS ---
def ask_ai(prompt):
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            # Updated to the latest stable model
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"My brain hurts: {e}"

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
    
    if category == "Uncategorized":
        ai_cat = ask_ai(f"Categorize this expense item into one word (e.g., Food, Transport, Tech). Output ONLY the word: '{item}'")
        if ai_cat:
            category = ai_cat.strip().split()[0].replace(".", "")

    payload = {"item": item, "amount": amount, "category": category}
    requests.post(url, json=payload, headers=headers)
    return category

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "🤖 **ContabilBOT Online**\n\n"
        "I am ready to judge your spending.\n"
        "Type `50 Pizza` to track an expense.\n"
        "Or use the buttons below 👇"
    )
    # forcing send_message instead of reply_to can sometimes help UI glitches
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(commands=['help', 'commands'])
def send_help(message):
    help_text = """
    📋 **Command Cheat Sheet**
    
    **Manual Commands:**
    • `/total` - See total spending
    • `/highest` - Your most expensive mistake
    • `/history` - Last 5 items
    • `/analyze` - AI Financial Therapy
    
    **How to Track:**
    Simply type the amount followed by the item name:
    • `200 Groceries`
    • `50 Taxi`
    """
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == '❓ Help')
def help_btn(message):
    send_help(message)

# --- STATS HANDLERS ---

@bot.message_handler(commands=['total'])
def show_total(message):
    res = run_query("expenses?select=amount")
    if res.status_code == 200:
        data = res.json()
        total = sum([float(x['amount']) for x in data])
        bot.reply_to(message, f"💰 **Total Spent:** {total:,.2f} MDL", reply_markup=get_main_menu())
    else:
        bot.reply_to(message, "❌ Database error.")

@bot.message_handler(func=lambda m: m.text == '💰 Total')
def total_btn(message):
    show_total(message)

@bot.message_handler(commands=['highest'])
def show_highest(message):
    res = run_query("expenses?select=item,amount&order=amount.desc&limit=1")
    if res.status_code == 200 and len(res.json()) > 0:
        top = res.json()[0]
        bot.reply_to(message, f"🏆 **Highest Expense:**\n{top['amount']} on {top['item']}", reply_markup=get_main_menu())
    else:
        bot.reply_to(message, "No expenses found.")

@bot.message_handler(func=lambda m: m.text == '🏆 Highest')
def highest_btn(message):
    show_highest(message)

@bot.message_handler(commands=['history'])
def show_history(message):
    res = run_query("expenses?select=item,amount,category,created_at&order=created_at.desc&limit=5")
    if res.status_code == 200:
        expenses = res.json()
        text = "📜 **Last 5 Expenses:**\n"
        for ex in expenses:
            date_obj = datetime.fromisoformat(ex['created_at'].replace('Z', '+00:00'))
            date_str = date_obj.strftime("%d/%m")
            text += f"`{date_str}`: {ex['amount']} - {ex['item']} ({ex['category']})\n"
        bot.reply_to(message, text, parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == '📜 History')
def history_btn(message):
    show_history(message)

@bot.message_handler(commands=['analyze'])
def run_analysis(message):
    bot.send_chat_action(message.chat.id, 'typing')
    res = run_query("expenses?select=item,amount,category&order=created_at.desc&limit=20")
    data = res.json()
    
    if not data:
        bot.reply_to(message, "You have no expenses to analyze.")
        return

    expense_list = "\n".join([f"- {x['amount']} on {x['item']} ({x['category']})" for x in data])
    prompt = f"Here are my last 20 expenses:\n{expense_list}\nAct as a rude, sarcastic financial advisor. Summarize habits, point out the stupidest purchase, and give harsh advice. Keep it under 100 words."
    
    analysis = ask_ai(prompt)
    bot.reply_to(message, f"🧠 **The Verdict:**\n\n{analysis}", parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == '🧠 Analyze')
def analyze_btn(message):
    run_analysis(message)

# --- MAIN LISTENER ---
@bot.message_handler(func=lambda message: True)
def handle_expense(message):
    try:
        text = message.text.strip()
        parts = text.split()
        
        if len(parts) < 2:
            return 
            
        amount = float(parts[0])
        item = ' '.join(parts[1:])
        
        category = save_expense(item, amount)
        
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