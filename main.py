

# =============================
# streamlit_app.py
# =============================
import threading
import asyncio
import os
import streamlit as st

import discord
from discord import app_commands
from discord.ext import commands

# -------------------------------------------------------------
# Secrets Streamlit à définir dans Settings -> Secrets
# DISCORD_TOKEN = "..."
# CLIENT_ID = "..."
# GUILD_ID = "..."  # optionnel, pour sync immédiate sur un serveur
# -------------------------------------------------------------
DISCORD_TOKEN = st.secrets.get("DISCORD_TOKEN", os.getenv("DISCORD_TOKEN", ""))
CLIENT_ID = st.secrets.get("CLIENT_ID", os.getenv("CLIENT_ID", ""))
GUILD_ID = st.secrets.get("GUILD_ID", os.getenv("GUILD_ID", ""))

if not DISCORD_TOKEN:
    st.error("DISCORD_TOKEN manquant. Ajoute-le dans Streamlit Secrets.")
    st.stop()

# Intents
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --------------------- Vue ban: confirmation par boutons ---------------------
class BanConfirmView(discord.ui.View):
    def __init__(self, requester_id: int, target_id: int, reason: str | None):
        super().__init__(timeout=60)
        self.requester_id = requester_id
        self.target_id = target_id
        self.reason = reason or "Aucune raison fournie"

    async def interaction_guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Tu n'es pas l'auteur de la demande.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirmer le ban", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_guard(interaction):
            return
        guild = interaction.guild
        me = guild.me or await guild.fetch_member(bot.user.id)

        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                "Tu n'as pas la permission de bannir.", ephemeral=True
            )
            return
        if not me.guild_permissions.ban_members:
            await interaction.response.send_message(
                "Je n'ai pas la permission 'Bannir des membres'.", ephemeral=True
            )
            return

        try:
            await guild.ban(discord.Object(id=self.target_id), reason=self.reason)
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Utilisateur <@{self.target_id}> banni. Raison: {self.reason}",
                view=self
            )
        except Exception as e:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"Impossible de bannir <@{self.target_id}> : {e}",
                view=self
            )

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_guard(interaction):
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Ban annulé.", view=self)

# ---------------------- Commande slash /ban ----------------------
@app_commands.default_permissions(ban_members=True)
@tree.command(name="ban", description="Bannir un utilisateur avec confirmation")
@app_commands.describe(user="Utilisateur à bannir", reason="Raison (optionnelle)")
async def ban_command(interaction: discord.Interaction, user: discord.User, reason: str | None = None):
    view = BanConfirmView(requester_id=interaction.user.id, target_id=user.id, reason=reason)
    await interaction.response.send_message(
        content=f"Tu veux vraiment bannir {user.mention} ?",
        view=view,
        ephemeral=True
    )

# ----------------- Commandes vocales: mute/deafen/move/disconnect -----------------
# Permissions requises côté bot: Mute Members, Deafen Members, Move Members

