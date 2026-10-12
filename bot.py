import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import threading
from discord.ext import tasks, commands
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
    pass  # Evita saturar los logs con peticiones HTTP


def run_web_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), SimpleHandler)
  server.serve_forever()


# Arrancar el servidor web en un hilo secundario
threading.Thread(target=run_web_server, daemon=True).start()
# ---------------------------------------------------------

# Configuración de Spotify
sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    )
)

playlist_id = os.getenv("SPOTIFY_PLAYLIST_ID")
voice_channel_name = os.getenv("VOICE_CHANNEL_NAME", "general")


class MusicBot(commands.Bot):

  def __init__(self):
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.voice_states = True
    super().__init__(command_prefix="!", intents=intents)

    self.last_track_uris = set()
    self.empty_timer = 0

  async def setup_hook(self):
    nodes = [
        wavelink.Node(
            uri=os.getenv("LAVALINK_URI"),
            password=os.getenv("LAVALINK_PASSWORD"),
        )
    ]
    await wavelink.Pool.init(nodes=nodes)

  async def on_ready(self):
    print(f"Bot conectado como {self.user} (ID: {self.user.id})")
    if not self.playlist_monitor.is_running():
      self.playlist_monitor.start()

  @tasks.loop(seconds=10)
  async def playlist_monitor(self):
    try:
      results = sp.playlist_tracks(playlist_id)
      current_tracks = [
          item["track"]["uri"]
          for item in results["items"]
          if item["track"] and item["track"]["uri"]
      ]
      current_tracks_set = set(current_tracks)

      if not self.guilds:
        return
      guild = self.guilds[0]
      player: wavelink.Player = guild.voice_client

      if current_tracks_set - self.last_track_uris and not player:
        voice_channel = discord.utils.get(
            guild.voice_channels, name=voice_channel_name
        )
        if voice_channel:
          player = await voice_channel.connect(cls=wavelink.Player)
          print(f"Conectado automáticamente a {voice_channel.name}")

      self.last_track_uris = current_tracks_set

      if player and player.connected:
        if not player.playing and player.queue.is_empty:
          if current_tracks:
            tracks = await wavelink.Playable.search(
                f"https://open.spotify.com/playlist/{playlist_id}"
            )
            if tracks:
              if isinstance(tracks, wavelink.Playlist):
                player.queue.extend(tracks.tracks)
              else:
                player.queue.put(tracks[0])
              await player.play(player.queue.get())
              self.empty_timer = 0
          else:
            self.empty_timer += 10
            if self.empty_timer >= 300:
              await player.disconnect()
              print("Desconectado por inactividad (playlist vacía por 5 min).")
              self.empty_timer = 0
        else:
          self.empty_timer = 0

    except Exception as e:
      print(f"Error en el monitor de playlist: {e}")

  @playlist_monitor.before_loop
  async def before_monitor(self):
    await self.wait_until_ready()


bot = MusicBot()

if __name__ == "__main__":
  bot.run(os.getenv("DISCORD_TOKEN"))