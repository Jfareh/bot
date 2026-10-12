@bot.tree.command(
    name="start",
    description="Reproduce tu playlist de Spotify buscando los temas automáticamente",
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
    # 1. Obtenemos las canciones de la playlist usando Spotify API (Spotipy)
    playlist_data = sp.playlist_items(playlist_id)
    added_count = 0

    for item in playlist_data.get("items", []):
      track_info = item.get("track")
      if track_info:
        track_name = track_info["name"]
        artist_name = track_info["artists"][0]["name"]
        query = f"{track_name} - {artist_name}"

        # 2. Buscamos la canción equivalente en el nodo de audio
        search_results = await wavelink.Playable.search(query)
        if search_results:
          player.queue.put(search_results[0])
          added_count += 1

    if added_count == 0:
      await interaction.followup.send(
          "No se pudieron encontrar canciones de la playlist."
      )
      return

    # 3. Reproducimos si el reproductor está libre
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