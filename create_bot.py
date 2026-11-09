#!/usr/bin/env python3
"""Self-create a Telegram bot via the 'new BotFather' paths. No official
HTTP BotFather API exists - there are two real programmatic routes:

1. MANAGED BOTS (new, MTProto): `bots.createBot` (core.telegram.org/method/
   bots.createBot) creates a bot owned by a USER, controlled by a manager
   bot that has the `bot_can_manage_bots` flag. Needs MTProto user login
   (api_id/api_hash from my.telegram.org). Try: --managed @YourManagerBot
   After creation its token is fetched with the Bot API endpoint
   `getManagedBotToken` (called with the MANAGER bot's token + managed
   bot's user_id; `replaceManagedBotToken` rotates it). Those endpoints
   only work for managed bots - a regular BotFather-created bot already
   returns its token in the BotFather chat, so they don't apply there.
2. AUTOMATE @BotFather CHAT (MTProto): log in as a user with Telethon,
   send /newbot to @BotFather, answer name/username, parse the token.
   This is what telegram-bot-manager (GramJS) does. Default below.
Configuration (name/description/commands) for EITHER kind of bot is done
with the Bot API endpoints setMyName/setMyDescription/
setMyShortDescription/setMyCommands using the bot's own token - no
BotFather chat needed for that step (see configure_via_bot_api).

Usage:
  pip install telethon
  export TELEGRAM_API_ID=... TELEGRAM_API_HASH=...   # my.telegram.org/apps
  python3 create_bot.py --name "Boardgame Bot" --username flip7groupbot
  # interactive: enter your phone + login code once; session saved to
  # flip7_user.session (keep secret!). Token written to .env
Then:  set -a; . ./.env; python3 bot.py
Without API credentials it prints the manual @BotFather steps instead.
"""
import argparse, json, os, re, sys, time, urllib.request

TOKEN_RE = re.compile(r"\b(\d{8,12}:[A-Za-z0-9_-]{30,})\b")
HERE = os.path.dirname(os.path.abspath(__file__))


def bot_api(token, method, **params):
    """Call a Bot API method with a bot token (stdlib HTTP, no MTProto)."""
    data = json.dumps(params).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}", data=data,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def get_managed_bot_token(manager_token, managed_user_id):
    """Bot API: getManagedBotToken - ONLY for managed bots (see docstring).
    Must be called with the manager bot's token, not a regular bot's."""
    return bot_api(manager_token, "getManagedBotToken", user_id=int(managed_user_id))


def replace_managed_bot_token(manager_token, managed_user_id):
    return bot_api(manager_token, "replaceManagedBotToken",
                   user_id=int(managed_user_id))


def load_token():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        for line in open(path):
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.strip().split("=", 1)[1]
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def configure_via_bot_api(token, name="Boardgame Bot"):
    """setMyName / setMyDescription / setMyShortDescription / setMyCommands
    with the bot's own token. Returns True if commands verified."""
    print(bot_api(token, "setMyName", name=name))
    print(bot_api(token, "setMyDescription",
                  description="Flip 7 card game for groups: /newgame, /join, /startgame, /hit, /stay."))
    print(bot_api(token, "setMyShortDescription",
                  short_description="Flip 7 group card game - first to 200 wins."))
    cmds = [{"command": c.split(" - ")[0], "description": c.split(" - ", 1)[1]}
            for c in COMMANDS.split("\n")]
    print(bot_api(token, "setMyCommands", commands=cmds))
    got = bot_api(token, "getMyCommands")
    print("getMyCommands:", got.get("result"))
    return bool(got.get("ok") and got["result"])
COMMANDS = (
    "newgame - Create a Flip 7 game\n"
    "join - Join the lobby\n"
    "startgame - Creator starts the game\n"
    "hit - Flip another card\n"
    "stay - Bank your cards\n"
    "web - Play the HTML5 version\n"
    "play - Play Flip 7 (HTML game)\n"
    "regicide - Co-op Regicide game\n"
    "odin - Card-shedding Odin game\n"
    "lsd - Let's Summon Demons dice game\n"
    "spots - Push-your-luck Spots dog dice\n"
    "games - List the games you can start\n"
    "join_npc - Add a mock player anyone can control\n"
    "score - Show board and scores\n"
    "rules - How to play Flip 7\n"
    "cancel - Creator cancels the game\n"
    "help - Help"
)


