import os
import requests
from flask import Flask, request, jsonify
import telebot
from telebot.types import Update
from datetime import datetime, timedelta
from groq import Groq

app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "contabil123")

bot = telebot.TeleBot(TOKEN, threaded=False)
groq_client = Groq(api_key=GROQ_API_KEY)

CATEGORIES = [
    "Food",
    "Transport",
    "Tech",
    "Utilities",
    "Entertainment",
    "Health",
    "Misc",
]


def supabase_request(endpoint, method="GET", json_body=None, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    try:
        if method == "GET":
            return requests.get(url, headers=headers, params=params)
        elif method == "POST":
            return requests.post(url, headers=headers, json=json_body, params=params)
    except Exception as e:
        return None


def strict_categorization(item_text):
    categories_str = ", ".join(CATEGORIES)
    prompt = f"""Categorize this expense into EXACTLY ONE of these categories: {categories_str}.
Output ONLY the category name, nothing else.
Expense: "{item_text}"
Category:"""
    try:
        result = ask_ai(prompt).strip()
        for cat in CATEGORIES:
            if cat.lower() in result.lower():
                return cat
        return "Misc"
    except:
        return "Misc"


def ask_ai(prompt):
    try:
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"


def get_main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=False
    )
    markup.row("💰 Total", "🏆 Highest")
    markup.row("📜 History", "🧠 Analyze")
    markup.row("❓ Help")
    return markup


# --- DASHBOARD SECURE PROXY ENDPOINTS ---


@app.route("/api/stats", methods=["GET"])
def api_stats():
    password = request.headers.get("X-Dashboard-Password")
    if password != DASHBOARD_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    now = datetime.now()
    first_of_month = now.replace(day=1).strftime("%Y-%m-%d")

    # Total spent this month
    total_response = supabase_request(
        f"expenses?created_at=gte.{first_of_month}&select=amount"
    )
    total_spent = 0
    if total_response and total_response.status_code == 200:
        total_spent = sum([float(x.get("amount", 0)) for x in total_response.json()])

    # Categories breakdown
    cat_response = supabase_request("expenses?select=category,amount")
    categories = {}
    if cat_response and cat_response.status_code == 200:
        for item in cat_response.json():
            cat = item.get("category", "Misc")
            categories[cat] = categories.get(cat, 0) + float(item.get("amount", 0))

    # Last 10 expenses
    hist_response = supabase_request(
        "expenses?select=item,amount,category,created_at&order=created_at.desc&limit=10"
    )
    history = []
    if hist_response and hist_response.status_code == 200:
        for item in hist_response.json():
            history.append(
                {
                    "item": item.get("item", ""),
                    "amount": float(item.get("amount", 0)),
                    "category": item.get("category", "Misc"),
                    "date": item.get("created_at", "")[:10],
                }
            )

    # Financial profile
    profile_response = supabase_request("financial_profile?select=budget,goals")
    budget = 0
    goals = "Save money"
    if (
        profile_response
        and profile_response.status_code == 200
        and profile_response.json()
    ):
        profile = profile_response.json()[0]
        budget = float(profile.get("budget", 0))
        goals = profile.get("goals", "Save money")

    return jsonify(
        {
            "total": total_spent,
            "budget": budget,
            "remaining": budget - total_spent,
            "categories": categories,
            "history": history,
            "goals": goals,
        }
    )


@app.route("/api/profile", methods=["GET", "POST"])
def api_profile():
    password = request.headers.get("X-Dashboard-Password")
    if password != DASHBOARD_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == "POST":
        data = request.json or {}
        supabase_request("financial_profile", method="POST", json_body=data)
        return jsonify({"success": True})

    profile_response = supabase_request("financial_profile?select=budget,goals")
    if (
        profile_response
        and profile_response.status_code == 200
        and profile_response.json()
    ):
        return jsonify(profile_response.json()[0])
    return jsonify({"budget": 0, "goals": "Save money"})


# --- TELEGRAM BOT ---


@app.route("/", methods=["POST"])
def webhook():
    if not TOKEN:
        return "Error", 500
    json_str = request.get_data().decode("UTF-8")
    update = Update.de_json(json_str)
    if update:
        bot.process_new_updates([update])
    return "OK", 200


@bot.message_handler(commands=["start"])
def send_welcome(message):
    welcome = "🤖 **ContabilBOT Online**\n\nType `50 Pizza` to track an expense."
    bot.send_message(
        message.chat.id, welcome, parse_mode="Markdown", reply_markup=get_main_menu()
    )


