# ContabilBOT - Telegram Expense Tracker with Roast

A serverless Telegram bot that tracks expenses in Google Sheets and roasts you for spending money.

## Setup

### 1. Create Google Sheet

1. Create a new Google Spreadsheet named "Budget"
2. Add headers in row 1: `Date | Item | Amount | Category`
3. Create a service account in Google Cloud Console
4. Share the sheet with the service account's email address

### 2. Environment Variables

Add these in Vercel Dashboard → Settings → Environment Variables:

| Variable | Description |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `SHEET_NAME` | Name of Google Sheet (default: "Budget") |
| `GOOGLE_CREDS_JSON` | Full JSON content of service account credentials |

### 3. Telegram Webhook Setup

After deployment, set the webhook using this URL format:

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<YOUR-VERCEL-APP>.vercel.app/
```

Replace:
- `<TOKEN>` with your Telegram bot token
- `<YOUR-VERCEL-APP>` with your Vercel deployment name

Example:
```
https://api.telegram.org/bot123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11/setWebhook?url=https://my-contabilbot.vercel.app/
```

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