@app_commands.default_permissions(mute_members=True)
@tree.command(name="mute", description="Mute un membre dans le salon vocal actuel")
@app_commands.describe(user="Membre à mute", reason="Raison (optionnelle)")
async def mute_cmd(interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
    if not interaction.user.guild_permissions.mute_members:
        return await interaction.response.send_message("Tu n'as pas la permission de mute.", ephemeral=True)
    try:
        await user.edit(mute=True, reason=reason or "Mute via /mute")
        await interaction.response.send_message(f"{user.mention} a été mute.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Impossible de mute {user.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(mute_members=True)
@tree.command(name="unmute", description="Unmute un membre")
@app_commands.describe(user="Membre à unmute", reason="Raison (optionnelle)")
async def unmute_cmd(interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
    if not interaction.user.guild_permissions.mute_members:
        return await interaction.response.send_message("Tu n'as pas la permission d'unmute.", ephemeral=True)
    try:
        await user.edit(mute=False, reason=reason or "Unmute via /unmute")
        await interaction.response.send_message(f"{user.mention} a été unmute.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Impossible d'unmute {user.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(deafen_members=True)
@tree.command(name="deafen", description="Rend sourd un membre (server deafen)")
@app_commands.describe(user="Membre à rendre sourd", reason="Raison (optionnelle)")
async def deafen_cmd(interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
    if not interaction.user.guild_permissions.deafen_members:
        return await interaction.response.send_message("Tu n'as pas la permission de deafen.", ephemeral=True)
    try:
        await user.edit(deafen=True, reason=reason or "Deafen via /deafen")
        await interaction.response.send_message(f"{user.mention} est maintenant sourd.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Impossible de rendre sourd {user.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(deafen_members=True)
@tree.command(name="undeafen", description="Enlève le server deafen")
@app_commands.describe(user="Membre à réactiver", reason="Raison (optionnelle)")
async def undeafen_cmd(interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
    if not interaction.user.guild_permissions.deafen_members:
        return await interaction.response.send_message("Tu n'as pas la permission d'undeafen.", ephemeral=True)
    try:
        await user.edit(deafen=False, reason=reason or "Undeafen via /undeafen")
        await interaction.response.send_message(f"{user.mention} n'est plus sourd.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Impossible d'undeafen {user.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(move_members=True)
@tree.command(name="move", description="Déplace un membre vers un salon vocal")
@app_commands.describe(user="Membre à déplacer", channel="Salon vocal cible")
async def move_cmd(interaction: discord.Interaction, user: discord.Member, channel: discord.VoiceChannel):
    if not interaction.user.guild_permissions.move_members:
        return await interaction.response.send_message("Tu n'as pas la permission de déplacer des membres.", ephemeral=True)
    try:
        await user.move_to(channel)
        await interaction.response.send_message(f"{user.mention} a été déplacé vers {channel.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Impossible de déplacer {user.mention} : {e}", ephemeral=True)

@app_commands.default_permissions(move_members=True)
@tree.command(name="disconnect", description="Déconnecte un membre de son salon vocal")
@app_commands.describe(user="Membre à déconnecter")
async def disconnect_cmd(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.move_members:
        return await interaction.response.send_message("Tu n'as pas la permission de déconnecter des membres.", ephemeral=True)
    try:
        await user.move_to(None)
        await interaction.response.send_message(f"{user.mention} a été déconnecté du vocal.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Impossible de déconnecter {user.mention} : {e}", ephemeral=True)

# ----------------------------- Ready & Sync -----------------------------
@bot.event
async def on_ready():
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            await tree.sync(guild=guild)
        else:
            await tree.sync()
        print(f"Connecté en tant que {bot.user} — commandes synchronisées.")
    except Exception as e:
        print("Erreur de sync des commandes:", e)

# ---------------------- Démarrage dans un thread ----------------------

def run_bot_forever():
    asyncio.run(bot.start(DISCORD_TOKEN))

if "bot_thread" not in st.session_state:
    st.session_state.bot_thread = None

st.title("Dashboard Bot Discord")
st.write("Statut du bot lancé depuis Streamlit Cloud")

col1, col2 = st.columns(2)
with col1:
    running = st.session_state.bot_thread is not None and st.session_state.bot_thread.is_alive()
    st.metric("Bot en cours d'exécution", "Oui" if running else "Non")
with col2:
    st.text(f"Client ID: {CLIENT_ID or 'non défini'}")

start = st.button("Démarrer / Redémarrer le bot")
if start:
    if st.session_state.bot_thread and st.session_state.bot_thread.is_alive():
        st.info("Le bot tourne déjà.")
    else:
        t = threading.Thread(target=run_bot_forever, daemon=True)
        t.start()
        st.session_state.bot_thread = t
        st.success("Bot démarré")

st.markdown(
    """
    **Commandes disponibles**
    - /ban user reason
    - /mute user reason
    - /unmute user reason
    - /deafen user reason
    - /undeafen user reason
    - /move user channel
    - /disconnect user

    **Permissions à cocher pour le bot**
    - Ban Members
    - Mute Members
    - Deafen Members
    - Move Members
    - Send Messages
    - Use Application Commands
    - View Channels
    - Connect
    """
)