@bot.message_handler(commands=["help"])
def send_help(message):
    help_text = """📋 **Commands**
• `/total` - Total spending
• `/highest` - Most expensive
• `/history` - Last 5 items
• `/analyze` - AI Analysis"""
    bot.send_message(
        message.chat.id, help_text, parse_mode="Markdown", reply_markup=get_main_menu()
    )


@bot.message_handler(func=lambda m: m.text == "❓ Help")
def help_btn(message):
    send_help(message)


@bot.message_handler(commands=["total"])
def show_total(message):
    res = supabase_request("expenses?select=amount")
    if res and res.status_code == 200:
        total = sum([float(x.get("amount", 0)) for x in res.json()])
        bot.reply_to(
            message, f"💰 **Total:** {total:,.0f} MDL", reply_markup=get_main_menu()
        )


@bot.message_handler(func=lambda m: m.text == "💰 Total")
def total_btn(message):
    show_total(message)


@bot.message_handler(commands=["highest"])
def show_highest(message):
    res = supabase_request("expenses?select=item,amount&order=amount.desc&limit=1")
    if res and res.status_code == 200 and res.json():
        top = res.json()[0]
        bot.reply_to(
            message,
            f"🏆 **Highest:** {top['amount']} on {top['item']}",
            reply_markup=get_main_menu(),
        )


@bot.message_handler(func=lambda m: m.text == "🏆 Highest")
def highest_btn(message):
    show_highest(message)


@bot.message_handler(commands=["history"])
def show_history(message):
    res = supabase_request(
        "expenses?select=item,amount,category,created_at&order=created_at.desc&limit=5"
    )
    if res and res.status_code == 200:
        text = "📜 **Last 5:**\n"
        for ex in res.json():
            date = ex.get("created_at", "")[:10]
            text += f"{date}: {ex['amount']} - {ex['item']} ({ex.get('category', 'Misc')})\n"
        bot.reply_to(message, text, parse_mode="Markdown", reply_markup=get_main_menu())


@bot.message_handler(func=lambda m: m.text == "📜 History")
def history_btn(message):
    show_history(message)


@bot.message_handler(commands=["analyze"])
def analyze(message):
    bot.send_chat_action(message.chat.id, "typing")
    profile_res = supabase_request("financial_profile?select=budget,goals")
    budget = 0
    goals = "Save money"
    if profile_res and profile_res.status_code == 200 and profile_res.json():
        p = profile_res.json()[0]
        budget = float(p.get("budget", 0))
        goals = p.get("goals", "Save money")

    res = supabase_request(
        "expenses?select=item,amount,category&order=created_at.desc&limit=20"
    )
    if not res or res.status_code != 200 or not res.json():
        bot.reply_to(message, "No expenses to analyze.")
        return

    expense_list = "\n".join(
        [
            f"- {x['amount']} on {x['item']} ({x.get('category', 'Misc')})"
            for x in res.json()
        ]
    )
    prompt = f"""User Goal: {goals}. Budget: {budget}.
Recent Spend: {expense_list}.
Analyze spending behavior and give feedback based on their goal. Keep under 100 words."""

    analysis = ask_ai(prompt)
    bot.reply_to(
        message,
        f"🧠 **Analysis:**\n\n{analysis}",
        parse_mode="Markdown",
        reply_markup=get_main_menu(),
    )


@bot.message_handler(func=lambda m: m.text == "🧠 Analyze")
def analyze_btn(message):
    analyze(message)


@bot.message_handler(func=lambda m: True)
def handle_expense(message):
    try:
        text = message.text.strip()
        parts = text.split()
        if len(parts) < 2:
            return
        amount = float(parts[0])
        item = " ".join(parts[1:])
        category = strict_categorization(item)

        supabase_request(
            "expenses",
            method="POST",
            json_body={"item": item, "amount": amount, "category": category},
        )

        bot.reply_to(
            message,
            f"💸 Saved: {amount} - {item}\n📂 {category}",
            reply_markup=get_main_menu(),
        )
    except ValueError:
        bot.reply_to(message, "⚠️ Format: `50 Pizza`", reply_markup=get_main_menu())


@app.route("/", methods=["GET"])
def index():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "../public/index.html")

    try:
        with open(html_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: Could not find dashboard file.", 404


@app.route("/", methods=["POST"])
def webhook():
    if not TOKEN:
        return "Error", 500
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200
