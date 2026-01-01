import discord
from discord import app_commands
from discord.ext import commands
from collections import defaultdict

from cogs._help_registry import HelpEntry, get_help_entries, by_name


class Help(commands.Cog):
    HELP_ENTRIES = [
        HelpEntry(
            name="help",
            summary="Show available commands and usage",
            category="Utility",
            examples=[
                "/help",
                "/help tod",
                "/help paranoia",
            ],
            show_in_help=True,
            options_help={
                "command": "Optional command name for detailed help (e.g. `tod`, `paranoia`)",
            },
        )
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show commands and how to use them")
    @app_commands.describe(command="Get help for a specific command")
    async def help(self, interaction: discord.Interaction, command: str | None = None):
        # Auto-detect all slash commands currently registered
        detected = {c.name: c for c in self.bot.tree.get_commands()}
        entries = get_help_entries(self.bot)
        entry_map = by_name(entries)

        # -------- Specific command help --------
        if command:
            name = command.lstrip("/").strip()
            cmd = detected.get(name)
            meta = entry_map.get(name)

            if not cmd and not meta:
                return await interaction.response.send_message(
                    f"❌ I couldn't find `/{name}`.",
                    ephemeral=True,
                )

            title = f"Help • /{name}"
            desc = (meta.summary if meta else (cmd.description if cmd else ""))
            embed = discord.Embed(title=title, description=desc or "No description")

            if meta and meta.examples:
                embed.add_field(
                    name="Examples",
                    value="\n".join(f"• `{ex}`" for ex in meta.examples),
                    inline=False,
                )

            # If we have the actual command object, show options automatically
            if cmd and getattr(cmd, "parameters", None) and cmd.parameters:
                opts = []
                meta_opt = meta.options_help if meta else {}

                for p in cmd.parameters:
                    required = "required" if p.required else "optional"

                    # Prefer per-cog override text, fallback to Discord description
                    opt_desc = meta_opt.get(p.name) or (p.description or "No description")

                    # If Discord provides choices and cog didn't override, append them
                    if (p.name not in meta_opt) and p.choices:
                        choices = ", ".join(choice.name for choice in p.choices)
                        opt_desc += f" (Choices: {choices})"

                    opts.append(f"• **{p.name}** ({required}) — {opt_desc}")

                embed.add_field(name="Options", value="\n".join(opts), inline=False)

            embed.set_footer(text="Tip: type / and select a command to see its options.")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # -------- Main help page (categorized) --------
        embed = discord.Embed(
            title="Help",
            description="Available commands (buttons let you generate prompts without retyping).",
        )

        cats = defaultdict(list)

        # Prefer metadata for nice formatting (and to support hidden commands)
        for e in entries:
            if e.show_in_help:
                cats[e.category].append(f"**/{e.name}** — {e.summary}")

        # Also include detected commands that have no metadata (fallback)
        for name, cmd in detected.items():
            if name not in entry_map:
                cats["Other"].append(f"**/{name}** — {cmd.description or 'No description'}")

        # Render categories in stable order
        preferred_order = ["Games", "Utility", "Admin", "Other"]
        for cat in preferred_order:
            if cats.get(cat):
                embed.add_field(name=cat, value="\n".join(cats[cat]), inline=False)

        # Any remaining categories
        for cat, lines in cats.items():
            if cat not in preferred_order and lines:
                embed.add_field(name=cat, value="\n".join(lines), inline=False)

        embed.add_field(
            name="Tips",
            value=(
                "• Use `/help <command>` for detailed help (e.g. `/help tod`)\n"
                "• Use `lock:true` to lock buttons to you"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
