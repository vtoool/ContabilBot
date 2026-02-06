import os
import requests
from flask import Flask, request, jsonify, make_response
import telebot
from telebot import types
from datetime import datetime
from groq import Groq

app = Flask(__name__)

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")

bot = telebot.TeleBot(TOKEN, threaded=False)
groq_client = Groq(api_key=GROQ_API_KEY)


# --- DATABASE HELPERS ---
def run_query(endpoint, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    return requests.get(url, headers=headers, params=params)


def save_expense(item, amount, category="Uncategorized"):
    url = f"{SUPABASE_URL}/rest/v1/expenses"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    if category == "Uncategorized":
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": f"Categorize this expense item into one word (e.g., Food, Transport, Tech). Output ONLY the word: '{item}'",
                    }
                ],
                model="llama-3.3-70b-versatile",
            )
            ai_cat = (
                chat_completion.choices[0]
                .message.content.strip()
                .split()[0]
                .replace(".", "")
            )
            if ai_cat:
                category = ai_cat
        except:
            pass

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


# --- API ROUTES ---


@app.route("/api/stats", methods=["GET"])
def get_dashboard_stats():
    if request.headers.get("X-Dashboard-Password") != DASHBOARD_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    cat_res = run_query("expenses?select=category,amount")
    hist_res = run_query(
        "expenses?select=item,amount,created_at&order=created_at.desc&limit=10"
    )

    if cat_res.status_code != 200:
        return jsonify({"error": "DB Error"}), 500

    expenses = cat_res.json()
    category_totals = {}
    for ex in expenses:
        cat = ex["category"] or "Uncategorized"
        category_totals[cat] = category_totals.get(cat, 0) + float(ex["amount"])

    return jsonify(
        {
            "categories": category_totals,
            "history": hist_res.json(),
            "total_spent": sum(category_totals.values()),
        }
    )


# --- MAIN ROUTE (HTML + BOT) ---
@app.route("/", methods=["GET", "POST"])
def handle_root():
    if request.method == "GET":
        # Serve the embedded HTML directly
        return make_response(DASHBOARD_HTML)

    elif request.method == "POST":
        if not TOKEN:
            return "Error", 500
        json_str = request.get_data().decode("UTF-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "OK", 200


# --- BOT LOGIC ---
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Total", "🏆 Highest")
    markup.row("📜 History", "🧠 Analyze")
    markup.row("❓ Help")
    return markup


@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "🤖 **ContabilBOT CFO Online**\nI'm ready to judge your spending.\nType `/help` for instructions.",
        parse_mode="Markdown",
        reply_markup=get_main_menu(),
    )


@bot.message_handler(commands=["help"])
def send_help(message):
    help_text = """
    📚 **ContabilBOT User Manual**

    **1. Tracking Expenses:**
    Just type the amount and the item.
    • `50 Coffee`
    • `200 Taxi to airport`
    *(I will auto-categorize it for you)*

    **2. The Dashboard:**
    View your charts and full history here:
    👉 [Open Financial Command Center](https://contabil-bot.vercel.app/)
    *(You will need your password)*

    **3. Commands:**
    💰 **Total** - See how much you spent.
    🏆 **Highest** - Your biggest expense.
    🧠 **Analyze** - Get a brutal AI roast of your habits.
    """
    bot.send_message(
        message.chat.id, help_text, parse_mode="Markdown", reply_markup=get_main_menu()
    )


@bot.message_handler(func=lambda m: m.text == "❓ Help")
def help_btn(message):
    send_help(message)


@bot.message_handler(func=lambda m: m.text == "💰 Total")
@bot.message_handler(commands=["total"])
def show_total(message):
    res = run_query("expenses?select=amount")
    if res.status_code == 200:
        total = sum([float(x["amount"]) for x in res.json()])
        bot.reply_to(
            message, f"💰 Total: {total:,.2f} MDL", reply_markup=get_main_menu()
        )


@bot.message_handler(func=lambda m: m.text == "🏆 Highest")
@bot.message_handler(commands=["highest"])
def show_highest(message):
    res = run_query("expenses?select=item,amount&order=amount.desc&limit=1")
    if res.status_code == 200 and len(res.json()) > 0:
        top = res.json()[0]
        bot.reply_to(
            message,
            f"🏆 Highest: {top['amount']} on {top['item']}",
            reply_markup=get_main_menu(),
        )


@bot.message_handler(func=lambda m: m.text == "📜 History")
@bot.message_handler(commands=["history"])
def show_history(message):
    res = run_query(
        "expenses?select=item,amount,category,created_at&order=created_at.desc&limit=5"
    )
    if res.status_code == 200:
        text = "📜 **Recent:**\n"
        for ex in res.json():
            date_str = datetime.fromisoformat(
                ex["created_at"].replace("Z", "+00:00")
            ).strftime("%d/%m")
            text += f"`{date_str}`: {ex['amount']} - {ex['item']}\n"
        bot.reply_to(message, text, parse_mode="Markdown", reply_markup=get_main_menu())


