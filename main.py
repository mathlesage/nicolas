

# =============================
# main.py (Streamlit + Discord bot)
# =============================
import threading
import asyncio
import os
import streamlit as st

import discord
from discord import app_commands
from discord.ext import commands

# ---------------- Config via Secrets ----------------
# Dans Streamlit Cloud: Settings -> Secrets
# DISCORD_TOKEN="..."  (token régénéré et NON public)
# GUILD_ID="1101494689649152010"  (Run it back)
# TARGET_USER_ID="313356139163156493"  (justnexio)
DISCORD_TOKEN = st.secrets.get("DISCORD_TOKEN", os.getenv("DISCORD_TOKEN", ""))
TARGET_GUILD_ID = int(st.secrets.get("GUILD_ID", "0"))
TARGET_USER_ID = int(st.secrets.get("TARGET_USER_ID", "0"))

if not DISCORD_TOKEN:
    st.error("DISCORD_TOKEN manquant. Ajoute-le dans Streamlit Secrets.")
    st.stop()
if not TARGET_GUILD_ID or not TARGET_USER_ID:
    st.warning("GUILD_ID ou TARGET_USER_ID manquant dans Secrets. Les commandes seront bloquées.")

# ---------------- Intents minimaux ----------------
# Active 'Server Members Intent' dans le Developer Portal (Bot -> Privileged Gateway Intents)
intents = discord.Intents.none()
intents.guilds = True
intents.members = True          # requis pour ban/mute/move
intents.voice_states = True     # requis pour move/disconnect/mute vocal

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------------- Utils gardes ----------------
async def ensure_right_guild(interaction: discord.Interaction) -> bool:
    if interaction.guild is None or interaction.guild.id != TARGET_GUILD_ID:
        await interaction.response.send_message(
            "❌ Cette commande n'est autorisée que sur le serveur Run it back.",
            ephemeral=True,
        )
        return False
    return True

async def ensure_target_user(interaction: discord.Interaction, member: discord.abc.User) -> bool:
    if member.id != TARGET_USER_ID:
        await interaction.response.send_message(
            "❌ Cette commande est restreinte à l'utilisateur justnexio.",
            ephemeral=True,
        )
        return False
    return True

