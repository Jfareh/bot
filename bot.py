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
    print("[DEBUG] Intentando conectar con el nodo Lavalink...")
    try:
      node = wavelink.Node(
          uri=os.getenv("LAVALINK_URI"),
          password=os.getenv("LAVALINK_PASSWORD"),
      )
      await asyncio.wait_for(
          wavelink.Pool.connect(client=self, nodes=[node]), timeout=10.0
      )
      print("[DEBUG] ¡Conexión con Lavalink enviada con éxito!")
    except asyncio.TimeoutError:
      print(
          "[ERROR CRITICO] ⏳ La conexión con Lavalink agotó el tiempo límite"
          " (Timeout)."
      )
    except Exception as e:
      print(f"[ERROR CRITICO] Falló la conexión con Lavalink: {e}")

    for guild in self.guilds:
      self.tree.clear_commands(guild=guild)
      self.tree.copy_global_to(guild=guild)
      await self.tree.sync(guild=guild)
    print("[DEBUG] Comandos sincronizados.")

  async def on_ready(self):
    print(f"Bot conectado como {self.user} (ID: {self.user.id})")


# ==========================================
# 1. INSTANCIAMOS EL BOT
# ==========================================
bot = MusicBot()


# ==========================================
# 2. EVENTOS Y COMANDOS
# ==========================================
@bot.listen()
async def on_wavelink_node_ready(node: wavelink.Node):
  print(f"[DEBUG] ✅ ¡Nodo Lavalink '{node.identifier}' conectado y listo!")


@bot.listen()
async def on_wavelink_node_error(node: wavelink.Node, error: Exception):
  print(f"[ERROR NODO] El nodo {node.identifier} falló: {error}")


@bot.tree.command(
    name="start",
    description=(
        "Reproduce tu playlist de Spotify buscando los temas automáticamente"
    ),
)
async def start(interaction: discord.Interaction):
  if not interaction.user.voice or not interaction.user.voice.channel:
    await interaction.response.send_message(
        "¡Debes estar conectado a un canal de voz para usar este comando!",
        ephemeral=True,
    )
    return

  try:
    node = wavelink.Pool.get_node()
    if not node:
      raise Exception("No hay nodo disponible")
  except Exception:
    await interaction.response.send_message(
        "⚠️ El servidor de audio (Lavalink) no está conectado.", ephemeral=True
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
    playlist_data = sp.playlist_items(playlist_id)
    added_count = 0

    for item in playlist_data.get("items", []):
      track_info = item.get("track")
      if track_info:
        track_name = track_info["name"]
        artist_name = track_info["artists"][0]["name"]
        query = f"{track_name} - {artist_name}"

        search_results = await wavelink.Playable.search(query)
        if search_results:
          player.queue.put(search_results[0])
          added_count += 1

    if added_count == 0:
      await interaction.followup.send(
          "No se pudieron encontrar canciones de la playlist."
      )
      return

    if not player.playing:
      await player.play(player.queue.get())
      await interaction.followup.send(
          f"¡Conectado a **{voice_channel.name}**! Reproduciendo tu playlist de"
          f" Spotify ({added_count} canciones cargadas) 🎶"
      )
    else:
      await interaction.followup.send(
          f"¡Se añadieron {added_count} canciones de Spotify a la cola!"
      )

  except Exception as e:
    await interaction.followup.send(
        f"Ocurrió un error al procesar la playlist: {e}"
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