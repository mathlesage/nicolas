# main.py (ou streamlit_app.py)
import os
import threading
import asyncio
import time
import streamlit as st

import discord
from discord.ext import commands
from discord import app_commands

# ==================== Config / Secrets ====================
TOKEN = st.secrets.get("DISCORD_TOKEN", os.getenv("DISCORD_TOKEN", ""))
TARGET_GUILD_ID = int(st.secrets.get("GUILD_ID", os.getenv("GUILD_ID", "0")) or 0)
TARGET_USER_ID = int(st.secrets.get("TARGET_USER_ID", os.getenv("TARGET_USER_ID", "0")) or 0)

st.set_page_config(page_title="Run it back · Admin justnexio", layout="centered")
st.title("Run it back · Tableau de bord justnexio")

if not TOKEN:
    st.error("DISCORD_TOKEN manquant dans Streamlit Secrets.")
    st.stop()
if not TARGET_GUILD_ID or not TARGET_USER_ID:
    st.warning("GUILD_ID ou TARGET_USER_ID manquant dans Secrets. Les actions seront bloquées.")

# ==================== État global thread-safe (pas de Streamlit dans le thread) ====================
STATE = {
    "connected": False,        # mis à True sur on_ready
    "bot_user": "",            # nom#discrim du bot
    "last_error": "",          # dernier message d'erreur lisible
}
STATE_LOCK = threading.Lock()

def set_state(**kwargs):
    with STATE_LOCK:
        STATE.update(kwargs)

def get_state():
    with STATE_LOCK:
        return dict(STATE)

# ==================== Options ====================
with st.sidebar:
    st.header("Options")
    test_without_members_intent = st.checkbox(
        "Mode test: démarrer sans Members Intent",
        value=False,
        help="Utilise-le pour vérifier la connexion si tu n'as pas encore activé Server Members Intent."
    )
    autorefresh = st.checkbox(
        "Rafraîchir l’état toutes les 2 s",
        value=True,
        help="Actualise l'UI pour refléter rapidement le statut on_ready."
    )

# ==================== Bot factory ====================
def make_bot(with_members: bool) -> commands.Bot:
    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    intents.members = bool(with_members)  # True = nécessite Server Members Intent activé côté portail

    bot = commands.Bot(command_prefix="!", intents=intents)
    tree = bot.tree

    @tree.command(name="ping", description="Test de latence")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("pong", ephemeral=True)

    @bot.event
    async def on_ready():
        set_state(connected=True, bot_user=str(bot.user))
        try:
            if TARGET_GUILD_ID:
                await tree.sync(guild=discord.Object(id=TARGET_GUILD_ID))
            else:
                await tree.sync()
            print(f"[on_ready] Connecté en tant que {bot.user} — commandes synchronisées.")
        except Exception as e:
            print("[on_ready] Sync error:", e)

    @bot.event
    async def on_disconnect():
        set_state(connected=False)

    @bot.event
    async def on_resumed():
        set_state(connected=True)

    return bot

# ==================== Singleton bot par mode d’intents ====================
if "intent_mode" not in st.session_state:
    st.session_state.intent_mode = None
if "bot_instance" not in st.session_state:
    st.session_state.bot_instance = None
if "bot_thread" not in st.session_state:
    st.session_state.bot_thread = None

desired_mode = "no_members" if test_without_members_intent else "with_members"
if st.session_state.intent_mode != desired_mode or st.session_state.bot_instance is None:
    st.session_state.intent_mode = desired_mode
    st.session_state.bot_instance = make_bot(with_members=(desired_mode == "with_members"))
    # reset état connexion (sera fixé par on_ready)
    set_state(connected=False, bot_user="")

bot: commands.Bot = st.session_state.bot_instance

# ==================== Actions asynchrones ====================
async def _get_targets():
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
    return f"{member.display_name} banni."

async def do_mute():
    _, member = await _get_targets()
    await member.edit(mute=True, reason="Action via bouton Streamlit")
    return f"{member.display_name} mute."

async def do_deafen():
    _, member = await _get_targets()
    await member.edit(deafen=True, reason="Action via bouton Streamlit")
    return f"{member.display_name} rendu sourd."

async def do_disconnect():
    _, member = await _get_targets()
    await member.move_to(None)
    return f"{member.display_name} déconnecté du vocal."

# ==================== Exécuter sur la boucle du bot ====================
def run_on_bot_loop_coro(make_coro, timeout: int = 20):
    thread = st.session_state.bot_thread
    if not (thread and thread.is_alive()):
        return False, "Le bot n'est pas démarré (thread)."

    s = get_state()
    if not s["connected"] or not bot.is_ready():
        return False, "Le bot n'est pas connecté (gateway). Vérifie l’intent Members et le token."

    try:
        fut = asyncio.run_coroutine_threadsafe(make_coro(), bot.loop)
        res = fut.result(timeout)
        return True, res or "OK"
    except discord.errors.Forbidden as e:
        return False, f"Permission refusée : {e}"
    except discord.errors.HTTPException as e:
        return False, f"Erreur HTTP Discord : {e}"
    except Exception as e:
        return False, str(e)

# ==================== Lancement du bot en thread ====================
def run_bot_forever():
    try:
        asyncio.run(bot.start(TOKEN))
    except discord.errors.PrivilegedIntentsRequired:
        set_state(
            connected=False,
            bot_user="",
            last_error=(
                "Intents requis non activés : coche **Server Members Intent** "
                "dans Developer Portal → Bot → Privileged Gateway Intents, puis Save. "
                "Assure-toi aussi que le TOKEN vient de la même application."
            ),
        )
    except Exception as e:
        set_state(connected=False, bot_user="", last_error=f"Erreur de lancement du bot : {e}")

thread_alive = st.session_state.bot_thread is not None and st.session_state.bot_thread.is_alive()
if st.button("Démarrer / Redémarrer le bot", use_container_width=True):
    if thread_alive:
        st.info("Le bot tourne déjà.")
    else:
        # clear erreurs précédentes
        set_state(last_error="")
        t = threading.Thread(target=run_bot_forever, daemon=True, name="run_bot_forever")
        t.start()
        st.session_state.bot_thread = t
        st.success("Démarrage demandé. Attends l’état Connecté = Oui.")

# ==================== Statut & auto-refresh ====================
s = get_state()
colA, colB, colC = st.columns(3)
with colA:
    st.metric("Thread bot", "Oui" if thread_alive else "Non")
with colB:
    st.metric("Connecté à Discord", "Oui" if s["connected"] else "Non")
with colC:
    st.metric("Mode intents", "Sans members" if desired_mode == "no_members" else "Avec members")

if s["bot_user"]:
    st.write(f"Compte bot : **{s['bot_user']}**")
if s.get("last_error"):
    st.error(s["last_error"])

if autorefresh:
    st.experimental_set_query_params(_=str(time.time()))  # force un refresh léger
    st.experimental_rerun()  # relance le script pour récupérer l'état mis à jour

st.divider()

# ==================== 4 gros boutons ====================
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
    "1) Active **Server Members Intent** dans le Developer Portal. "
    "2) Invite le bot sur **Run it back** avec Ban/Mute/Deafen/Move/Connect/View Channels/Use Application Commands. "
    "3) Place le rôle du bot **au-dessus** de celui de justnexio."
)
