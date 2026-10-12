@bot.listen()
async def on_wavelink_node_ready(node: wavelink.Node):
  print(
      f"[DEBUG] ✅ ¡Nodo Lavalink '{node.identifier}' conectado y listo para"
      " reproducir!"
  )


@bot.listen()
async def on_wavelink_node_error(node: wavelink.Node, error: Exception):
  print(f"[ERROR NODO] El nodo {node.identifier} falló: {error}")