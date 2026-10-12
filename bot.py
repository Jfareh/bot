import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import threading
from discord.ext import commands
import discord
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import wavelink
from dotenv import load_dotenv

load_dotenv()

# --- SERVIDOR WEB MINIATURA PARA QUE RENDER SEA GRATIS ---


class SimpleHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b"Bot de Musica Activo!")

  def log_message(self, format, *args):
    pass


def run_web_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), SimpleHandler)
  server.serve_forever()


threading.Thread(target=run_web_server, daemon=True).start()
# ---------------------------------------------------------

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    )
)

playlist_id = os.getenv("SPOTIFY_PLAYLIST_ID")


class MusicBot(commands.Bot):

  def __init__(self):
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.voice_states = True
    super().__init__(command_prefix="!", intents=intents)

  async def setup_hook(self):
    print("[DEBUG] Conectando con el nodo Lavalink...")
    try:
      node = wavelink.Node(
          uri=os.getenv("LAVALINK_URI"),
          password=os.getenv("LAVALINK_PASSWORD"),
      )
      await wavelink.Pool.connect(client=self, nodes=[node])
    except Exception as e:
      print(f"[ERROR] No se pudo iniciar el nodo Lavalink: {e}")

    for guild in self.guilds:
      self.tree.clear_commands(guild=guild)
      self.tree.copy_global_to(guild=guild)
      await self.tree.sync(guild=guild)
    print("[DEBUG] Comandos sincronizados.")

  async def on_ready(self):
    print(f"Bot conectado como {self.user} (ID: {self.user.id})")


bot = MusicBot()


@bot.listen()
async def on_wavelink_node_ready(node: wavelink.Node):
  print(f"[DEBUG] ¡Nodo Lavalink '{node.identifier}' conectado y listo!")


@bot.tree.command(
    name="start",
    description="Conecta al bot a tu canal de voz y reproduce la playlist",
)
async def start(interaction: discord.Interaction):
  if not interaction.user.voice or not interaction.user.voice.channel:
    await interaction.response.send_message(
        "¡Debes estar conectado a un canal de voz para usar este comando!",
        ephemeral=True,
    )
    return

  # Comprobar si hay un nodo de Wavelink conectado antes de continuar
  try:
    wavelink.Pool.get_node()
  except Exception:
    await interaction.response.send_message(
        "⚠️ El servidor de audio (Lavalink) todavía no está conectado o está"
        " tardando en responder. Revisa los logs en Render o intenta de nuevo"
        " en unos segundos.",
        ephemeral=True,
    )
    return

  voice_channel = interaction.user.voice.channel
  player: wavelink.Player = interaction.guild.voice_client

  await interaction.response.defer()

  if not player:
    try:
      player = await voice_channel.connect(cls=wavelink.Player)
    except Exception as e:
      await interaction.followup.send(
          f"No se pudo conectar al canal de voz: {e}"
      )
      return

  try:
    tracks = await wavelink.Playable.search(
        f"https://open.spotify.com/playlist/{playlist_id}"
    )
    if not tracks:
      await interaction.followup.send(
          "No se encontraron canciones en la playlist de Spotify."
      )
      return

    if isinstance(tracks, wavelink.Playlist):
      player.queue.extend(tracks.tracks)
    else:
      player.queue.put(tracks[0])

    if not player.playing:
      await player.play(player.queue.get())
      await interaction.followup.send(
          f"¡Conectado a **{voice_channel.name}** y reproduciendo la playlist"
          " de Spotify! 🎶"
      )
    else:
      await interaction.followup.send(
          "¡Canciones añadidas a la cola de reproducción!"
      )

  except Exception as e:
    await interaction.followup.send(
        f"Ocurrió un error al cargar la música: {e}"
    )


@bot.tree.command(
    name="stop", description="Detiene la música y desconecta al bot del canal"
)
async def stop(interaction: discord.Interaction):
  player: wavelink.Player = interaction.guild.voice_client
  if player:
    await player.disconnect()
    await interaction.response.send_message(
        "¡Música detenida y bot desconectado del canal de voz! 👋"
    )
  else:
    await interaction.response.send_message(
        "El bot no está conectado a ningún canal de voz.", ephemeral=True
    )


if __name__ == "__main__":
  bot.run(os.getenv("DISCORD_TOKEN"))