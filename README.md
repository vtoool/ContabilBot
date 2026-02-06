# ContabilBOT - Telegram Expense Tracker with Roast

A serverless Telegram bot that tracks expenses in Supabase and roasts you for spending money.

## Setup

### 1. Supabase Setup

1. Create a new Supabase project
2. Create a table named `expenses` with columns:
   - `id` (bigint, auto-generated)
   - `item` (text)
   - `amount` (numeric)
   - `category` (text, default: 'Uncategorized')
   - `created_at` (timestamp with timezone, auto-generated)

### 2. Environment Variables

Add these in Vercel Dashboard → Settings → Environment Variables:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/public key |

### 3. Telegram Webhook Setup

After deployment, set the webhook using this URL format:

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<YOUR-VERCEL-APP>.vercel.app/
```

Replace:
- `<TOKEN>` with your Telegram bot token
- `<YOUR-VERCEL-APP>` with your Vercel deployment name

### 4. Usage

Send messages to your bot in format:
```
[Amount] [Item]
```

Examples:
- `50 Coffee`
- `120 Lunch`
- `15.50 Taxi`

The bot will record the expense and roast you.

## Deployment

1. Push to GitHub
2. Import in Vercel
3. Add environment variables
4. Deploy
5. Set webhook URL
