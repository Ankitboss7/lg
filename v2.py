import os
import json
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import discord
from discord.ext import commands
import requests

# -------------- CONFIG --------------
PREFIX = "*"
TOKEN = ""
# Embed images (optional)
PLANS_IMAGE_URL ="https://postimg.cc/cvPJQwrw"
LOGO_URL ="https://postimg.cc/R6zZ1kL1"

# Pterodactyl panel
PANEL_URL = "http://103.194.228.138/"
PANEL_API_KEY = "ptla_dKi5JYB14l8lq9dnfsixO7GHjkIo2wvUcv2iah6IXcL"
# Defaults for new servers
DEFAULT_NODE = "1"
DEFAULT_ALLOCATION_ID = "1"

# Map numeric menu to (nest_id, egg_id, docker_image, startup)
# NOTE: Replace egg IDs/startups with your panel's actual values.
EGG_CATALOG = {
    1: {"name": "Bungeecord", "nest": 1, "egg": 1, "docker_image": "ghcr.io/pterodactyl/yolks:java_17", "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    2: {"name": "Forge Minecraft", "nest": 1, "egg": 2, "docker_image": "ghcr.io/pterodactyl/yolks:java_17", "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    3: {"name": "Sponge (SpongeVanilla)", "nest": 1, "egg": 3, "docker_image": "ghcr.io/pterodactyl/yolks:java_17", "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    4: {"name": "Paper", "nest": 1, "egg": 4, "docker_image": "ghcr.io/pterodactyl/yolks:java_17", "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    5: {"name": "Vanilla Minecraft", "nest": 1, "egg": 5, "docker_image": "ghcr.io/pterodactyl/yolks:java_17", "startup": "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"},
    6: {"name": "Server Importer", "nest": 1, "egg": 6, "docker_image": "ghcr.io/pterodactyl/yolks:java_17", "startup": "bash"},
    7: {"name": "Team Fortress 2", "nest": 4, "egg": 7, "docker_image": "ghcr.io/pterodactyl/yolks:source", "startup": "./srcds_run"},
    8: {"name": "CS:GO", "nest": 4, "egg": 8, "docker_image": "ghcr.io/pterodactyl/yolks:source", "startup": "./srcds_run"},
    9: {"name": "Insurgency", "nest": 4, "egg": 9, "docker_image": "ghcr.io/pterodactyl/yolks:source", "startup": "./srcds_run"},
    10: {"name": "Garrys Mod", "nest": 4, "egg": 10, "docker_image": "ghcr.io/pterodactyl/yolks:source", "startup": "./srcds_run"},
    11: {"name": "Ark: Survival Evolved", "nest": 7, "egg": 11, "docker_image": "ghcr.io/pterodactyl/yolks:linux", "startup": "./ShooterGameServer"},
    12: {"name": "Custom Source Engine", "nest": 4, "egg": 12, "docker_image": "ghcr.io/pterodactyl/yolks:source", "startup": "./srcds_run"},
    13: {"name": "Mumble Server", "nest": 5, "egg": 13, "docker_image": "ghcr.io/pterodactyl/yolks:debian", "startup": "murmurd -ini murmur.ini"},
    14: {"name": "Teamspeak3 Server", "nest": 5, "egg": 14, "docker_image": "ghcr.io/pterodactyl/yolks:debian", "startup": "./ts3server"},
    15: {"name": "Rust", "nest": 4, "egg": 15, "docker_image": "ghcr.io/pterodactyl/yolks:rust", "startup": "./RustDedicated"},
    16: {"name": "Python Generic", "nest": 5, "egg": 16, "docker_image": "ghcr.io/pterodactyl/yolks:python_3.11", "startup": "python main.py"},
    17: {"name": "Node.js", "nest": 5, "egg": 17, "docker_image": "ghcr.io/pterodactyl/yolks:nodejs_18", "startup": "node index.js"},
}

# -------------- FILE HELPERS --------------
DATA_DIR = "."
ADMINS_FILE = os.path.join(DATA_DIR, "admins.txt")
INVITES_FILE = os.path.join(DATA_DIR, "invites.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

os.makedirs(DATA_DIR, exist_ok=True)
for path, default in [
    (ADMINS_FILE, ""),
    (INVITES_FILE, "{}"),
    (USERS_FILE, "{}"),
]:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(default)

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
    with open(ADMINS_FILE, "r", encoding="utf-8") as f:
        ids = [line.strip() for line in f if line.strip()]
    return set(ids)


def save_admins(admin_ids: set):
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        for _id in admin_ids:
            f.write(str(_id) + "\n")

# -------------- PLAN LOGIC --------------
@dataclass
class Tier:
    name: str
    min_invites: int
    ram_mb: int
    cpu_pct: int
    disk_mb: int

TIERS = [
    Tier("Basic", 0, 4096, 150, 10000),
    Tier("Advanced", 4, 6144, 200, 15000),
    Tier("Pro", 6, 7168, 230, 20000),
    Tier("Premium", 8, 9216, 270, 25000),
    Tier("Elite", 15, 12288, 320, 30000),
    Tier("Ultimate", 20, 16384, 400, 35000),
]


def tier_for_invites(n: int) -> Tier:
    cur = TIERS[0]
    for t in TIERS:
        if n >= t.min_invites:
            cur = t
    return cur


def next_tier_info(n: int) -> Optional[Tuple[Tier, int]]:
    for t in TIERS:
        if n < t.min_invites:
            return t, t.min_invites - n
    return None

# -------------- PTERODACTYL HELPERS --------------
HEADERS = {
    "Authorization": f"Bearer {PANEL_API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def panel_post(path: str, payload: dict) -> requests.Response:
    url = f"{PANEL_URL}/api/application{path}"
    return requests.post(url, headers=HEADERS, json=payload, timeout=30)


def panel_get(path: str, params: dict = None) -> requests.Response:
    url = f"{PANEL_URL}/api/application{path}"
    return requests.get(url, headers=HEADERS, params=params or {}, timeout=30)


def panel_delete(path: str) -> requests.Response:
    url = f"{PANEL_URL}/api/application{path}"
    return requests.delete(url, headers=HEADERS, timeout=30)


def create_panel_user(username: str, email: str, password: str) -> Optional[int]:
    payload = {
        "username": username,
        "email": email,
        "first_name": username,
        "last_name": "User",
        "password": password,
    }
    r = panel_post("/users", payload)
    if r.status_code in (200, 201):
        return r.json()["attributes"]["id"]
    # If already exists, try fetch
    if r.status_code == 422 and "email" in r.text:
        rr = panel_get("/users", params={"filter[email]": email})
        if rr.status_code == 200 and rr.json().get("data"):
            return rr.json()["data"][0]["attributes"]["id"]
    return None


def create_panel_server(name: str, owner_id: int, egg: dict, ram_mb: int, cpu_pct: int, disk_mb: int) -> Tuple[bool, str]:
    env = {
        "SERVER_JARFILE": "server.jar",
        "MINECRAFT_VERSION": "latest",
        "EULA": "true",
    }
    payload = {
        "name": name,
        "user": owner_id,
        "egg": egg["egg"],
        "docker_image": egg["docker_image"],
        "startup": egg["startup"],
        "limits": {
            "memory": ram_mb,
            "swap": 0,
            "disk": disk_mb,
            "io": 500,
            "cpu": cpu_pct,
        },
        "environment": env,
        "feature_limits": {"databases": 2, "backups": 2, "allocations": 1},
        "allocation": {"default": DEFAULT_ALLOCATION_ID},
        "deploy": {"locations": [], "dedicated_ip": False, "port_range": []},
    }
    r = panel_post("/servers", payload)
    if r.status_code in (200, 201, 202):
        data = r.json().get("attributes", {})
        sid = str(data.get("id")) or "?"
        return True, f"Server created: {name} (ID: {sid})"
    return False, f"Panel error {r.status_code}: {r.text[:300]}"


def delete_panel_server_by_name(name_sub: str) -> Tuple[bool, str]:
    rr = panel_get("/servers")
    if rr.status_code != 200:
        return False, f"List error {rr.status_code}: {rr.text[:200]}"
    for item in rr.json().get("data", []):
        attrs = item.get("attributes", {})
        if name_sub.lower() in attrs.get("name", "").lower():
            sid = attrs.get("id")
            dr = panel_delete(f"/servers/{sid}")
            if dr.status_code in (204, 200):
                return True, f"Deleted server '{attrs.get('name')}' (ID {sid})"
            return False, f"Delete error {dr.status_code}: {dr.text[:200]}"
    return False, "No matching server found."

# -------------- DISCORD BOT --------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Utility checks

def is_admin(user_id: int) -> bool:
    admins = load_admins()
    return str(user_id) in admins


async def require_admin(ctx):
    if not is_admin(ctx.author.id):
        await ctx.reply("You are not an admin for this bot.")
        return False
    return True


def pretty_tiers() -> str:
    lines = []
    for t in TIERS:
        lines.append(f"**{t.name}** — at {t.min_invites} invites\nRAM: {t.ram_mb//1024} GB\nCPU: {t.cpu_pct}%\nDisk: {t.disk_mb//1000} GB\n")
    return "\n".join(lines)


# -------------- COMMANDS --------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (prefix {PREFIX})")


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(title="Cute Cloud Bot Help", color=discord.Color.blurple())
    embed.description = (
        "**Account**\n"
        f"`{PREFIX}register <email> <password>` — Link your panel account to your Discord\n"
        "\n**Server**\n"
        f"`{PREFIX}create` — Create a new server (interactive)\n"
        f"`{PREFIX}upgrade` — Show your current tier limits\n"
        "\n**Invites**\n"
        f"`{PREFIX}i [@user]` — Check invites & tier\n"
        f"`{PREFIX}plans` — View invite reward tiers\n"
        f"`{PREFIX}verify [TierName]` — Quick verification for a tier\n"
        f"`{PREFIX}screenshot <image_url>` — Show a screenshot embed\n"
        "\n**Admin**\n"
        f"`{PREFIX}admin add_i @user <amount>` — Add invites\n"
        f"`{PREFIX}admin add_a @user` / `{PREFIX}admin rm_a @user` — add/remove admin\n"
        f"`{PREFIX}admin create_a @user <email> <password>` — Create panel user and link\n"
        f"`{PREFIX}admin create_s <name> <owner_email>` — Create server (interactive egg + limits)\n"
        f"`{PREFIX}admin delete_s <name>` — Delete server by name contains\n"
    )
    if LOGO_URL:
        embed.set_thumbnail(url=LOGO_URL)
    await ctx.reply(embed=embed)


@bot.command(name="plans")
async def plans_cmd(ctx: commands.Context):
    embed = discord.Embed(title="✨ Invite Plans", color=discord.Color.gold())
    embed.description = pretty_tiers()
    if PLANS_IMAGE_URL:
        embed.set_image(url=PLANS_IMAGE_URL)
    await ctx.reply(embed=embed)


@bot.command(name="i")
async def invites_check(ctx: commands.Context, user: Optional[discord.Member] = None):
    target = user or ctx.author
    invites = load_json(INVITES_FILE)
    n = int(invites.get(str(target.id), 0))
    tier = tier_for_invites(n)
    nxt = next_tier_info(n)

    embed = discord.Embed(title=f"💎 Invite Stats – {target.display_name}", color=discord.Color.blue())
    embed.add_field(name="Total Invites", value=str(n))
    embed.add_field(name="Current Tier", value=tier.name)
    if nxt:
        embed.add_field(name="Next Tier", value=f"{nxt[0].name} at {nxt[0].min_invites} invites (need {nxt[1]})", inline=False)
    embed.add_field(name="Current Tier Benefits", value=f"RAM: {tier.ram_mb}MB\nCPU: {tier.cpu_pct}%\nDisk: {tier.disk_mb}MB", inline=False)
    await ctx.reply(embed=embed)


@bot.group(name="admin", invoke_without_command=True)
async def admin_group(ctx: commands.Context):
    await help_cmd(ctx)


@admin_group.command(name="add_i")
async def admin_add_invites(ctx: commands.Context, user: discord.Member, amount: int):
    if not await require_admin(ctx):
        return
    invites = load_json(INVITES_FILE)
    old = int(invites.get(str(user.id), 0))
    invites[str(user.id)] = old + max(0, amount)
    save_json(INVITES_FILE, invites)
    await ctx.reply(f"✅ Added {amount} invites to {user.mention}. New total: **{invites[str(user.id)]}**")


@admin_group.command(name="add_a")
async def admin_add_admin(ctx: commands.Context, user: discord.Member):
    if not await require_admin(ctx):
        return
    admins = load_admins()
    admins.add(str(user.id))
    save_admins(admins)
    await ctx.reply(f"✅ {user.mention} is now a bot admin.")


@admin_group.command(name="rm_a")
async def admin_remove_admin(ctx: commands.Context, user: discord.Member):
    if not await require_admin(ctx):
        return
    admins = load_admins()
    if str(user.id) in admins:
        admins.remove(str(user.id))
        save_admins(admins)
        await ctx.reply(f"✅ Removed admin: {user.mention}")
    else:
        await ctx.reply("That user is not an admin.")


@bot.command(name="register")
async def register_cmd(ctx: commands.Context, email: str, password: str):
    users = load_json(USERS_FILE)
    if str(ctx.author.id) in users:
        await ctx.reply("You are already registered.")
        return
    panel_id = create_panel_user(ctx.author.name, email, password)
    if panel_id is None:
        await ctx.reply("❌ Failed to create/find user on panel. Check API key & URL in config.")
        return
    users[str(ctx.author.id)] = {"email": email, "password": password, "panel_id": panel_id}
    save_json(USERS_FILE, users)
    await ctx.reply(f"✅ Registered with panel user ID **{panel_id}**")


@admin_group.command(name="create_a")
async def admin_create_account(ctx: commands.Context, user: discord.Member, email: str, password: str):
    if not await require_admin(ctx):
        return
    users = load_json(USERS_FILE)
    panel_id = create_panel_user(user.name, email, password)
    if panel_id is None:
        await ctx.reply("❌ Panel user create failed. Check API + email uniqueness.")
        return
    users[str(user.id)] = {"email": email, "password": password, "panel_id": panel_id}
    save_json(USERS_FILE, users)
    try:
        await user.send(f"✅ Your panel account is ready!\nEmail: **{email}**\nPassword: **{password}**\nPanel: {PANEL_URL}")
    except Exception:
        pass
    await ctx.reply(f"✅ Linked panel user ID **{panel_id}** to {user.mention}")


async def prompt_number(ctx: commands.Context, prompt: str, valid: range, timeout: int = 60) -> Optional[int]:
    if prompt:
        await ctx.send(prompt)
    def check(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        m = await bot.wait_for("message", timeout=timeout, check=check)
        val = int(m.content.strip())
        if val in valid:
            return val
    except Exception:
        pass
    await ctx.send("Timed out or invalid input.")
    return None


@bot.command(name="create")
async def create_cmd(ctx: commands.Context):
    users = load_json(USERS_FILE)
    ud = users.get(str(ctx.author.id))
    if not ud:
        await ctx.reply(f"Register first: `{PREFIX}register <email> <password>` or ask admin to run `{PREFIX}admin create_a`.")
        return

    # Choose egg
    menu = [f"{i}. {EGG_CATALOG[i]['name']}" for i in sorted(EGG_CATALOG.keys())]
    msg = "**Select server type:**\n" + "\n".join(menu) + f"\n\nReply with number (1-{len(menu)})"
    choice = await prompt_number(ctx, msg, valid=range(1, len(menu) + 1))
    if not choice:
        return
    egg = EGG_CATALOG[choice]

    # Ask limits based on current tier
    invites = load_json(INVITES_FILE)
    my_inv = int(invites.get(str(ctx.author.id), 0))
    t = tier_for_invites(my_inv)

    await ctx.send(f"Enter **RAM MB** (max {t.ram_mb}):")
    ram = await prompt_number(ctx, "", valid=range(128, t.ram_mb + 1))
    if not ram:
        return
    await ctx.send(f"Enter **CPU %** (max {t.cpu_pct}):")
    cpu = await prompt_number(ctx, "", valid=range(10, t.cpu_pct + 1))
    if not cpu:
        return
    await ctx.send(f"Enter **Disk MB** (max {t.disk_mb}):")
    disk = await prompt_number(ctx, "", valid=range(1000, t.disk_mb + 1))
    if not disk:
        return

    name = f"{time.strftime('%Y%m%d')}-{ctx.author.name.lower()}"
    ok, text = create_panel_server(name, ud["panel_id"], egg, ram, cpu, disk)
    if ok:
        embed = discord.Embed(title="✅ Server created!", color=discord.Color.green())
        embed.add_field(name="Name", value=name)
        embed.add_field(name="Type", value=egg["name"])
        embed.add_field(name="RAM", value=f"{ram}MB")
        embed.add_field(name="CPU", value=f"{cpu}%")
        embed.add_field(name="Disk", value=f"{disk}MB")
        await ctx.reply(embed=embed)
    else:
        await ctx.reply("❌ " + text)


@admin_group.command(name="create_s")
async def admin_create_server(ctx: commands.Context, name: str, owner_email: str):
    if not await require_admin(ctx):
        return
    # find owner by email
    users = load_json(USERS_FILE)
    owner_panel_id = None
    for k, v in users.items():
        if v.get("email") == owner_email:
            owner_panel_id = v.get("panel_id")
            break
    if not owner_panel_id:
        await ctx.reply("Owner email not linked in users.json. Use *admin create_a first.")
        return

    menu = [f"{i}. {EGG_CATALOG[i]['name']}" for i in sorted(EGG_CATALOG.keys())]
    msg = "**Select server type:**\n" + "\n".join(menu) + f"\n\nReply with number (1-{len(menu)})"
    choice = await prompt_number(ctx, msg, valid=range(1, len(menu) + 1))
    if not choice:
        return
    egg = EGG_CATALOG[choice]

    await ctx.send("Enter RAM MB (e.g. 4096):")
    ram = await prompt_number(ctx, "", valid=range(128, 262144))
    if not ram:
        return
    await ctx.send("Enter CPU % (e.g. 200):")
    cpu = await prompt_number(ctx, "", valid=range(10, 1001))
    if not cpu:
        return
    await ctx.send("Enter Disk MB (e.g. 15000):")
    disk = await prompt_number(ctx, "", valid=range(1000, 2097152))
    if not disk:
        return

    ok, text = create_panel_server(name, owner_panel_id, egg, ram, cpu, disk)
    await ctx.reply(text)


@admin_group.command(name="delete_s")
async def admin_delete_server(ctx: commands.Context, *, name_contains: str):
    if not await require_admin(ctx):
        return
    ok, text = delete_panel_server_by_name(name_contains)
    await ctx.reply(text)


@bot.command(name="upgrade")
async def upgrade_cmd(ctx: commands.Context):
    invites = load_json(INVITES_FILE)
    n = int(invites.get(str(ctx.author.id), 0))
    t = tier_for_invites(n)
    await ctx.reply(f"Your current tier is **{t.name}** — max RAM {t.ram_mb}MB, CPU {t.cpu_pct}%, Disk {t.disk_mb}MB. Ask an admin to apply on your server.")


# ---- Extras ----
@bot.command(name="verify")
async def verify_cmd(ctx: commands.Context, tier_name: str = None):
    """Quick invite verification for a target tier name (e.g., *verify Premium)."""
    invites = load_json(INVITES_FILE)
    n = int(invites.get(str(ctx.author.id), 0))
    cur = tier_for_invites(n)
    if not tier_name:
        await ctx.reply(f"You have **{n}** invites → Current Tier: **{cur.name}**")
        return
    wanted = None
    for t in TIERS:
        if t.name.lower() == tier_name.lower():
            wanted = t
            break
    if not wanted:
        await ctx.reply("Unknown tier. Use *plans to see valid names.")
        return
    if n >= wanted.min_invites:
        await ctx.reply(f"✅ Verified: You meet **{wanted.name}** (invites: {n} ≥ {wanted.min_invites}).")
    else:
        await ctx.reply(f"❌ Not enough invites for **{wanted.name}**. You have {n}, need {wanted.min_invites}.")


@bot.command(name="screenshot")
async def screenshot_cmd(ctx: commands.Context, *, image_url: str):
    """Embed a screenshot/image URL (helper per your screenshots flow)."""
    embed = discord.Embed(title="📸 Screenshot", color=discord.Color.dark_gray())
    embed.description = image_url
    try:
        embed.set_image(url=image_url)
    except Exception:
        pass
    await ctx.reply(embed=embed)

 bot.run(TOKEN)
