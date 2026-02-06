import os
import random
import requests
from flask import Flask, request
import telebot
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

# --- AI BRAIN (GROQ) ---
def ask_ai(prompt):
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama3-8b-8192", # Very fast, free tier friendly
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
    
    # Ask AI to guess category if it's generic
    if category == "Uncategorized":
        # Keep prompt short for speed
        ai_cat = ask_ai(f"Categorize this expense item into one word (e.g., Food, Transport, Tech). Output ONLY the word: '{item}'")
        if ai_cat:
            category = ai_cat.strip().split()[0].replace(".", "")

    payload = {"item": item, "amount": amount, "category": category}
    requests.post(url, json=payload, headers=headers)
    return category

# --- COMMANDS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = """
    📉 **ContabilBOT 3.0 (Groq Edition)**
    
    **Add Expense:**
    `50 Pizza` -> Saves 50 for Pizza
    
    **Commands:**
    💰 `/total` - Total spent (all time)
    🏆 `/highest` - Most expensive item
    📜 `/history` - Last 5 expenses
    🧠 `/analyze` - AI judges your spending habits
    """
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['total'])
def show_total(message):
    res = run_query("expenses?select=amount")
    if res.status_code == 200:
        data = res.json()
        total = sum([float(x['amount']) for x in data])
        bot.reply_to(message, f"💰 **Total Spent:** {total:,.2f} MDL", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Database error.")

@bot.message_handler(commands=['highest'])
def show_highest(message):
    res = run_query("expenses?select=item,amount&order=amount.desc&limit=1")
    if res.status_code == 200 and len(res.json()) > 0:
        top = res.json()[0]
        bot.reply_to(message, f"🏆 **Highest Expense:**\n{top['amount']} on *{top['item']}*", parse_mode="Markdown")
    else:
        bot.reply_to(message, "No expenses found.")

@bot.message_handler(commands=['history'])
def show_history(message):
    res = run_query("expenses?select=item,amount,category,created_at&order=created_at.desc&limit=5")
    if res.status_code == 200:
        expenses = res.json()
        text = "📜 **Last 5 Expenses:**\n"
        for ex in expenses:
            # Format date neatly
            date_obj = datetime.fromisoformat(ex['created_at'].replace('Z', '+00:00'))
            date_str = date_obj.strftime("%d/%m")
            text += f"`{date_str}`: {ex['amount']} - {ex['item']} ({ex['category']})\n"
        bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['analyze'])
def analyze_finances(message):
    bot.send_chat_action(message.chat.id, 'typing') # Show "typing..."
    
    # Get last 20 expenses
    res = run_query("expenses?select=item,amount,category&order=created_at.desc&limit=20")
    data = res.json()
    
    if not data:
        bot.reply_to(message, "You have no expenses. Are you a ghost?")
        return

    expense_list = "\n".join([f"- {x['amount']} on {x['item']} ({x['category']})" for x in data])
    
    prompt = f"""
    Here are my last 20 expenses:
    {expense_list}
    
    Act as a rude, sarcastic financial advisor. 
    1. Summarize my spending habits.
    2. Point out the stupidest purchase.
    3. Give me one piece of harsh advice.
    Keep it short (under 100 words).
    """
    
    analysis = ask_ai(prompt)
    bot.reply_to(message, f"🧠 **The Verdict:**\n\n{analysis}", parse_mode="Markdown")

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
        
        # Save and auto-categorize (now using Groq)
        category = save_expense(item, amount)
        
        bot.reply_to(message, f"💸 Saved: {amount} for {item}.\n📂 Category: {category}")

    except ValueError:
        bot.reply_to(message, "⚠️ Numbers first! Example: `50 Pizza`")
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