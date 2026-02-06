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
    # Try multiple paths for Vercel compatibility
    possible_paths = [
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "../public/index.html"
        ),
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "../../public/index.html"
        ),
        os.path.join(os.getcwd(), "public/index.html"),
        "/var/task/public/index.html",
        "/var/task/../public/index.html",
    ]

    # Add absolute path from repo root if we can detect it
    vercel_root = os.environ.get("VERCEL", "")
    if vercel_root:
        possible_paths.insert(0, "/var/task/public/index.html")

    html_content = None
    for html_path in possible_paths:
        try:
            if os.path.exists(html_path):
                with open(html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                    break
        except Exception:
            continue

    if html_content is not None:
        return html_content
    else:
        return (
            "Error: Dashboard file not found. Please ensure public/index.html exists.",
            404,
        )


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