def manual_steps(name, username):
    print(f"""
No MTProto credentials found - create the bot manually (2 minutes):
  1. Open @BotFather in Telegram, send /newbot
  2. Name: {name}
  3. Username: {username}   (must end in 'bot'; if taken, pick another)
  4. Copy the token BotFather gives you, then:
       export TELEGRAM_BOT_TOKEN=<token>
       python3 bot.py
  5. Optional BotFather settings: /setdescription, /setabouttext,
     /setcommands (paste the list in COMMANDS), /setprivacy -> Disable
     (so the bot reads /join etc. in groups), /setadmins in BotFather
     if you want it to see all group messages.
Get api_id/api_hash at https://my.telegram.org/apps to use the
automated paths above instead.
""")


async def botfather_chat(client, name, username):
    from telethon.tl.custom import Dialog  # noqa: F401  (ensures telethon present)
    async def send_and_wait(text, timeout=30):
        before = await client.get_messages("BotFather", limit=1)
        last_id = before[0].id if before else 0
        await client.send_message("BotFather", text)
        for _ in range(timeout):
            async for msg in client.iter_messages("BotFather", limit=5):
                if msg.id > last_id and msg.out is False and msg.text:
                    return msg.text
            await asyncio.sleep(1)
        raise TimeoutError(f"No BotFather reply to {text!r}")

    import asyncio
    print("→ /newbot")
    await send_and_wait("/newbot")
    print(f"→ name: {name}")
    await send_and_wait(name)
    print(f"→ username: {username}")
    reply = await send_and_wait(username)
    m = TOKEN_RE.search(reply)
    if not m:
        raise SystemExit(f"BotFather didn't return a token. Reply was:\n{reply}")
    token = m.group(1)
    try:
        configure_via_bot_api(token, name)  # Bot API, not BotFather chat
    except Exception as e:
        print(f"  (Bot API config skipped, token is key: {e})")
    return token


async def configure_botfather(client, username):
    """BotFather config is 3-step: /cmd -> which bot? (username) -> value."""
    import asyncio

    async def send_and_wait(text, timeout=30):
        before = await client.get_messages("BotFather", limit=1)
        last_id = before[0].id if before else 0
        await client.send_message("BotFather", text)
        for _ in range(timeout):
            async for msg in client.iter_messages("BotFather", limit=5):
                if msg.id > last_id and msg.out is False and msg.text:
                    return msg.text
            await asyncio.sleep(1)
        raise TimeoutError(f"No BotFather reply to {text!r}")

    async def send_and_wait_msg(text, timeout=30):
        before = await client.get_messages("BotFather", limit=1)
        last_id = before[0].id if before else 0
        await client.send_message("BotFather", text)
        for _ in range(timeout):
            async for msg in client.iter_messages("BotFather", limit=5):
                if msg.id > last_id and msg.out is False and msg.text:
                    return msg
            await asyncio.sleep(1)
        raise TimeoutError(f"No BotFather reply to {text!r}")

    async def click_bot(msg, username):
        for row in (msg.buttons or []):
            for btn in row:
                if username.lower() in (btn.text or "").lower().replace("@", ""):
                    await msg.click(data=btn.data)
                    return True
        return False

    for cmd, payload in (("/setdescription",
                          "Flip 7 card game for groups: /newgame, /join, /startgame, /hit, /stay."),
                         ("/setabouttext", "Flip 7 group card game - first to 200 wins."),
                         ("/setcommands", COMMANDS)):
        try:
            prompt = await send_and_wait_msg(cmd)
            if not await click_bot(prompt, username):
                print(f"  ({cmd} skipped: bot button not found)")
                continue
            reply = await send_and_wait(payload)
            print(f"{cmd}: {reply[:120]}")
        except Exception as e:
            print(f"  ({cmd} skipped: {e})")