# ---------------- Vue de confirmation BAN ----------------
class BanConfirmView(discord.ui.View):
    def __init__(self, requester_id: int, target_id: int, reason: str | None):
        super().__init__(timeout=60)
        self.requester_id = requester_id
        self.target_id = target_id
        self.reason = reason or "Aucune raison fournie"

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "❌ Tu n'es pas l'auteur de la demande.", ephemeral=True
            )
            return False
        if not await ensure_right_guild(interaction):
            return False
        return True

    @discord.ui.button(label="Confirmer le ban", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._guard(interaction):
            return
        guild = interaction.guild
        me = guild.me or await guild.fetch_member(bot.user.id)
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("❌ Permission manquante: Ban Members.", ephemeral=True)
        if not me.guild_permissions.ban_members:
            return await interaction.response.send_message("❌ Le bot n'a pas la permission Ban Members.", ephemeral=True)
        try:
            await guild.ban(discord.Object(id=self.target_id), reason=self.reason)
            for c in self.children: c.disabled = True
            await interaction.response.edit_message(
                content=f"✅ <@{self.target_id}> banni. Raison: {self.reason}", view=self
            )
        except Exception as e:
            for c in self.children: c.disabled = True
            await interaction.response.edit_message(
                content=f"❌ Impossible de bannir <@{self.target_id}> : {e}", view=self
            )

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not await self._guard(interaction):
            return
        for c in self.children: c.disabled = True
        await interaction.response.edit_message(content="Ban annulé.", view=self)

# ---------------- Commandes ----------------
@app_commands.default_permissions(ban_members=True)
@tree.command(name="ban", description="Bannir justnexio avec confirmation")
@app_commands.describe(reason="Raison (optionnelle)")
async def ban_cmd(interaction: discord.Interaction, reason: str | None = None):
    if not await ensure_right_guild(interaction):
        return
    # Forcer la cible = justnexio
    try:
        member = await interaction.guild.fetch_member(TARGET_USER_ID)
    except Exception:
        return await interaction.response.send_message("❌ justnexio introuvable sur ce serveur.", ephemeral=True)
    # Confirmation
    view = BanConfirmView(requester_id=interaction.user.id, target_id=member.id, reason=reason)
    await interaction.response.send_message(
        content=f"Tu veux vraiment bannir {member.mention} ?",
        view=view,
        ephemeral=True,
    )

@app_commands.default_permissions(mute_members=True)
@tree.command(name="mute", description="Mute justnexio dans le salon vocal")
@app_commands.describe(reason="Raison (optionnelle)")
async def mute_cmd(interaction: discord.Interaction, reason: str | None = None):
    if not await ensure_right_guild(interaction):
        return
    try:
        member = await interaction.guild.fetch_member(TARGET_USER_ID)
    except Exception:
        return await interaction.response.send_message("❌ justnexio introuvable.", ephemeral=True)
    try:
        await member.edit(mute=True, reason=reason or "Mute via /mute")
        await interaction.response.send_message(f"✅ {member.mention} a été mute.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Impossible de mute {member.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(mute_members=True)
@tree.command(name="unmute", description="Unmute justnexio")
@app_commands.describe(reason="Raison (optionnelle)")
async def unmute_cmd(interaction: discord.Interaction, reason: str | None = None):
    if not await ensure_right_guild(interaction):
        return
    try:
        member = await interaction.guild.fetch_member(TARGET_USER_ID)
    except Exception:
        return await interaction.response.send_message("❌ justnexio introuvable.", ephemeral=True)
    try:
        await member.edit(mute=False, reason=reason or "Unmute via /unmute")
        await interaction.response.send_message(f"✅ {member.mention} a été unmute.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Impossible d'unmute {member.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(deafen_members=True)
@tree.command(name="deafen", description="Rendre sourd justnexio (server deafen)")
@app_commands.describe(reason="Raison (optionnelle)")
async def deafen_cmd(interaction: discord.Interaction, reason: str | None = None):
    if not await ensure_right_guild(interaction):
        return
    try:
        member = await interaction.guild.fetch_member(TARGET_USER_ID)
    except Exception:
        return await interaction.response.send_message("❌ justnexio introuvable.", ephemeral=True)
    try:
        await member.edit(deafen=True, reason=reason or "Deafen via /deafen")
        await interaction.response.send_message(f"✅ {member.mention} est maintenant sourd.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Impossible de rendre sourd {member.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(deafen_members=True)
@tree.command(name="undeafen", description="Enlever le server deafen de justnexio")
@app_commands.describe(reason="Raison (optionnelle)")
async def undeafen_cmd(interaction: discord.Interaction, reason: str | None = None):
    if not await ensure_right_guild(interaction):
        return
    try:
        member = await interaction.guild.fetch_member(TARGET_USER_ID)
    except Exception:
        return await interaction.response.send_message("❌ justnexio introuvable.", ephemeral=True)
    try:
        await member.edit(deafen=False, reason=reason or "Undeafen via /undeafen")
        await interaction.response.send_message(f"✅ {member.mention} n'est plus sourd.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Impossible d'undeafen {member.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(move_members=True)
@tree.command(name="move", description="Déplacer justnexio vers un salon vocal")
@app_commands.describe(channel="Salon vocal cible")
async def move_cmd(interaction: discord.Interaction, channel: discord.VoiceChannel):
    if not await ensure_right_guild(interaction):
        return
    try:
        member = await interaction.guild.fetch_member(TARGET_USER_ID)
    except Exception:
        return await interaction.response.send_message("❌ justnexio introuvable.", ephemeral=True)
    try:
        await member.move_to(channel)
        await interaction.response.send_message(f"✅ {member.mention} déplacé vers {channel.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Impossible de déplacer {member.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(move_members=True)
@tree.command(name="disconnect", description="Déconnecter justnexio du vocal")
async def disconnect_cmd(interaction: discord.Interaction):
    if not await ensure_right_guild(interaction):
        return
    try:
        member = await interaction.guild.fetch_member(TARGET_USER_ID)
    except Exception:
        return await interaction.response.send_message("❌ justnexio introuvable.", ephemeral=True)
    try:
        await member.move_to(None)
        await interaction.response.send_message(f"✅ {member.mention} a été déconnecté du vocal.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Impossible de déconnecter {member.mention} : {e}", ephemeral=True)

# ---------------- Ready & Sync ----------------
@bot.event
async def on_ready():
    try:
        if TARGET_GUILD_ID:
            await tree.sync(guild=discord.Object(id=TARGET_GUILD_ID))
        else:
            await tree.sync()
        print(f"Connecté en tant que {bot.user} — commandes synchronisées.")
    except Exception as e:
        print("Erreur de sync des commandes:", e)

# ---------------- Lancement bot dans un thread ----------------

def run_bot_forever():
    asyncio.run(bot.start(DISCORD_TOKEN))

if "bot_thread" not in st.session_state:
    st.session_state.bot_thread = None

st.title("Dashboard Bot — Run it back · justnexio")
st.write("Statut du bot lancé depuis Streamlit Cloud.")

running = st.session_state.bot_thread is not None and st.session_state.bot_thread.is_alive()
st.metric("Bot en cours d'exécution", "Oui" if running else "Non")

if st.button("Démarrer / Redémarrer le bot", use_container_width=True):
    if running:
        st.info("Le bot tourne déjà.")
    else:
        t = threading.Thread(target=run_bot_forever, daemon=True)
        t.start()
        st.session_state.bot_thread = t
        st.success("Bot démarré.")

# ================= Quick Actions (4 gros boutons) =================
# Helpers pour exécuter une coroutine sur la boucle du bot

def run_on_bot_loop(coro, timeout=20):
    if not (st.session_state.bot_thread and st.session_state.bot_thread.is_alive()):
        return False, "Le bot n'est pas démarré."
    try:
        fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        res = fut.result(timeout=timeout)
        return True, res or "OK"
    except Exception as e:
        return False, str(e)

async def _get_targets():
    guild = bot.get_guild(TARGET_GUILD_ID)
    if guild is None:
        try:
            guild = await bot.fetch_guild(TARGET_GUILD_ID)
        except Exception as e:
            raise RuntimeError(f"Serveur introuvable: {e}")
    try:
        member = await guild.fetch_member(TARGET_USER_ID)
    except Exception as e:
        raise RuntimeError(f"justnexio introuvable sur le serveur: {e}")
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

st.subheader("Actions rapides sur justnexio")
col1, col2 = st.columns(2)
with col1:
    if st.button("🚫 BAN justnexio", use_container_width=True):
        ok, msg = run_on_bot_loop(do_ban())
        (st.success if ok else st.error)(msg)
    if st.button("🔇 MUTE justnexio", use_container_width=True):
        ok, msg = run_on_bot_loop(do_mute())
        (st.success if ok else st.error)(msg)
with col2:
    if st.button("🔕 DEAFEN justnexio", use_container_width=True):
        ok, msg = run_on_bot_loop(do_deafen())
        (st.success if ok else st.error)(msg)
    if st.button("🔌 DISCONNECT justnexio", use_container_width=True):
        ok, msg = run_on_bot_loop(do_disconnect())
        (st.success if ok else st.error)(msg)

st.markdown(
    """
    **Commandes actives (slash) également disponibles**
    - /ban · /mute · /unmute · /deafen · /undeafen · /move · /disconnect

    **Permissions à cocher pour le bot**
    - Ban Members · Mute Members · Deafen Members · Move Members
    - Send Messages · Use Application Commands · View Channels · Connect

    **Note** : Active *Server Members Intent* dans le Developer Portal.
    """
)
