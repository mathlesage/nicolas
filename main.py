# main.py  (ou streamlit_app.py)
import os
import threading
import asyncio
import streamlit as st

import discord
from discord.ext import commands
from discord import app_commands

# ------------------------- Secrets -------------------------
TOKEN = st.secrets.get("DISCORD_TOKEN", os.getenv("DISCORD_TOKEN", ""))
TARGET_GUILD_ID = int(st.secrets.get("GUILD_ID", os.getenv("GUILD_ID", "0")) or 0)
TARGET_USER_ID = int(st.secrets.get("TARGET_USER_ID", os.getenv("TARGET_USER_ID", "0")) or 0)

st.set_page_config(page_title="Run it back · Admin justnexio", layout="centered")

st.title("Run it back · Admin rapide sur justnexio")
if not TOKEN:
    st.error("DISCORD_TOKEN manquant dans Streamlit Secrets.")
    st.stop()
if not TARGET_GUILD_ID or not TARGET_USER_ID:
    st.warning("GUILD_ID ou TARGET_USER_ID manquant dans Secrets. Les actions seront bloquées.")

# ------------------------- Intents -------------------------
# IMPORTANT : active 'Server Members Intent' dans le Developer Portal (Bot → Privileged Gateway Intents)
intents = discord.Intents.none()
intents.guilds = True
intents.members = True          # requis pour fetch/edit un membre
intents.voice_states = True     # requis pour move/disconnect/mute vocal

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ------------------------- État UI -------------------------
if "bot_thread" not in st.session_state:
    st.session_state.bot_thread = None
if "last_error" not in st.session_state:
    st.session_state.last_error = ""

# ---------------------- Slash minimal (ping) ----------------------
@tree.command(name="ping", description="Test de latence")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong", ephemeral=True)

# ---------------------- Ready & sync ----------------------
@bot.event
async def on_ready():
    try:
        if TARGET_GUILD_ID:
            await tree.sync(guild=discord.Object(id=TARGET_GUILD_ID))
        else:
            await tree.sync()
        print(f"[on_ready] Connecté en tant que {bot.user} — commandes synchronisées.")
    except Exception as e:
        print("[on_ready] Sync error:", e)

# ---------------------- Helpers asynchrones ----------------------
async def _get_targets():
    """Retourne (guild, member) ou lève une exception explicite."""
    if not bot.is_ready():
        raise RuntimeError("Le bot n'est pas connecté.")
    guild = bot.get_guild(TARGET_GUILD_ID)
    if guild is None:
        try:
            guild = await bot.fetch_guild(TARGET_GUILD_ID)
        except Exception as e:
            raise RuntimeError(f"Serveur introuvable : {e}")
    try:
        member = await guild.fetch_member(TARGET_USER_ID)
    except Exception as e:
        raise RuntimeError(f"justnexio introuvable sur ce serveur : {e}")
    return guild, member

async def do_ban():
    guild, member = await _get_targets()
    await guild.ban(member, reason="Action via bouton Streamlit")
    return f"✅ {member.display_name} banni."

async def do_mute():
    _, member = await _get_targets()
    await member.edit(mute=True, reason="Action via bouton Streamlit")
    return f"✅ {member.display_name} mute."

async def do_deafen():
    _, member = await _get_targets()
    await member.edit(deafen=True, reason="Action via bouton Streamlit")
    return f"✅ {member.display_name} rendu sourd."

async def do_disconnect():
    _, member = await _get_targets()
    await member.move_to(None)
    return f"✅ {member.display_name} déconnecté du vocal."

# ----------------- Exécuter sur la boucle du bot -----------------
def run_on_bot_loop_coro(make_coro, timeout: int = 20):
    """
    make_coro: fonction sans argument qui retourne une coroutine,
    créée uniquement si le bot est démarré & prêt.
    """
    thread = st.session_state.bot_thread
    if not (thread and thread.is_alive()):
        return False, "Le bot n'est pas démarré."
    if not bot.is_ready():
        return False, "Le bot n'est pas connecté."
    try:
        fut = asyncio.run_coroutine_threadsafe(make_coro(), bot.loop)
        res = fut.result(timeout)
        return True, res or "OK"
    except Exception as e:
        return False, str(e)

# ------------------------ Lancement bot ------------------------
def run_bot_forever():
    try:
        asyncio.run(bot.start(TOKEN))
    except discord.errors.PrivilegedIntentsRequired:
        # Intents non activés côté portail
        st.session_state.last_error = (
            "Active 'Server Members Intent' dans le Developer Portal (Bot → Privileged Gateway Intents) "
            "et vérifie que le token correspond bien à la même application."
        )
    except Exception as e:
        st.session_state.last_error = f"Erreur de lancement du bot : {e}"

running = st.session_state.bot_thread is not None and st.session_state.bot_thread.is_alive()
st.metric("Bot en cours d'exécution", "Oui" if running else "Non")

if st.button("Démarrer / Redémarrer le bot", use_container_width=True):
    if running:
        st.info("Le bot tourne déjà.")
    else:
        st.session_state.last_error = ""
        t = threading.Thread(target=run_bot_forever, daemon=True)
        t.start()
        st.session_state.bot_thread = t
        st.success("Bot démarré.")

if st.session_state.last_error:
    st.error(st.session_state.last_error)

st.divider()

# ------------------------ 4 gros boutons ------------------------
st.subheader("Actions rapides sur justnexio")
col1, col2 = st.columns(2)

with col1:
    if st.button("🚫 BAN justnexio", use_container_width=True):
        ok, msg = run_on_bot_loop_coro(lambda: do_ban())
        (st.success if ok else st.error)(msg)

    if st.button("🔇 MUTE justnexio", use_container_width=True):
        ok, msg = run_on_bot_loop_coro(lambda: do_mute())
        (st.success if ok else st.error)(msg)

with col2:
    if st.button("🔕 DEAFEN justnexio", use_container_width=True):
        ok, msg = run_on_bot_loop_coro(lambda: do_deafen())
        (st.success if ok else st.error)(msg)

    if st.button("🔌 DISCONNECT justnexio", use_container_width=True):
        ok, msg = run_on_bot_loop_coro(lambda: do_disconnect())
        (st.success if ok else st.error)(msg)

st.caption(
    "Rappels : 1) Active *Server Members Intent* dans le Developer Portal. "
    "2) Invite le bot sur **Run it back** avec les permissions Ban/Mute/Deafen/Move/Connect/View Channels/Use Application Commands. "
    "3) Place le rôle du bot **au-dessus** de celui de justnexio."
)
