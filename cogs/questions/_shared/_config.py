from discord import app_commands

API_ROOT = "https://api.truthordarebot.xyz"
API_V1 = f"{API_ROOT}/v1"
API_API = f"{API_ROOT}/api"

# Central rating choices
RATING_CHOICES = [
    app_commands.Choice(name="Any", value="any"),
    app_commands.Choice(name="PG", value="pg"),
    app_commands.Choice(name="PG-13", value="pg13"),
    app_commands.Choice(name="R", value="r"),
]
