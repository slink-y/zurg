import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DOWNLOAD_CHANNEL_ID = int(os.getenv("DOWNLOAD_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class DestinationDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="music/"),
            discord.SelectOption(label="media/"),
            discord.SelectOption(label="shared/"),
            discord.SelectOption(label="downloads/"),
        ]
        super().__init__(
            placeholder="Choose a destination...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
            )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Files will be saved to `{self.values[0]}`", ephemeral=True
        )

class DownloadView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(DestinationDropdown())

    @discord.ui.button(label="Add Note", style=discord.ButtonStyle.primary, row=1)
    async def add_note_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NoteModal())

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Download cancelled.", view=None)


class NoteModal(discord.ui.Modal, title="Add a Note"):
    note = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"📝 Note saved: {self.note.value}", ephemeral=True)


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if message.channel.id == DOWNLOAD_CHANNEL_ID and "http" in message.content:
        # Simulated download
        view = DownloadView()
        await message.channel.send(
            content=f"Downloading from: {message.content}\nProgress: **0%**",
            view=view
        )


bot.run(TOKEN)