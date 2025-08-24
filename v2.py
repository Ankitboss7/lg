import os
import json
import time
from typing import Optional, Tuple, Dict, Any
import discord
from discord.ext import commands
import requests

# -------------- CONFIG --------------
PREFIX = "*"
TOKEN = ""
# Panel base config (Application API)
PANEL_URL = "http://103.194.228.138/"
PANEL_APP_KEY = "ptla_dKi5JYB14l8lq9dnfsixO7GHjkIo2wvUcv2iah6IXcL"

# Optional branding
BOT_VERSION = "27.6v"
MADE_BY = "Gamerzhacker"
SERVER_LOCATION = "India"
LOGO_URL = ""
PLANS_IMAGE_URL = ""
# Defaults for new servers
DEFAULT_ALLOCATION_ID = "1"

# Egg catalog (menu number → attributes)
# NOTE: Replace these IDs/startups/images for your panel
EGG_CATALOG = {
    1: {"name": "Paper",         "nest": 1, "egg": 4,  "docker_image": "ghcr.io/pterodactyl/yolks:java_17",   "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    2: {"name": "Forge",         "nest": 1, "egg": 2,  "docker_image": "ghcr.io/pterodactyl/yolks:java_17",   "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    3: {"name": "Bungeecord",    "nest": 1, "egg": 1,  "docker_image": "ghcr.io/pterodactyl/yolks:java_17",   "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    4: {"name": "Vanilla",       "nest": 1, "egg": 5,  "docker_image": "ghcr.io/pterodactyl/yolks:java_17",   "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    5: {"name": "Node.js",       "nest": 5, "egg": 17, "docker_image": "ghcr.io/pterodactyl/yolks:nodejs_18",  "startup": "node index.js"},
    6: {"name": "Python",        "nest": 5, "egg": 16, "docker_image": "ghcr.io/pterodactyl/yolks:python_3.11","startup": "python main.py"},
}

# Default environment vars for common eggs (auto-filled)
DEFAULT_ENV = {
    "SERVER_JARFILE": "server.jar",
    "EULA": "true",
    "VERSION": "latest",
    "BUILD_NUMBER": "1",
}

# Files (stored in working dir)
DATA_DIR = "."
ADMINS_FILE = os.path.join(DATA_DIR, "admins.txt")  # one discord ID per line
INVITES_FILE = os.path.join(DATA_DIR, "invites.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")   # { discord_id: {email, password, panel_id} }
CLIENT_KEYS_FILE = os.path.join(DATA_DIR, "client_keys.json")  # { discord_id: client_api_key }

for path, default in [
    (ADMINS_FILE, ""),
    (INVITES_FILE, "{}"),
    (USERS_FILE, "{}"),
    (CLIENT_KEYS_FILE, "{}"),
]:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(default)

# -------------- HELPERS --------------
def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_admins() -> set:
    try:
        with open(ADMINS_FILE, "r", encoding="utf-8") as f:
            ids = [x.strip() for x in f if x.strip()]
        return set(ids)
    except Exception:
        return set()

def save_admins(ids: set):
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        for i in ids:
            f.write(str(i) + "\n")

# Simple plan tiers (invite → limits)
TIERS = [
    {"name": "Basic",    "at": 0,  "ram": 4096,  "cpu": 150, "disk": 10000},
    {"name": "Advanced", "at": 4,  "ram": 6144,  "cpu": 200, "disk": 15000},
    {"name": "Pro",      "at": 6,  "ram": 7168,  "cpu": 230, "disk": 20000},
    {"name": "Premium",  "at": 8,  "ram": 9216,  "cpu": 270, "disk": 25000},
    {"name": "Elite",    "at": 15, "ram": 12288, "cpu": 320, "disk": 30000},
    {"name": "Ultimate", "at": 20, "ram": 16384, "cpu": 400, "disk": 35000},
]

def tier_for(invites: int) -> Dict[str, Any]:
    cur = TIERS[0]
    for t in TIERS:
        if invites >= t["at"]:
            cur = t
    return cur

# Panel request helpers (Application API)
APP_HEADERS = {
    "Authorization": f"Bearer {PANEL_APP_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def app_get(path: str, params: dict = None) -> requests.Response:
    return requests.get(f"{PANEL_URL}/api/application{path}", headers=APP_HEADERS, params=params or {}, timeout=30)

def app_post(path: str, payload: dict) -> requests.Response:
    return requests.post(f"{PANEL_URL}/api/application{path}", headers=APP_HEADERS, json=payload, timeout=45)

def app_delete(path: str) -> requests.Response:
    return requests.delete(f"{PANEL_URL}/api/application{path}", headers=APP_HEADERS, timeout=30)

# Client API (power actions, reinstall, allocations)
def client_headers(client_key: str) -> dict:
    return {"Authorization": f"Bearer {client_key}", "Content-Type": "application/json", "Accept": "application/json"}

def client_post(client_key: str, server_id: str, path: str, payload=None) -> requests.Response:
    return requests.post(f"{PANEL_URL}/api/client/servers/{server_id}{path}", headers=client_headers(client_key), json=payload or {}, timeout=30)

def client_get(client_key: str, server_id: str, path: str) -> requests.Response:
    return requests.get(f"{PANEL_URL}/api/client/servers/{server_id}{path}", headers=client_headers(client_key), timeout=30)

# -------------- DISCORD BOT --------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# -------------- UTILS --------------
def is_admin(uid: int) -> bool:
    return str(uid) in load_admins()

async def require_admin(ctx: commands.Context) -> bool:
    if not is_admin(ctx.author.id):
        await ctx.reply("You are not a bot admin.")
        return False
    return True

async def prompt_number(ctx: commands.Context, prompt: str, min_v: int, max_v: int, timeout: int = 60) -> Optional[int]:
    await ctx.send(f"{prompt} (min {min_v}, max {max_v})")
    def check(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        m = await bot.wait_for("message", timeout=timeout, check=check)
        v = int(m.content.strip())
        if min_v <= v <= max_v:
            return v
    except Exception:
        pass
    await ctx.send("Timed out or invalid value.")
    return None

# -------------- CORE CMDS --------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | Prefix {PREFIX}")

@bot.command(name="botinfo")
async def botinfo(ctx: commands.Context):
    embed = discord.Embed(title="🤖 Bot Info", color=discord.Color.blurple())
    embed.add_field(name="Version", value=BOT_VERSION)
    embed.add_field(name="Made by", value=MADE_BY)
    embed.add_field(name="Location", value=SERVER_LOCATION)
    if LOGO_URL:
        embed.set_thumbnail(url=LOGO_URL)
    await ctx.reply(embed=embed)

@bot.command(name="plans")
async def plans(ctx: commands.Context):
    lines = [f"**{t['name']}** — at {t['at']} invites\nRAM {t['ram']}MB | CPU {t['cpu']}% | Disk {t['disk']}MB" for t in TIERS]
    embed = discord.Embed(title="✨ Invite Plans", description="\n\n".join(lines), color=discord.Color.gold())
    if PLANS_IMAGE_URL:
        embed.set_image(url=PLANS_IMAGE_URL)
    await ctx.reply(embed=embed)

@bot.command(name="i")
async def invites_cmd(ctx: commands.Context, user: Optional[discord.Member] = None):
    target = user or ctx.author
    inv = load_json(INVITES_FILE)
    n = int(inv.get(str(target.id), 0))
    t = tier_for(n)
    embed = discord.Embed(title=f"💎 Invites — {target.display_name}", color=discord.Color.blue())
    embed.add_field(name="Total", value=str(n))
    embed.add_field(name="Tier", value=t['name'])
    embed.add_field(name="Limits", value=f"RAM {t['ram']}MB\nCPU {t['cpu']}%\nDisk {t['disk']}MB", inline=False)
    await ctx.reply(embed=embed)

# Register/link panel user
@bot.command(name="register")
async def register(ctx: commands.Context, email: str, password: str):
    users = load_json(USERS_FILE)
    if str(ctx.author.id) in users:
        await ctx.reply("You are already registered.")
        return
    payload = {
        "username": ctx.author.name,
        "email": email,
        "first_name": ctx.author.name,
        "last_name": "User",
        "password": password,
    }
    r = app_post("/users", payload)
    if r.status_code not in (200, 201):
        # maybe exists
        rr = app_get("/users", params={"filter[email]": email})
        if rr.status_code == 200 and rr.json().get("data"):
            pid = rr.json()["data"][0]["attributes"]["id"]
        else:
            await ctx.reply(f"❌ Panel error: {r.status_code}\n{r.text[:200]}")
            return
    else:
        pid = r.json()["attributes"]["id"]
    users[str(ctx.author.id)] = {"email": email, "password": password, "panel_id": pid}
    save_json(USERS_FILE, users)
    await ctx.reply(f"✅ Linked panel user ID **{pid}**. Use `{PREFIX}manage` to control servers.")

# Create server (only RAM/CPU/Disk inputs)
@bot.command(name="create")
async def create_server(ctx: commands.Context):
    users = load_json(USERS_FILE)
    invs = load_json(INVITES_FILE)
    u = users.get(str(ctx.author.id))
    if not u:
        await ctx.reply(f"Register first: `{PREFIX}register <email> <password>` or ask admin.")
        return
    my_inv = int(invs.get(str(ctx.author.id), 0))
    t = tier_for(my_inv)
    # choose egg
    opts = [f"{i}. {EGG_CATALOG[i]['name']}" for i in sorted(EGG_CATALOG.keys())]
    menu = "**Select server type:**\n" + "\n".join(opts) + f"\nReply with number 1-{len(opts)}"
    await ctx.send(menu)
    def check(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for("message", timeout=60, check=check)
        idx = int(msg.content.strip())
        if idx not in EGG_CATALOG:
            await ctx.send("Invalid choice.")
            return
    except Exception:
        await ctx.send("Timed out.")
        return
    egg = EGG_CATALOG[idx]

    ram = await prompt_number(ctx, f"Enter RAM MB", 256, t["ram"])
    if not ram: return
    cpu = await prompt_number(ctx, f"Enter CPU %", 10, t["cpu"])
    if not cpu: return
    disk = await prompt_number(ctx, f"Enter Disk MB", 1000, t["disk"])
    if not disk: return

    name = f"{ctx.author.name}-{int(time.time())}"
    payload = {
        "name": name,
        "user": u["panel_id"],
        "egg": egg["egg"],
        "docker_image": egg["docker_image"],
        "startup": egg["startup"],
        "limits": {"memory": ram, "swap": 0, "disk": disk, "io": 500, "cpu": cpu},
        "feature_limits": {"databases": 2, "backups": 2, "allocations": 1},
        "allocation": {"default": DEFAULT_ALLOCATION_ID},
        "environment": DEFAULT_ENV,
    }
    r = app_post("/servers", payload)
    if r.status_code not in (200, 201, 202):
        await ctx.reply(f"❌ Panel error {r.status_code}: {r.text[:300]}")
        return
    data = r.json().get("attributes", {})
    sid = data.get("identifier") or str(data.get("id"))
    embed = discord.Embed(title="✅ Server Created", color=discord.Color.green())
    embed.add_field(name="Name", value=name)
    embed.add_field(name="Type", value=egg["name"])
    embed.add_field(name="RAM/CPU/Disk", value=f"{ram}MB / {cpu}% / {disk}MB", inline=False)
    await ctx.reply(embed=embed)
    try:
        await ctx.author.send(f"Your server is ready on {PANEL_URL}. ID: {sid}")
    except Exception:
        pass

# -------------- ADMIN GROUP --------------
@bot.group(name="admin", invoke_without_command=True)
async def admin_group(ctx: commands.Context):
    await ctx.reply(f"Admin cmds: add_i, remove_i, add_a, rm_a, create_a, create_s, delete_s, rm_ac, newmsg, serverlist, lock, unlock")

@admin_group.command(name="add_i")
async def admin_add_i(ctx: commands.Context, user: discord.Member, amount: int):
    if not await require_admin(ctx): return
    inv = load_json(INVITES_FILE)
    inv[str(user.id)] = int(inv.get(str(user.id), 0)) + max(0, amount)
    save_json(INVITES_FILE, inv)
    await ctx.reply(f"✅ Added **{amount}** invites to {user.mention}. Total: {inv[str(user.id)]}")

@admin_group.command(name="remove_i")
async def admin_remove_i(ctx: commands.Context, user: discord.Member, amount: int):
    if not await require_admin(ctx): return
    inv = load_json(INVITES_FILE)
    cur = int(inv.get(str(user.id), 0))
    newv = max(0, cur - max(0, amount))
    inv[str(user.id)] = newv
    save_json(INVITES_FILE, inv)
    await ctx.reply(f"✅ Removed **{amount}** invites from {user.mention}. Total: {newv}")

@admin_group.command(name="add_a")
async def admin_add_a(ctx: commands.Context, user: discord.Member):
    if not await require_admin(ctx): return
    ids = load_admins(); ids.add(str(user.id)); save_admins(ids)
    await ctx.reply(f"✅ {user.mention} is now a bot admin.")

@admin_group.command(name="rm_a")
async def admin_rm_a(ctx: commands.Context, user: discord.Member):
    if not await require_admin(ctx): return
    ids = load_admins(); ids.discard(str(user.id)); save_admins(ids)
    await ctx.reply(f"✅ Removed admin: {user.mention}")

@admin_group.command(name="create_a")
async def admin_create_a(ctx: commands.Context, user: discord.Member, email: str, password: str):
    if not await require_admin(ctx): return
    users = load_json(USERS_FILE)
    payload = {"username": user.name, "email": email, "first_name": user.name, "last_name": "User", "password": password}
    r = app_post("/users", payload)
    if r.status_code not in (200, 201):
        rr = app_get("/users", params={"filter[email]": email})
        if rr.status_code == 200 and rr.json().get("data"):
            pid = rr.json()["data"][0]["attributes"]["id"]
        else:
            await ctx.reply(f"❌ Panel error: {r.status_code} {r.text[:200]}")
            return
    else:
        pid = r.json()["attributes"]["id"]
    users[str(user.id)] = {"email": email, "password": password, "panel_id": pid}
    save_json(USERS_FILE, users)
    try: await user.send(f"✅ Your panel account is ready!\nEmail: **{email}**\nPassword: **{password}**\nPanel: {PANEL_URL}")
    except Exception: pass
    await ctx.reply(f"✅ Linked panel user ID **{pid}** to {user.mention}")

@admin_group.command(name="create_s")
async def admin_create_s(ctx: commands.Context, name: str, owner_email: str):
    if not await require_admin(ctx): return
    users = load_json(USERS_FILE)
    owner_id = None
    for _, v in users.items():
        if v.get("email") == owner_email:
            owner_id = v.get("panel_id"); break
    if not owner_id:
        await ctx.reply("Owner email not linked. Use *admin create_a first.")
        return
    opts = [f"{i}. {EGG_CATALOG[i]['name']}" for i in sorted(EGG_CATALOG.keys())]
    await ctx.send("**Select server type:**\n" + "\n".join(opts))
    def check(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        m = await bot.wait_for("message", timeout=60, check=check)
        idx = int(m.content.strip())
        if idx not in EGG_CATALOG:
            await ctx.send("Invalid."); return
    except Exception:
        await ctx.send("Timed out."); return
    egg = EGG_CATALOG[idx]
    # Ask raw limits
    ram = await prompt_number(ctx, "Enter RAM MB", 256, 262144)
    if not ram: return
    cpu = await prompt_number(ctx, "Enter CPU %", 10, 1000)
    if not cpu: return
    disk = await prompt_number(ctx, "Enter Disk MB", 1000, 2097152)
    if not disk: return
    payload = {"name": name, "user": owner_id, "egg": egg["egg"], "docker_image": egg["docker_image"], "startup": egg["startup"],
               "limits": {"memory": ram, "swap": 0, "disk": disk, "io": 500, "cpu": cpu},
               "feature_limits": {"databases": 2, "backups": 2, "allocations": 1},
               "allocation": {"default": DEFAULT_ALLOCATION_ID},
               "environment": DEFAULT_ENV}
    r = app_post("/servers", payload)
    if r.status_code not in (200, 201, 202):
        await ctx.reply(f"❌ {r.status_code}: {r.text[:300]}"); return
    await ctx.reply("✅ Server created.")

@admin_group.command(name="delete_s")
async def admin_delete_s(ctx: commands.Context, *, name_contains: str):
    if not await require_admin(ctx): return
    rr = app_get("/servers")
    if rr.status_code != 200:
        await ctx.reply(f"List error {rr.status_code}"); return
    for d in rr.json().get("data", []):
        a = d.get("attributes", {})
        if name_contains.lower() in a.get("name", "").lower():
            sid = a.get("id")
            dr = app_delete(f"/servers/{sid}")
            if dr.status_code in (204,200):
                await ctx.reply(f"✅ Deleted '{a.get('name')}' (ID {sid})"); return
            else:
                await ctx.reply(f"❌ Delete error {dr.status_code}: {dr.text[:200]}"); return
    await ctx.reply("No matching server found.")

@admin_group.command(name="rm_ac")
async def admin_rm_ac(ctx: commands.Context, user: discord.Member):
    if not await require_admin(ctx): return
    users = load_json(USERS_FILE)
    u = users.get(str(user.id))
    if not u:
        await ctx.reply("User not linked in users.json"); return
    pid = u.get("panel_id")
    # delete servers first
    rr = app_get("/servers")
    if rr.status_code == 200:
        for d in rr.json().get("data", []):
            a = d.get("attributes", {})
            if a.get("user") == pid:
                app_delete(f"/servers/{a.get('id')}")
    # delete user
    dr = app_delete(f"/users/{pid}")
    if dr.status_code in (204,200):
        users.pop(str(user.id), None); save_json(USERS_FILE, users)
        await ctx.reply(f"✅ Removed panel account and servers for {user.mention}")
    else:
        await ctx.reply(f"❌ Panel error {dr.status_code}: {dr.text[:200]}")

@admin_group.command(name="newmsg")
async def admin_newmsg(ctx: commands.Context, channel_id: int):
    if not await require_admin(ctx): return
    ch = ctx.guild.get_channel(channel_id) or bot.get_channel(channel_id)
    if not ch:
        await ctx.reply("Channel not found"); return
    await ch.send("This is a broadcast message from admin.")
    await ctx.reply("✅ Sent.")

@admin_group.command(name="serverlist")
async def admin_serverlist(ctx: commands.Context):
    if not await require_admin(ctx): return
    rr = app_get("/servers")
    if rr.status_code != 200:
        await ctx.reply(f"❌ {rr.status_code}"); return
    lines = []
    for d in rr.json().get("data", []):
        a = d.get("attributes", {})
        lim = a.get("limits", {})
        lines.append(f"• {a.get('name')} — RAM {lim.get('memory')}MB CPU {lim.get('cpu')}% Disk {lim.get('disk')}MB")
    desc = "\n".join(lines) or "No servers."
    await ctx.reply(embed=discord.Embed(title="🖥️ Server List", description=desc, color=discord.Color.dark_gray()))

# -------------- MODERATION --------------
@admin_group.command(name="lock")
async def admin_lock(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    if not await require_admin(ctx): return
    ch = channel or ctx.channel
    overwrites = ch.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = False
    await ch.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    await ctx.reply(f"🔒 Locked {ch.mention}")

@admin_group.command(name="unlock")
async def admin_unlock(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    if not await require_admin(ctx): return
    ch = channel or ctx.channel
    overwrites = ch.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = True
    await ch.set_permissions(ctx.guild.default_role, overwrite=overwrites)
    await ctx.reply(f"🔓 Unlocked {ch.mention}")

@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_cmd(ctx: commands.Context, amount: int):
    deleted = await ctx.channel.purge(limit=min(max(amount,1), 500))
    await ctx.send(f"🧹 Cleared {len(deleted)} messages.", delete_after=5)

# -------------- NODE & SERVER INFO --------------
@bot.command(name="node")
async def node_status(ctx: commands.Context):
    r = app_get("/nodes")
    if r.status_code != 200:
        await ctx.reply("❌ Could not reach panel.")
        return
    names = [n.get("attributes", {}).get("name") for n in r.json().get("data", [])]
    desc = "\n".join([f"• {n} — Online" for n in names]) or "No nodes found."
    await ctx.reply(embed=discord.Embed(title="📡 Nodes", description=desc, color=discord.Color.green()))

@bot.command(name="serverinfo")
async def serverinfo(ctx: commands.Context):
    g = ctx.guild
    owner = g.owner
    boosts = g.premium_subscription_count
    level = g.premium_tier
    icon = g.icon.url if g.icon else None
    online = sum(1 for m in g.members if m.status != discord.Status.offline)
    embed = discord.Embed(title="📊 Server Info", color=discord.Color.blurple())
    embed.add_field(name="Name", value=g.name)
    embed.add_field(name="Owner", value=f"{owner} ({owner.id})" if owner else "?")
    embed.add_field(name="Server ID", value=str(g.id))
    embed.add_field(name="Members", value=str(g.member_count))
    embed.add_field(name="Online", value=str(online))
    embed.add_field(name="Boosts", value=f"{boosts} (Level {level})")
    embed.add_field(name="Roles", value=str(len(g.roles)))
    embed.add_field(name="Location", value=SERVER_LOCATION)
    embed.add_field(name="Bot Version", value=BOT_VERSION)
    if icon:
        embed.set_thumbnail(url=icon)
    await ctx.reply(embed=embed)

# -------------- MANAGE (Client API buttons) --------------
class ManageView(discord.ui.View):
    def __init__(self, server_identifier: str, client_key: str):
        super().__init__(timeout=180)
        self.sid = server_identifier
        self.ck = client_key

    async def _power(self, interaction: discord.Interaction, signal: str):
        r = client_post(self.ck, self.sid, "/power", {"signal": signal})
        if r.status_code in (204, 200):
            await interaction.response.send_message(f"✅ {signal.title()} sent.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {r.status_code}: {r.text[:200]}", ephemeral=True)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success)
    async def start(self, i: discord.Interaction, b: discord.ui.Button):
        await self._power(i, "start")

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def stop(self, i: discord.Interaction, b: discord.ui.Button):
        await self._power(i, "stop")

    @discord.ui.button(label="Restart", style=discord.ButtonStyle.primary)
    async def restart(self, i: discord.Interaction, b: discord.ui.Button):
        await self._power(i, "restart")

    @discord.ui.button(label="Kill", style=discord.ButtonStyle.secondary)
    async def kill(self, i: discord.Interaction, b: discord.ui.Button):
        await self._power(i, "kill")

    @discord.ui.button(label="Reinstall", style=discord.ButtonStyle.danger)
    async def reinstall(self, i: discord.Interaction, b: discord.ui.Button):
        r = client_post(self.ck, self.sid, "/settings/reinstall")
        if r.status_code in (204, 200):
            await i.response.send_message("🧩 Reinstall queued.", ephemeral=True)
        else:
            await i.response.send_message(f"❌ {r.status_code}: {r.text[:200]}", ephemeral=True)

    @discord.ui.button(label="IP & Allocation", style=discord.ButtonStyle.secondary)
    async def ipcheck(self, i: discord.Interaction, b: discord.ui.Button):
        r = client_get(self.ck, self.sid, "/network/allocations")
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                a = data[0]["attributes"]
                await i.response.send_message(f"🌐 {a.get('ip') if a.get('ip') else a.get('ip_alias')}:{a.get('port')}", ephemeral=True)
                return
        await i.response.send_message("❌ Could not fetch allocation.", ephemeral=True)

    @discord.ui.button(label="SFTP Details", style=discord.ButtonStyle.secondary)
    async def sftp(self, i: discord.Interaction, b: discord.ui.Button):
        r = client_get(self.ck, self.sid, "")
        if r.status_code == 200:
            at = r.json().get("attributes", {})
            host = at.get("sftp_details", {}).get("ip")
            port = at.get("sftp_details", {}).get("port")
            await i.response.send_message(f"🗂️ SFTP → `{host}:{port}`\nUsername: your_panel_user\nPassword: your_panel_password", ephemeral=True)
            return
        await i.response.send_message("❌ Could not fetch SFTP.", ephemeral=True)

    @discord.ui.button(label="Exit", style=discord.ButtonStyle.gray)
    async def exit(self, i: discord.Interaction, b: discord.ui.Button):
        await i.message.delete()

@bot.command(name="manage")
async def manage(ctx: commands.Context):
    # Ask for client API key once and store
    ckeys = load_json(CLIENT_KEYS_FILE)
    ck = ckeys.get(str(ctx.author.id))
    if not ck:
        await ctx.reply("🔑 Send your **Client API Key** (from Panel → API). This message will timeout in 90s.")
        def check(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            m = await bot.wait_for("message", timeout=90, check=check)
            ck = m.content.strip()
            ckeys[str(ctx.author.id)] = ck
            save_json(CLIENT_KEYS_FILE, ckeys)
        except Exception:
            await ctx.reply("Timed out."); return
    # Ask for server identifier
    await ctx.send("Enter your **Server Identifier** (short ID visible in panel URL).")
    def check2(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        m2 = await bot.wait_for("message", timeout=60, check=check2)
        sid = m2.content.strip()
    except Exception:
        await ctx.send("Timed out."); return

    # Fetch status
    rr = client_get(ck, sid, "")
    if rr.status_code != 200:
        await ctx.reply(f"❌ Invalid server or key ({rr.status_code}).")
        return
    name = rr.json().get("attributes", {}).get("name", sid)
    embed = discord.Embed(title=f"⚙️ Manage: {name}", description="Use the buttons below.", color=discord.Color.dark_gray())
    await ctx.reply(embed=embed, view=ManageView(sid, ck))

# -------------- MISC --------------
@bot.command(name="verify")
async def verify(ctx: commands.Context, tier: Optional[str] = None):
    inv = load_json(INVITES_FILE)
    n = int(inv.get(str(ctx.author.id), 0))
    cur = tier_for(n)
    if not tier:
        await ctx.reply(f"You have **{n}** invites → Tier **{cur['name']}**")
        return
    wanted = next((t for t in TIERS if t['name'].lower()==tier.lower()), None)
    if not wanted:
        await ctx.reply("Unknown tier name. Use *plans"); return
    if n >= wanted['at']:
        await ctx.reply(f"✅ Eligible for **{wanted['name']}**")
    else:
        await ctx.reply(f"❌ Need {wanted['at']-n} more invites for {wanted['name']}")

@bot.command(name="screenshot")
async def screenshot_cmd(ctx: commands.Context, *, url: str):
    embed = discord.Embed(title="📸 Screenshot", description=url, color=discord.Color.dark_gray())
    try: embed.set_image(url=url)
    except Exception: pass
    await ctx.reply(embed=embed)

# -------------- RUN --------------
bot.run(TOKEN)
