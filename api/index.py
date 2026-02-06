import os
import json
import requests
import telebot
from flask import Flask, request, jsonify, make_response
from telebot.types import Update
from datetime import datetime, timedelta
from groq import Groq

app = Flask(__name__)

# --- CONFIG ---
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

# === EMBEDDED DASHBOARD HTML ===
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ContabilBOT CFO Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #0f172a; color: #e2e8f0; }
        .card { background-color: #1e293b; border-radius: 16px; padding: 1.5rem; }
        .chat-widget { position: fixed; bottom-4 right-4; z-index: 50; }
        .chat-window { display: none; position: fixed; bottom-20 right-4; width: 380px; height: 520px; background: #1e293b; border-radius: 16px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6); flex-direction: column; overflow: hidden; border: 1px solid #334155; }
        .chat-messages { flex: 1; overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
        .chat-input { background: #0f172a; border-top: 1px solid #334155; padding: 0.75rem; }
        .chat-message { max-width: 85%; padding: 0.75rem 1rem; border-radius: 12px; font-size: 0.875rem; line-height: 1.4; }
        .chat-user { background: #2563eb; color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
        .chat-assistant { background: #334155; color: #e2e8f0; align-self: flex-start; border-bottom-left-radius: 4px; }
        .typing-indicator { display: flex; gap: 4px; padding: 0.75rem 1rem; background: #334155; border-radius: 12px; align-self: flex-start; width: fit-content; }
        .typing-dot { width: 8px; height: 8px; background: #9ca3af; border-radius: 50%; animation: typing 1.4s infinite; }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-4px); } }
    </style>
</head>
<body class="min-h-screen">
    <div id="loginModal" class="fixed inset-0 bg-black/90 flex items-center justify-center z-50">
        <div class="card max-w-sm mx-4 w-full text-center">
            <div class="mb-4 text-4xl">🔐</div>
            <h2 class="text-2xl font-bold mb-2 text-green-400">ContabilBOT CFO</h2>
            <p class="text-gray-400 mb-6 text-sm">Enter your dashboard password</p>
            <input type="password" id="password" placeholder="Password" 
                   class="w-full bg-gray-700 border border-gray-600 text-white px-4 py-3 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-green-500"
                   onkeypress="if(event.key==='Enter')login()">
            <button onclick="login()" class="w-full bg-green-500 hover:bg-green-600 text-black font-bold py-3 rounded-lg transition">
                Unlock Dashboard
            </button>
            <p id="errorMsg" class="text-red-400 mt-4 text-sm hidden">Invalid password. Try again.</p>
        </div>
    </div>

    <div id="dashboard" class="hidden p-4 md:p-6 max-w-7xl mx-auto">
        <header class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-3xl font-bold text-green-400">💰 Financial Command Center</h1>
                <p class="text-gray-400 text-sm">v5.0 - Agentic CFO</p>
            </div>
            <div class="flex items-center gap-4">
                <span class="text-xs text-gray-500">Powered by Groq</span>
                <button onclick="logout()" class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg text-sm font-medium transition">Logout</button>
            </div>
        </header>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div class="card">
                <p class="text-gray-400 text-xs uppercase tracking-wider">Income (Month)</p>
                <p class="text-2xl md:text-3xl font-bold text-green-400 mt-1" id="incomeTotal">-</p>
            </div>
            <div class="card">
                <p class="text-gray-400 text-xs uppercase tracking-wider">Expenses (Month)</p>
                <p class="text-2xl md:text-3xl font-bold text-red-400 mt-1" id="expenseTotal">-</p>
            </div>
            <div class="card">
                <p class="text-gray-400 text-xs uppercase tracking-wider">Net Savings</p>
                <p class="text-2xl md:text-3xl font-bold mt-1" id="netSavings">-</p>
            </div>
            <div class="card">
                <p class="text-gray-400 text-xs uppercase tracking-wider">Monthly Budget</p>
                <p class="text-2xl md:text-3xl font-bold text-blue-400 mt-1" id="budgetDisplay">-</p>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
            <div class="card">
                <h3 class="text-lg font-bold mb-4 flex items-center gap-2"><span>📊</span> Spending by Category</h3>
                <div class="h-64"><canvas id="catChart"></canvas></div>
            </div>
            <div class="card">
                <h3 class="text-lg font-bold mb-4 flex items-center gap-2"><span>📈</span> Income vs Expenses</h3>
                <div class="h-64"><canvas id="incomeChart"></canvas></div>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
            <div class="card">
                <h3 class="text-lg font-bold mb-4 flex items-center gap-2"><span>🔄</span> Subscriptions <span class="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded" id="subBadge">0</span></h3>
                <div id="subscriptionsList" class="space-y-2 max-h-48 overflow-y-auto"><p class="text-gray-500 text-sm">Loading...</p></div>
            </div>
            <div class="card">
                <h3 class="text-lg font-bold mb-4 flex items-center gap-2"><span>🎯</span> Savings Goals</h3>
                <div id="goalsList" class="space-y-3 max-h-48 overflow-y-auto"><p class="text-gray-500 text-sm">Loading...</p></div>
            </div>
        </div>

        <div class="card">
            <h3 class="text-lg font-bold mb-4 flex items-center gap-2"><span>📜</span> Recent Transactions</h3>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead><tr class="text-left text-gray-400 border-b border-gray-700"><th class="pb-3 pr-4 text-sm">Date</th><th class="pb-3 pr-4 text-sm">Item</th><th class="pb-3 pr-4 text-sm">Category</th><th class="pb-3 text-right text-sm">Amount</th></tr></thead>
                    <tbody id="transactionsTable" class="text-sm"><tr><td colspan="4" class="py-4 text-center text-gray-500">Loading...</td></tr></tbody>
                </table>
            </div>
        </div>

        <div class="card mt-4">
            <h3 class="text-lg font-bold mb-2">🎯 User Goals</h3>
            <p id="userGoals" class="text-gray-300">Loading...</p>
        </div>
    </div>

    <div class="chat-widget">
        <button onclick="toggleChat()" class="bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 rounded-full p-4 shadow-lg transition transform hover:scale-105">
            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
            </svg>
        </button>
        <div id="chatWindow" class="chat-window">
            <div class="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-800">
                <div class="flex items-center gap-2"><span class="text-xl">🤖</span><h3 class="font-bold">CFO Chat</h3></div>
                <button onclick="toggleChat()" class="text-gray-400 hover:text-white transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <div id="chatMessages" class="chat-messages">
                <div class="chat-message chat-assistant">
                    <p class="font-semibold mb-1">🤖 ContabilBOT CFO</p>
                    <p>Hey! I'm your Agentic CFO. Ask me anything about your finances:</p>
                    <ul class="mt-2 space-y-1 text-xs opacity-75">
                        <li>• "How much did I spend on food this month?"</li>
                        <li>• "Log 50 for coffee"</li>
                        <li>• "What's my net savings?"</li>
                        <li>• "Show my subscriptions"</li>
                    </ul>
                </div>
            </div>
            <div class="chat-input">
                <input type="text" id="chatInput" placeholder="Ask about your finances..." 
                       class="w-full bg-gray-700 text-white px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
                       onkeypress="if(event.key==='Enter')sendChatMessage()">
            </div>
        </div>
    </div>

    <script>
        const API = '/api';
        let catChart = null;
        let incomeChart = null;
        let chatHistory = [];

        function getHeaders() { return { 'X-Dashboard-Password': localStorage.getItem('dash_pwd') || '', 'Content-Type': 'application/json' }; }

        function toggleChat() {
            const w = document.getElementById('chatWindow');
            const isHidden = w.style.display === 'none' || w.style.display === '';
            w.style.display = isHidden ? 'flex' : 'none';
            if (isHidden) document.getElementById('chatInput').focus();
        }

        function addMessage(role, text) {
            const m = document.getElementById('chatMessages');
            const div = document.createElement('div');
            div.className = 'chat-message ' + (role === 'user' ? 'chat-user' : 'chat-assistant');
            div.innerHTML = role === 'assistant' ? '<p class="font-semibold mb-1">🤖 ContabilBOT</p><p>' + text + '</p>' : '<p>' + text + '</p>';
            m.appendChild(div);
            m.scrollTop = m.scrollHeight;
            chatHistory.push({ role, content: text });
            if (chatHistory.length > 10) chatHistory.shift();
        }

        function showTyping() {
            const m = document.getElementById('chatMessages');
            const div = document.createElement('div');
            div.id = 'typingIndicator';
            div.className = 'typing-indicator';
            div.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
            m.appendChild(div);
            m.scrollTop = m.scrollHeight;
        }

        function hideTyping() { const typing = document.getElementById('typingIndicator'); if (typing) typing.remove(); }

        async function sendChatMessage() {
            const input = document.getElementById('chatInput');
            const msg = input.value.trim();
            if (!msg) return;
            addMessage('user', msg);
            input.value = '';
            showTyping();
            try {
                const res = await fetch(API + '/chat', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ message: msg, history: chatHistory }) });
                hideTyping();
                if (res.status === 401) { addMessage('assistant', '❌ Unauthorized. Please reload and enter the correct password.'); return; }
                if (!res.ok) { addMessage('assistant', '❌ Error: Could not connect to the CFO agent.'); return; }
                const data = await res.json();
                addMessage('assistant', data.response || 'No response received.');
            } catch (e) { hideTyping(); addMessage('assistant', '❌ Connection error: ' + e.message); }
        }

        function login() {
            const pwd = document.getElementById('password').value;
            if (!pwd) return;
            localStorage.setItem('dash_pwd', pwd);
            loadDashboard();
        }

        function logout() { localStorage.removeItem('dash_pwd'); chatHistory = []; location.reload(); }

        async function loadDashboard() {
            try {
                const res = await fetch(API + '/stats', { headers: getHeaders() });
                if (res.status === 401) { document.getElementById('errorMsg').classList.remove('hidden'); document.getElementById('password').value = ''; return; }
                if (!res.ok) { alert('Failed to load dashboard data'); return; }
                document.getElementById('loginModal').classList.add('hidden');
                document.getElementById('dashboard').classList.remove('hidden');
                renderDashboard(await res.json());
            } catch (e) { console.error('Dashboard load error:', e); alert('Failed to connect.'); }
        }

        function renderDashboard(data) {
            document.getElementById('incomeTotal').textContent = (data.income || 0).toLocaleString();
            document.getElementById('expenseTotal').textContent = (data.expenses || 0).toLocaleString();
            document.getElementById('netSavings').textContent = (data.net || 0).toLocaleString();
            document.getElementById('netSavings').className = 'text-2xl md:text-3xl font-bold mt-1 ' + ((data.net || 0) >= 0 ? 'text-green-400' : 'text-red-400');
            document.getElementById('budgetDisplay').textContent = (data.budget || 0).toLocaleString();
            document.getElementById('userGoals').textContent = data.goals || 'Save money';
            renderCatChart(data.categories || {});
            renderIncomeChart(data.income || 0, data.expenses || 0);
            renderTransactions(data.history || []);
            renderSubscriptions(data.subscriptions || []);
            renderGoals(data.savings_goals || []);
        }

        function renderCatChart(cats) {
            const ctx = document.getElementById('catChart').getContext('2d');
            if (catChart) catChart.destroy();
            const labels = Object.keys(cats);
            const values = Object.values(cats);
            if (labels.length === 0) { labels.push('No Data'); values.push(1); }
            catChart = new Chart(ctx, { type: 'doughnut', data: { labels: labels, datasets: [{ data: values, backgroundColor: ['#ef4444', '#f97316', '#eab308', '#22c55e', '#06b6d4', '#8b5cf6', '#6b7280'].slice(0, labels.length), borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#9ca3af', padding: 10 } } } } });
        }

        function renderIncomeChart(income, expenses) {
            const ctx = document.getElementById('incomeChart').getContext('2d');
            if (incomeChart) incomeChart.destroy();
            incomeChart = new Chart(ctx, { type: 'bar', data: { labels: ['Income', 'Expenses'], datasets: [{ data: [income, expenses], backgroundColor: ['#22c55e', '#ef4444'], borderRadius: 8 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { color: '#9ca3af' }, grid: { color: '#334155' } }, x: { ticks: { color: '#9ca3af' }, grid: { display: false } } } } });
        }

        function renderTransactions(history) {
            const tbody = document.getElementById('transactionsTable');
            if (!history || history.length === 0) { tbody.innerHTML = '<tr><td colspan="4" class="py-4 text-center text-gray-500">No transactions yet</td></tr>'; return; }
            tbody.innerHTML = history.map(e => '<tr class="border-b border-gray-700 hover:bg-gray-800/50 transition"><td class="py-3 pr-4 text-gray-400">' + (e.date || '-') + '</td><td class="py-3 pr-4">' + (e.item || '-') + '</td><td class="py-3 pr-4"><span class="bg-gray-700 px-2 py-0.5 rounded text-xs">' + (e.category || 'Misc') + '</span></td><td class="py-3 text-right text-red-400 font-medium">' + (e.amount || 0).toLocaleString() + '</td></tr>').join('');
        }

        function renderSubscriptions(subs) {
            const container = document.getElementById('subscriptionsList');
            document.getElementById('subBadge').textContent = subs.length;
            if (!subs || subs.length === 0) { container.innerHTML = '<p class="text-gray-500 text-sm">No active subscriptions</p>'; return; }
            container.innerHTML = subs.map(s => '<div class="flex justify-between items-center bg-gray-800 p-3 rounded-lg"><div class="flex items-center gap-3"><span class="text-lg">🔄</span><div><p class="font-medium text-sm">' + s.name + '</p><p class="text-xs text-gray-500">' + s.billing_cycle + '</p></div></div><span class="text-red-400 font-medium">-' + s.amount.toLocaleString() + '</span></div>').join('');
        }

        function renderGoals(goals) {
            const container = document.getElementById('goalsList');
            if (!goals || goals.length === 0) { container.innerHTML = '<p class="text-gray-500 text-sm">No savings goals set</p>'; return; }
            container.innerHTML = goals.map(g => { var target = g.target_amount || 1; var current = g.current_amount || 0; var pct = Math.min(100, (current / target) * 100); var remaining = target - current; return '<div class="bg-gray-800 p-3 rounded-lg"><div class="flex justify-between items-center mb-2"><span class="font-medium text-sm">' + g.name + '</span><span class="text-xs text-gray-400">' + current.toLocaleString() + ' / ' + target.toLocaleString() + '</span></div><div class="w-full bg-gray-700 rounded-full h-2 mb-1"><div class="bg-gradient-to-r from-blue-500 to-blue-400 h-2 rounded-full transition-all" style="width: ' + pct + '%"></div></div><p class="text-xs text-gray-500">' + (remaining > 0 ? remaining.toLocaleString() + ' remaining' : 'Goal reached! 🎉') + '</p></div>'; }).join('');
        }

        if (localStorage.getItem('dash_pwd')) { document.getElementById('password').value = localStorage.getItem('dash_pwd'); loadDashboard(); }
    </script>
</body>
</html>
"""


# --- SUPABASE HELPER (Now supports all methods) ---
def supabase_request(endpoint, method="GET", json_body=None, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        if method == "GET":
            return requests.get(url, headers=headers, params=params)
        elif method == "POST":
            return requests.post(url, headers=headers, json=json_body, params=params)
        elif method == "PATCH":
            return requests.patch(url, headers=headers, json=json_body, params=params)
        elif method == "DELETE":
            return requests.delete(url, headers=headers, params=params)
    except Exception as e:
        print(f"Supabase error: {e}")
        return None


# --- CATEGORIZATION ---
def strict_categorization(item_text):
    """Use AI to categorize expense, fallback to 'Misc'"""
    if not GROQ_API_KEY:
        return "Misc"

    categories_str = ", ".join(CATEGORIES)
    prompt = f"""Categorize this expense into EXACTLY ONE of these categories: {categories_str}.
Output ONLY the category name, nothing else.
Expense: "{item_text}"
Category:"""

    try:
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        for cat in CATEGORIES:
            if cat.lower() in result.lower():
                return cat
        return "Misc"
    except Exception as e:
        print(f"Categorization error: {e}")
        return "Misc"


# === TOOL DEFINITIONS (Native Groq Schema) ===
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tool_log_transaction",
            "description": "Log a financial transaction (expense or income). Use for purchases, income, refunds, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["expense", "income"],
                        "description": "Transaction type",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount in local currency",
                    },
                    "item": {
                        "type": "string",
                        "description": "Item name or description",
                    },
                    "category": {
                        "type": "string",
                        "enum": CATEGORIES,
                        "description": "Category for expenses (optional, AI will infer if not provided)",
                    },
                },
                "required": ["type", "amount", "item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_get_analytics",
            "description": "Query financial data for analytics, summaries, or specific questions about spending/income.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "enum": ["expenses", "income", "subscriptions"],
                    },
                    "filter_item": {
                        "type": "string",
                        "description": "Partial match on item name (e.g., 'Uber')",
                    },
                    "category": {"type": "string", "description": "Filter by category"},
                    "start_date": {
                        "type": "string",
                        "description": "ISO date (e.g., '2024-01-01')",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "ISO date (e.g., '2024-01-31')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_manage_subscription",
            "description": "Add, update, or cancel a recurring subscription. Use for Netflix, gym, software, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "update", "cancel"]},
                    "name": {"type": "string", "description": "Subscription name"},
                    "amount": {"type": "number", "description": "Monthly amount"},
                    "billing_cycle": {
                        "type": "string",
                        "enum": ["weekly", "monthly", "yearly"],
                        "description": "Billing frequency",
                    },
                },
                "required": ["action", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_get_summary",
            "description": "Get a quick financial summary (income vs expenses, net savings) for a period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": [
                            "today",
                            "this_week",
                            "this_month",
                            "last_month",
                            "this_year",
                            "all_time",
                        ],
                    }
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_update_savings",
            "description": "Update progress on a savings goal or add money toward it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {
                        "type": "string",
                        "description": "Name of savings goal",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount to add to savings",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["add", "set_target", "create"],
                    },
                },
                "required": ["goal_name"],
            },
        },
    },
]


# === TOOL IMPLEMENTATIONS ===
def tool_log_transaction(type, amount, item, category=None):
    """Log expense or income to Supabase"""
    if type == "expense":
        # Auto-categorize if not provided
        if not category:
            category = strict_categorization(item)

        data = {"item": item, "amount": float(amount), "category": category}
        resp = supabase_request("expenses", method="POST", json_body=data)
        success = resp and resp.status_code in (200, 201)
        message = (
            f"Logged expense: {amount} on {item} ({category})"
            if success
            else "Failed to log expense"
        )
    else:
        data = {"amount": float(amount), "source": item}
        resp = supabase_request("income", method="POST", json_body=data)
        success = resp and resp.status_code in (200, 201)
        message = (
            f"Logged income: {amount} from {item}"
            if success
            else "Failed to log income"
        )

    return {"success": success, "message": message}


def tool_get_analytics(
    table="expenses",
    filter_item=None,
    category=None,
    start_date=None,
    end_date=None,
    limit=10,
):
    """Query expenses/income with filters"""
    # Build filter string for Supabase
    filters = []
    if start_date:
        filters.append(f"created_at=gte.{start_date}")
    if end_date:
        filters.append(f"created_at=lte.{end_date}")

    filter_str = "&".join(filters) if filters else ""
    endpoint = f"{table}?select=*"
    if filter_str:
        endpoint += f"&{filter_str}"
    endpoint += f"&limit={limit}"

    resp = supabase_request(endpoint)
    if not resp or resp.status_code != 200:
        return {"success": False, "error": "Query failed"}

    results = resp.json()

    # Apply post-query filters
    if filter_item:
        results = [
            r
            for r in results
            if filter_item.lower() in r.get("item", "").lower()
            or filter_item.lower() in r.get("source", "").lower()
        ]
    if category:
        results = [r for r in results if r.get("category") == category]

    total = sum(float(r.get("amount", 0)) for r in results)
    return {"success": True, "data": results, "count": len(results), "total": total}


def tool_manage_subscription(action, name, amount=None, billing_cycle="monthly"):
    """UPSERT subscription"""
    if action == "cancel":
        # Soft delete - update is_active
        resp = supabase_request(
            f"subscriptions?name=eq.{name}",
            method="PATCH",
            json_body={"is_active": False},
        )
        success = resp and resp.status_code in (200, 201)
        message = f"Cancelled subscription: {name}"
    elif action == "update":
        data = {"amount": float(amount), "billing_cycle": billing_cycle}
        resp = supabase_request(
            f"subscriptions?name=eq.{name}", method="PATCH", json_body=data
        )
        success = resp and resp.status_code in (200, 201)
        message = f"Updated subscription: {name}"
    else:
        # Add new subscription
        data = {
            "name": name,
            "amount": float(amount) if amount else 0,
            "billing_cycle": billing_cycle,
            "is_active": True,
        }
        resp = supabase_request("subscriptions", method="POST", json_body=data)
        success = resp and resp.status_code in (200, 201)
        message = f"Added subscription: {name} ({amount}/{billing_cycle})"

    return {"success": success, "action": action, "name": name, "message": message}


def tool_update_savings(goal_name, amount=None, action="add"):
    """Update savings goal progress"""
    # Check if goal exists
    check = supabase_request(f"savings_goals?name=eq.{goal_name}")

    if not check or not check.json():
        # Create new goal
        target = amount if action == "set_target" else (amount or 1000)
        current = 0 if action in ["create", "set_target"] else (amount or 0)
        data = {"name": goal_name, "target_amount": target, "current_amount": current}
        resp = supabase_request("savings_goals", method="POST", json_body=data)
        success = resp and resp.status_code in (200, 201)
        message = f"Created savings goal: {goal_name} (Target: {target})"
    else:
        goal = check.json()[0]
        goal_id = goal.get("id")

        if action == "add":
            new_amount = goal["current_amount"] + (amount or 0)
            data = {"current_amount": new_amount}
            message = f"Added {amount} to {goal_name} (Now: {new_amount}/{goal['target_amount']})"
        elif action == "set_target":
            data = {"target_amount": amount}
            message = f"Set target for {goal_name} to {amount}"
        else:
            new_amount = amount or 0
            data = {"current_amount": new_amount}
            message = f"Set {goal_name} progress to {new_amount}"

        resp = supabase_request(
            f"savings_goals?id=eq.{goal_id}", method="PATCH", json_body=data
        )
        success = resp and resp.status_code in (200, 201)

    return {"success": success, "goal": goal_name, "action": action, "message": message}


def tool_get_summary(period="this_month"):
    """Get income vs expense summary"""
    now = datetime.now()

    # Calculate date ranges
    periods = {
        "today": (
            now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            now.isoformat(),
        ),
        "this_week": (
            (now - timedelta(days=now.weekday()))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .isoformat(),
            now.isoformat(),
        ),
        "this_month": (
            now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(),
            now.isoformat(),
        ),
        "last_month": (
            (now.replace(day=1) - timedelta(days=1))
            .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            .isoformat(),
            now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(),
        ),
        "this_year": (
            now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            ).isoformat(),
            now.isoformat(),
        ),
        "all_time": ("2020-01-01T00:00:00", now.isoformat()),
    }

    start, end = periods.get(period, periods["this_month"])

    # Query expenses
    exp_resp = supabase_request(
        f"expenses?created_at=gte.{start}&created_at=lte.{end}&select=amount,category"
    )
    exp_total = 0
    exp_by_cat = {}

    if exp_resp and exp_resp.status_code == 200:
        for e in exp_resp.json():
            amt = float(e.get("amount", 0))
            exp_total += amt
            cat = e.get("category", "Misc")
            exp_by_cat[cat] = exp_by_cat.get(cat, 0) + amt

    # Query income
    inc_resp = supabase_request(
        f"income?created_at=gte.{start}&created_at=lte.{end}&select=amount"
    )
    inc_total = 0
    if inc_resp and inc_resp.status_code == 200:
        for i in inc_resp.json():
            inc_total += float(i.get("amount", 0))

    # Query subscriptions
    sub_resp = supabase_request("subscriptions?is_active=eq.true&select=amount,name")
    subscriptions = []
    sub_total = 0
    if sub_resp and sub_resp.status_code == 200:
        for s in sub_resp.json():
            amt = float(s.get("amount", 0))
            sub_total += amt
            subscriptions.append({"name": s.get("name"), "amount": amt})

    # Query savings goals
    goals_resp = supabase_request(
        "savings_goals?is_active=eq.true&select=name,target_amount,current_amount"
    )
    goals = []
    if goals_resp and goals_resp.status_code == 200:
        goals = goals_resp.json()

    return {
        "success": True,
        "period": period,
        "income": inc_total,
        "expenses": exp_total,
        "net": inc_total - exp_total,
        "top_categories": dict(
            sorted(exp_by_cat.items(), key=lambda x: x[1], reverse=True)[:3]
        ),
        "subscriptions": subscriptions,
        "total_subscriptions": sub_total,
        "savings_goals": goals,
    }


# === AGENT LOOP ===
def agent_process_message(
    user_message: str, user_id: int = 1, chat_history: list = None
):
    """Main agent loop with native tool calling"""

    # Fetch user profile
    profile_resp = supabase_request(f"financial_profile?user_id=eq.{user_id}")
    profile = (
        profile_resp.json()[0]
        if profile_resp and profile_resp.json()
        else {"budget": 5000, "goals": "Save money"}
    )

    # Fetch chat history
    history_resp = supabase_request(
        f"chat_history?user_id=eq.{user_id}&order=created_at.desc&limit=10"
    )
    history = history_resp.json()[::-1] if history_resp and history_resp.json() else []

    # Build system prompt
    system_prompt = f"""You are ContabilBOT, a witty, sarcastic, but highly competent AI CFO.

Your personality:
- Sarcastic but helpful when analyzing finances
- Don't hold back on calling out wasteful spending
- Celebrate smart financial moves
- Keep responses concise but memorable

Your capabilities:
- You have access to tools to log transactions, query data, and manage subscriptions
- Always extract specific numbers (amounts, dates) from user queries
- For expense tracking, infer category if not provided
- For analytics questions, provide specific numbers and comparisons

Current User Profile:
- Budget: {profile.get("budget", 5000)} MDL
- Goals: {profile.get("goals", "Save money")}

Current date: {datetime.now().strftime("%Y-%m-%d")}

Remember: Call the appropriate tool BEFORE responding to get real data. Never make up numbers."""

    messages = [{"role": "system", "content": system_prompt}]

    # Add chat history
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})

    # Add current user message
    messages.append({"role": "user", "content": user_message})

    # Call Groq with tools
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.7,
        )
    except Exception as e:
        return f"Oops, my brain hiccuped: {str(e)}"

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls
    tool_results = []

    # Execute tool calls
    if tool_calls:
        for call in tool_calls:
            func_name = call.function.name
            func_args = json.loads(call.function.arguments)

            # Map function name to implementation
            func = globals().get(func_name)
            if func:
                try:
                    result = func(**func_args)
                except Exception as e:
                    result = {"success": False, "error": str(e)}

                tool_results.append(
                    {"tool": func_name, "arguments": func_args, "result": result}
                )

        # Save user message to history
        supabase_request(
            "chat_history",
            method="POST",
            json_body={"user_id": user_id, "role": "user", "content": user_message},
        )

        # Feed tool results back to LLM for final witty response
        messages.append(response_message)

        for i, result in enumerate(tool_results):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_calls[i].id,
                    "content": json.dumps(result["result"]),
                }
            )

        try:
            final_response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile", messages=messages, temperature=0.8
            )
            final_content = final_response.choices[0].message.content
        except Exception as e:
            final_content = (
                f"I got the data but my witty response generator failed: {str(e)}"
            )

        # Save assistant response with tool context
        supabase_request(
            "chat_history",
            method="POST",
            json_body={
                "user_id": user_id,
                "role": "assistant",
                "content": final_content,
                "tool_calls": json.dumps([tc.function.name for tc in tool_calls]),
                "tool_results": json.dumps(tool_results),
            },
        )

        return final_content
    else:
        # No tool calls needed
        content = (
            response_message.content or "I didn't understand that. Try rephrasing?"
        )

        supabase_request(
            "chat_history",
            method="POST",
            json_body={"user_id": user_id, "role": "assistant", "content": content},
        )

        return content


# === FLASK ENDPOINTS ===


@app.route("/api/stats", methods=["GET"])
def get_dashboard_stats():
    """Enhanced stats endpoint for v5.0 dashboard"""
    if request.headers.get("X-Dashboard-Password") != DASHBOARD_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    now = datetime.now()
    first_of_month = now.replace(day=1).strftime("%Y-%m-%d")

    # Expenses this month
    exp_resp = supabase_request(
        f"expenses?created_at=gte.{first_of_month}&select=amount,category,item,created_at"
    )
    expenses_month = exp_resp.json() if exp_resp and exp_resp.status_code == 200 else []

    # Income this month
    inc_resp = supabase_request(
        f"income?created_at=gte.{first_of_month}&select=amount,source,created_at"
    )
    income_month = inc_resp.json() if inc_resp and inc_resp.status_code == 200 else []

    # Categories breakdown (all time)
    cat_resp = supabase_request("expenses?select=category,amount")
    categories = {}
    if cat_resp and cat_resp.status_code == 200:
        for e in cat_resp.json():
            cat = e.get("category", "Misc")
            categories[cat] = categories.get(cat, 0) + float(e.get("amount", 0))

    # Recent transactions (last 10)
    hist_resp = supabase_request(
        "expenses?select=item,amount,category,created_at&order=created_at.desc&limit=10"
    )
    history = []
    if hist_resp and hist_resp.status_code == 200:
        for e in hist_resp.json():
            history.append(
                {
                    "item": e.get("item"),
                    "amount": float(e.get("amount", 0)),
                    "category": e.get("category", "Misc"),
                    "date": e.get("created_at", "")[:10],
                }
            )

    # Subscriptions
    sub_resp = supabase_request(
        "subscriptions?is_active=eq.true&select=name,amount,billing_cycle"
    )
    subscriptions = []
    sub_total = 0
    if sub_resp and sub_resp.status_code == 200:
        for s in sub_resp.json():
            amt = float(s.get("amount", 0))
            sub_total += amt
            subscriptions.append(
                {
                    "name": s.get("name"),
                    "amount": amt,
                    "billing_cycle": s.get("billing_cycle", "monthly"),
                }
            )

    # Savings goals
    goals_resp = supabase_request(
        "savings_goals?is_active=eq.true&select=name,target_amount,current_amount"
    )
    goals = goals_resp.json() if goals_resp and goals_resp.status_code == 200 else []

    # Profile
    prof_resp = supabase_request("financial_profile?user_id=eq.1")
    budget = 0
    goals_text = "Save money"
    if prof_resp and prof_resp.json():
        p = prof_resp.json()[0]
        budget = float(p.get("budget", 0))
        goals_text = p.get("goals", "Save money")

    total_spent = sum(float(e.get("amount", 0)) for e in expenses_month)
    total_income = sum(float(i.get("amount", 0)) for i in income_month)

    return jsonify(
        {
            "income": total_income,
            "expenses": total_spent,
            "net": total_income - total_spent,
            "budget": budget,
            "goals": goals_text,
            "categories": categories,
            "history": history,
            "subscriptions": subscriptions,
            "total_subscriptions": sub_total,
            "savings_goals": goals,
        }
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Chat endpoint for the dashboard widget"""
    password = request.headers.get("X-Dashboard-Password")
    if password != DASHBOARD_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    user_message = data.get("message", "")
    history = data.get("history", [])

    if not user_message.strip():
        return jsonify({"response": "You didn't say anything... 🤔"})

    response = agent_process_message(user_message, user_id=1, chat_history=history)
    return jsonify({"response": response})


@app.route("/", methods=["GET"])
def index():
    """Serve the dashboard HTML"""
    return DASHBOARD_HTML


@app.route("/", methods=["POST"])
def webhook():
    """Telegram webhook"""
    if not TOKEN:
        return "Error", 500

    try:
        json_str = request.get_data().decode("UTF-8")
        update = Update.de_json(json_str)
        if update:
            bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return "Error", 500


# === TELEGRAM HANDLERS ===


def get_main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=False
    )
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
    help_text = """📚 **ContabilBOT User Manual**

**1. Tracking Expenses:**
Just type the amount and the item.
• `50 Coffee`
• `200 Taxi to airport`
*(I will auto-categorize it for you)*

**2. Track Income:**
• `2000 Salary`
• `500 Freelance`

**3. Ask Questions:**
• "How much did I spend on food?"
• "What's my net savings this month?"
• "Show my subscriptions"

**4. The Dashboard:**
👉 https://contabil-bot.vercel.app/
*(You'll need your password)*

**5. Commands:**
💰 **Total** - Spending summary
🏆 **Highest** - Biggest expense
📜 **History** - Recent transactions
🧠 **Analyze** - AI roast of habits"""
    bot.send_message(
        message.chat.id, help_text, parse_mode="Markdown", reply_markup=get_main_menu()
    )


@bot.message_handler(func=lambda m: m.text == "❓ Help")
def help_btn(message):
    send_help(message)


@bot.message_handler(func=lambda m: m.text == "💰 Total")
@bot.message_handler(commands=["total"])
def total_btn(message):
    response = agent_process_message(
        "Give me my total spending and income summary for this month", chat_history=[]
    )
    bot.send_message(
        message.chat.id, response, parse_mode="Markdown", reply_markup=get_main_menu()
    )


@bot.message_handler(func=lambda m: m.text == "🏆 Highest")
@bot.message_handler(commands=["highest"])
def highest_btn(message):
    response = agent_process_message(
        "What was my highest single expense?", chat_history=[]
    )
    bot.send_message(
        message.chat.id, response, parse_mode="Markdown", reply_markup=get_main_menu()
    )


@bot.message_handler(func=lambda m: m.text == "📜 History")
@bot.message_handler(commands=["history"])
def history_btn(message):
    response = agent_process_message(
        "Show me my recent spending history with dates and categories", chat_history=[]
    )
    bot.send_message(
        message.chat.id, response, parse_mode="Markdown", reply_markup=get_main_menu()
    )


@bot.message_handler(func=lambda m: m.text == "🧠 Analyze")
@bot.message_handler(commands=["analyze"])
def analyze_btn(message):
    response = agent_process_message(
        "Analyze my spending habits and give me a witty roast with specific numbers",
        chat_history=[],
    )
    bot.send_message(
        message.chat.id, response, parse_mode="Markdown", reply_markup=get_main_menu()
    )


@bot.message_handler(func=lambda m: True)
def handle_message(message):
    """All other messages go through the agent"""
    response = agent_process_message(message.text)
    bot.send_message(
        message.chat.id, response, parse_mode="Markdown", reply_markup=get_main_menu()
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