@bot.message_handler(func=lambda m: m.text == "🧠 Analyze")
@bot.message_handler(commands=["analyze"])
def run_analysis(message):
    bot.send_chat_action(message.chat.id, "typing")
    res = run_query(
        "expenses?select=item,amount,category&order=created_at.desc&limit=20"
    )
    if not res.json():
        bot.reply_to(message, "No data.")
        return
    expense_list = "\n".join(
        [f"- {x['amount']} on {x['item']} ({x['category']})" for x in res.json()]
    )
    analysis = ask_ai(
        f"Last 20 expenses:\n{expense_list}\nRoast this user's spending habits."
    )
    bot.reply_to(
        message,
        f"🧠 **Verdict:**\n{analysis}",
        parse_mode="Markdown",
        reply_markup=get_main_menu(),
    )


@bot.message_handler(func=lambda message: True)
def handle_expense(message):
    try:
        parts = message.text.strip().split()
        if len(parts) < 2:
            return
        amount = float(parts[0])
        item = " ".join(parts[1:])
        category = save_expense(item, amount)
        bot.reply_to(
            message,
            f"💸 Saved: {amount} for {item}.\n📂 {category}",
            reply_markup=get_main_menu(),
        )
    except:
        pass


# --- EMBEDDED DASHBOARD HTML ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ContabilBOT CFO</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-gray-900 text-white font-sans antialiased">
    <div id="loginModal" class="fixed inset-0 bg-black bg-opacity-90 flex items-center justify-center z-50">
        <div class="bg-gray-800 p-8 rounded-xl w-96 text-center border border-gray-700">
            <h2 class="text-2xl font-bold mb-4 text-green-400">🔐 Login</h2>
            <input type="password" id="passwordInput" class="w-full p-3 bg-gray-900 border border-gray-600 rounded text-white mb-4" placeholder="Password">
            <button onclick="login()" class="w-full bg-green-500 hover:bg-green-600 text-black font-bold py-3 rounded">Unlock</button>
        </div>
    </div>
    <div id="dashboard" class="hidden container mx-auto p-6">
        <header class="flex justify-between items-center mb-10">
            <h1 class="text-3xl font-bold text-green-400">💰 Financial Command Center</h1>
            <button onclick="logout()" class="text-xs text-gray-500 hover:text-white">Logout</button>
        </header>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
            <div class="bg-gray-800 p-6 rounded-2xl border border-gray-700">
                <h3 class="text-gray-400 text-sm uppercase">Total Spent</h3>
                <p id="totalSpent" class="text-4xl font-mono font-bold text-white mt-2">Loading...</p>
            </div>
            <div class="bg-gray-800 p-6 rounded-2xl border border-gray-700">
                <h3 class="text-gray-400 text-sm uppercase">Status</h3>
                <p class="text-4xl font-mono font-bold text-green-400 mt-2">ACTIVE</p>
            </div>
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="bg-gray-800 p-6 rounded-2xl border border-gray-700 lg:col-span-1">
                <canvas id="catChart"></canvas>
            </div>
            <div class="bg-gray-800 p-6 rounded-2xl border border-gray-700 lg:col-span-2">
                <table class="w-full text-left">
                    <thead><tr class="text-gray-500 border-b border-gray-700"><th class="pb-3">Date</th><th class="pb-3">Item</th><th class="pb-3 text-right">Amount</th></tr></thead>
                    <tbody id="historyTable" class="text-gray-300"></tbody>
                </table>
            </div>
        </div>
    </div>
    <script>
        const API_URL = '/api/stats';
        function login() {
            const pass = document.getElementById('passwordInput').value;
            localStorage.setItem('dash_pass', pass);
            loadDashboard();
        }
        function logout() { localStorage.removeItem('dash_pass'); location.reload(); }
        async function loadDashboard() {
            const pass = localStorage.getItem('dash_pass');
            if (!pass) return;
            try {
                const res = await fetch(API_URL, { headers: { 'X-Dashboard-Password': pass } });
                if (res.status === 401) { alert("Wrong Password!"); return; }
                const data = await res.json();
                document.getElementById('loginModal').classList.add('hidden');
                document.getElementById('dashboard').classList.remove('hidden');
                document.getElementById('totalSpent').innerText = data.total_spent.toLocaleString() + ' MDL';
                new Chart(document.getElementById('catChart'), {
                    type: 'doughnut',
                    data: {
                        labels: Object.keys(data.categories),
                        datasets: [{ data: Object.values(data.categories), backgroundColor: ['#34D399', '#60A5FA', '#F87171', '#FBBF24', '#A78BFA', '#F472B6'] }]
                    },
                    options: { plugins: { legend: { position: 'bottom', labels: { color: '#9CA3AF' } } } }
                });
                document.getElementById('historyTable').innerHTML = data.history.map(item => `
                    <tr class="border-b border-gray-800"><td class="py-3 text-sm text-gray-400">${new Date(item.created_at).toLocaleDateString()}</td><td class="py-3">${item.item}</td><td class="py-3 text-right text-green-400">${item.amount}</td></tr>
                `).join('');
            } catch (err) { console.error(err); }
        }
        if(localStorage.getItem('dash_pass')) loadDashboard();
    </script>
</body>
</html>
"""
