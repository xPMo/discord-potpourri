#!python
import discord
import logging
import scrape.dragdown
from discord.commands import option
from discord.ext import commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

class Completions:
    def __init__(self, characters):
        self.characters = characters

    def palettes(self, ctx: discord.AutocompleteContext):
        char = ctx.options['character']
        skin = ctx.options['skin']
        try:
            return [k for k in characters[char].skins[skin]['palettes'].keys()
                    if k.lower().startswith(ctx.value.lower())]
        except:
            return []

    def skins(self, ctx: discord.AutocompleteContext):
        char = ctx.options['character']
        try:
            return [k for k in characters[char].skins.keys()
                    if k.lower().startswith(ctx.value.lower())]
        except:
            return []

    def attack(self, ctx: discord.AutocompleteContext):
        char = ctx.options['character']
        try:
            return [k for k in characters[char].framedata.keys()
                    if k.lower().startswith(ctx.value.lower())]
        except:
            return []

    def attackhit(self, ctx: discord.AutocompleteContext):
        char = ctx.options['character']
        attack = ctx.options['attack']
        try:
            return [k for k in characters[char].framedata[attack].keys()
                    if k.lower().startswith(ctx.value.lower())]
        except:
            return []

# have to create completions object first
characters = scrape.dragdown.characterlist()
completions = Completions(characters)

class Cog(discord.Cog):

    def __init__(self, bot, characters):
        logging.debug("Loading Rivals 2 Cog")
        self.bot = bot

    @discord.slash_command(name='resetc', description='Reload all data for Rivals 2 characters')
    async def resetc(self, ctx):
        logging.debug(f'{ctx.command}: {ctx.user}')
        logging.debug(f'{ctx.command}: {ctx.guild} ({ctx.guild_id}) {ctx.channel} ({ctx.channel_id})')

        new = scrape.dragdown.characterlist()
        characters.update(new)
        await ctx.respond('Reset!')

    @discord.slash_command(name='palette', description='Get a Rivals 2 palette')
    @option('character', description='Rivals 2 Character',
            autocomplete=discord.utils.basic_autocomplete(characters.keys())
    )
    @option('skin', description='Choose a skin',
            autocomplete=completions.skins
    )
    @option('palette', description='Choose a palette',
            autocomplete=completions.palettes
    )
    async def palette(self, ctx, character: str, skin: str, palette: str):
        logging.debug(f'{ctx.command}: {ctx.user}')
        logging.debug(f'{ctx.command}: {ctx.guild} ({ctx.guild_id}) {ctx.channel} ({ctx.channel_id})')
        try:
            c = characters[character]
            image, thumb, unlock_text, description = c.get_palette(skin, palette=palette)
            embed = discord.Embed(title=f'{skin} {character} ({palette})', description=description, url=image)
            embed.set_image(url=thumb)
            embed.set_footer(text=unlock_text)
            await ctx.respond(None, embed=embed)
        except KeyError as e:
            logging.info(f'{ctx.command}: No {character}/{skin}/{palette}', exc_info=e)
            await ctx.respond(f'Could not find {e} for {character}/{skin}/{palette}')

    @discord.slash_command(name='framedata', description='Get frame data for a particular move')
    @option('character', description='Rivals 2 Character',
            autocomplete=discord.utils.basic_autocomplete(characters.keys())
    )
    @option('attack', description='Choose an attack',
            autocomplete=completions.attack
    )
    @option('hit', description='Choose the variant/hit of the attack',
            autocomplete=completions.attackhit
    )
    async def framedata(self, ctx, character: str, attack: str, hit: str):
        try:
            ignorekeys = { 'attack', 'caption', 'character', 'hitboxes', 'images', 'name', }
            ignorevalues = {'False', 'N/A', ''}
            data = characters[character].framedata[attack][hit]
            embed = discord.Embed(title=f'{character} {data["attack"]} ({data["name"]})',
                                  description='\n'.join([f'- {k}: {v}' for k, v in data.items()
                                                         if k not in ignorekeys
                                                         and v not in ignorevalues])
                                  )
            await ctx.respond(None, embed=embed)
        except KeyError as e:
            logging.info(f'{ctx.command}: No {character}/{skin}/{palette}', exc_info=e)
            await ctx.respond(f'Could not find {e} for {character}/{skin}/{palette}')


    @discord.slash_command(name='stats', description='Get general stats for a Rivals 2 character')
    @option('character', description='Rivals 2 Character',
            autocomplete=discord.utils.basic_autocomplete(characters.keys())
    )
    async def stats(self, ctx, character: str):
        try:
            c = characters[character]
            embed = discord.Embed(title=f'{character}',
                                  description='\n'.join([f'- {k}: {v}' for k, v in c.stats.items() if k != 'chara'])
                                  )
            await ctx.respond(None, embed=embed)
        except KeyError as e:
            logging.info(f'{ctx.command}: No {character}/{skin}/{palette}', exc_info=e)
            await ctx.respond(f'Could not find {e} for {character}/{skin}/{palette}')

def setup(bot):
    bot.add_cog(Cog(bot, characters))