async def managed_bot(client, manager, name, username):
    """bots.createBot: manager bot needs bot_can_manage_bots. Returns User;
    token is then delivered via the manager/BotFather flow - print both."""
    try:
        from telethon.tl.functions.bots import CreateBot, CheckUsername
    except ImportError:  # telethon>=1.40: only *Request classes
        from telethon.tl.functions.bots import CreateBotRequest as CreateBot
        from telethon.tl.functions.bots import CheckUsernameRequest as CheckUsername
    entity = await client.get_input_entity(manager)
    try:
        ok = await client(CheckUsername(username))
        print(f"username available: {ok}")
    except Exception as e:
        print(f"checkUsername: {e}")
    user = await client(CreateBot(name=name, username=username, manager_id=entity))
    print(f"Managed bot created: id={user.id} username={username}")
    manager_token = os.environ.get("MANAGER_BOT_TOKEN", "")
    if manager_token:
        # Bot API endpoint for managed bots only:
        r = get_managed_bot_token(manager_token, user.id)
        print("getManagedBotToken:", r.get("ok"))
        if r.get("ok"):
            with open(os.path.join(HERE, ".env"), "w") as f:
                f.write(f"TELEGRAM_BOT_TOKEN={r['result']}\n")
            print("Token saved to .env")
    else:
        print("Set MANAGER_BOT_TOKEN to fetch the token via getManagedBotToken.")
    return user


LOGIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".login.json")


async def amain(args):
    import asyncio, json
    if args.configure:
        token = load_token()
        if token:
            configure_via_bot_api(token, args.name)
            return
        # no token yet: fall through to MTProto BotFather configure below
    try:
        from telethon import TelegramClient as AsyncClient  # telethon>=1.40
    except ImportError:
        try:
            from telethon.asyncio import TelegramClient as AsyncClient
        except ImportError:
            manual_steps(args.name, args.username)
            return
    api_id, api_hash = os.environ.get("TELEGRAM_API_ID"), os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        manual_steps(args.name, args.username)
        return
    session = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flip7_user")
    client = AsyncClient(session, int(api_id), api_hash)
    await client.connect()  # not `async with`: that auto-calls start()/prompts
    try:
        if args.request_code:
            if not args.phone:
                sys.exit("--request-code needs --phone +<countrycode><number>")
            sent = await client.send_code_request(args.phone)
            with open(LOGIN_FILE, "w") as f:
                json.dump({"phone": args.phone,
                           "phone_code_hash": sent.phone_code_hash}, f)
            print(f"CODE_SENT to {args.phone} - awaiting login code")
            return
        if args.code:
            if not os.path.exists(LOGIN_FILE):
                sys.exit("no .login.json - run with --request-code first")
            saved = json.load(open(LOGIN_FILE))
            from telethon.errors import SessionPasswordNeededError
            try:
                await client.sign_in(saved["phone"], args.code,
                                     phone_code_hash=saved["phone_code_hash"])
            except SessionPasswordNeededError:
                if not args.password:
                    sys.exit("2FA_REQUIRED - re-run with --password <password>")
                await client.sign_in(password=args.password)
            os.remove(LOGIN_FILE)
            print("LOGGED_IN")
        elif not await client.is_user_authorized():
            await client.start()  # interactive fallback
        if args.configure:
            await configure_botfather(client, args.username)
            return
        if args.managed:
            await managed_bot(client, args.managed, args.name, args.username)
            print("Managed bot created - get its token from your manager bot / @BotFather /mybots.")
            return
        token = await botfather_chat(client, args.name, args.username)
    finally:
        await client.disconnect()
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), "w") as f:
        f.write(f"TELEGRAM_BOT_TOKEN={token}\n")
    print(f"\n✅ Bot created! Token saved to .env (keep it secret)")
    print(f"   Chat it at https://t.me/{args.username} - then run:  set -a; . ./.env; python3 bot.py")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", default="Boardgame Bot")
    ap.add_argument("--username", default="flip7groupbot",
                    help="must end in 'bot', unique, 5-32 chars")
    ap.add_argument("--managed", metavar="@ManagerBot",
                    help="new managed-bots path: bots.createBot via this manager bot")
    ap.add_argument("--phone", help="phone with country code, e.g. +15551234567")
    ap.add_argument("--request-code", action="store_true",
                    help="send login code to --phone and exit (two-step login)")
    ap.add_argument("--code", help="login code from Telegram, completes login")
    ap.add_argument("--password", help="two-step verification password (if enabled)")
    ap.add_argument("--configure", action="store_true",
                    help="set name/description/commands via Bot API setMy* endpoints (uses .env token; MTProto/BotFather only as fallback)")
    args = ap.parse_args()
    if not args.username.lower().endswith("bot"):
        sys.exit("username must end in 'bot'")
    import asyncio
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
