# GET Jobs Bot

Telegram bot that scans 60+ job sources for **Graduate Engineer Trainee (GET)** roles across India — both IT and Non-IT — and alerts you with tags:

- `GET[IT]` — software / IT trainee roles
- `GET[Non-IT]` — mechanical, civil, electrical, electronics, chemical & other core branches

Runs daily at **9:00 AM & 9:00 PM IST**. Already-sent jobs are never repeated.

## Railway Deployment

1. Create a new bot via [@BotFather](https://t.me/BotFather) → copy the token
2. **Open Telegram, find your new bot, press START** (the bot cannot message you before this!)
3. Get your numeric chat id from [@userinfobot](https://t.me/userinfobot)
4. Deploy this repo on [Railway](https://railway.app) and set variables:
   - `GET_TELEGRAM_BOT_TOKEN` = token from BotFather
   - `GET_TELEGRAM_CHAT_ID` = your numeric chat id
5. (Recommended) Mount a Volume and set `GET_DATA_DIR=/data` so sent-job history survives redeploys

Optional variables for more results: `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `JOOBLE_API_KEY`

## Commands

| Command | Description |
|---|---|
| `/check` | Force a scan now |
| `/sources` | Show all sources & health |
| `/status` | Last scan stats |
| `/seen` | Recently sent jobs |
| `/export` | Download jobs as CSV |

## Troubleshooting

**Bot not responding?**
- Check Railway deploy logs for `INVALID BOT TOKEN` → re-copy the token from BotFather
- Logs say `Could not message chat_id` → press START on the bot in Telegram first, and confirm chat id is your numeric user id
- Did you redeploy after setting the variables?

## Sources (60+)

Workday, Greenhouse, Lever, SmartRecruiters, Ashby, Adzuna, Jooble, Remotive,
Arbeitnow, RemoteOK, LinkedIn, Unstop, Internshala + India portals,
PSU career pages (ISRO, DRDO, NTPC, BHEL...) & mass-recruiter off-campus portals.
