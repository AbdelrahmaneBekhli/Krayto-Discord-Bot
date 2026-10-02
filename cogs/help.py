from __future__ import annotations

from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry, by_name, get_help_entries

FIELD_LIMIT = 1024  # Discord's per-field value limit
PREFERRED_ORDER = ("Games", "Utility", "Admin", "Other")


def _fit_field(lines: list[str]) -> str:
    """Join lines into one field value, dropping any that would overflow."""
    out: list[str] = []
    used = 0
    for line in lines:
        cost = len(line) + (1 if out else 0)
        if used + cost > FIELD_LIMIT:
            marker = "…"
            if used + len(marker) + 1 <= FIELD_LIMIT:
                out.append(marker)
            break
        out.append(line)
        used += cost
    return "\n".join(out)


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

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _visible_names(self) -> list[str]:
        """Command names that /help is willing to talk about."""
        entry_map = by_name(get_help_entries(self.bot))
        names = [name for name, entry in entry_map.items() if entry.show_in_help]
        names += [
            cmd.name
            for cmd in self.bot.tree.get_commands()
            if cmd.name not in entry_map
        ]
        return sorted(set(names))

    async def _command_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        current = current.lstrip("/").lower()
        return [
            app_commands.Choice(name=name, value=name)
            for name in self._visible_names()
            if current in name.lower()
        ][:25]

    @app_commands.command(name="help", description="Show commands and how to use them")
    @app_commands.describe(command="Get help for a specific command")
    @app_commands.autocomplete(command=_command_autocomplete)
    async def help(self, interaction: discord.Interaction, command: str | None = None) -> None:
        # Auto-detect all slash commands currently registered
        detected = {c.name: c for c in self.bot.tree.get_commands()}
        entries = get_help_entries(self.bot)
        entry_map = by_name(entries)

        # -------- Specific command help --------
        if command:
            name = command.lstrip("/").strip()
            meta = entry_map.get(name)
            cmd = detected.get(name)

            # Hidden commands are treated as nonexistent so /help never leaks them.
            if (meta and not meta.show_in_help) or (not cmd and not meta):
                return await interaction.response.send_message(
                    f"❌ I couldn't find `/{name}`.",
                    ephemeral=True,
                )

            desc = meta.summary if meta else (cmd.description if cmd else "")
            if meta and meta.details:
                desc = f"{desc}\n\n{meta.details.strip()}"
            embed = discord.Embed(
                title=f"Help • /{name}",
                description=(desc or "No description")[:4096],
            )

            if meta and meta.examples:
                embed.add_field(
                    name="Examples",
                    value=_fit_field([f"• `{ex}`" for ex in meta.examples]),
                    inline=False,
                )

            # If we have the actual command object, show options automatically
            parameters = getattr(cmd, "parameters", None)
            if parameters:
                meta_opt = meta.options_help if meta else {}
                opts = []

                for p in parameters:
                    required = "required" if p.required else "optional"

                    # Prefer per-cog override text, fallback to Discord description
                    opt_desc = meta_opt.get(p.name) or (p.description or "No description")

                    # If Discord provides choices and cog didn't override, append them
                    if (p.name not in meta_opt) and p.choices:
                        choices = ", ".join(choice.name for choice in p.choices)
                        opt_desc += f" (Choices: {choices})"

                    opts.append(f"• **{p.name}** ({required}) — {opt_desc}")

                embed.add_field(name="Options", value=_fit_field(opts), inline=False)

            embed.set_footer(text="Tip: type / and select a command to see its options.")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # -------- Main help page (categorized) --------
        embed = discord.Embed(
            title="Help",
            description="Available commands (buttons let you generate prompts without retyping).",
        )

        cats: defaultdict[str, list[str]] = defaultdict(list)

        # Prefer metadata for nice formatting (and to support hidden commands)
        for e in entries:
            if e.show_in_help:
                cats[e.category].append(f"**/{e.name}** — {e.summary}")

        # Also include detected commands that have no metadata (fallback)
        for name, cmd in detected.items():
            if name not in entry_map:
                cats["Other"].append(f"**/{name}** — {cmd.description or 'No description'}")

        # Render categories in stable order, then any remaining ones alphabetically
        extra = sorted(cat for cat in cats if cat not in PREFERRED_ORDER)
        for cat in (*PREFERRED_ORDER, *extra):
            if cats.get(cat):
                embed.add_field(name=cat, value=_fit_field(cats[cat]), inline=False)

        embed.add_field(
            name="Tips",
            value=(
                "• Use `/help <command>` for detailed help (e.g. `/help tod`)\n"
                "• Use `lock:true` to lock buttons to you"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
