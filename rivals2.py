#!python
import discord
import logging
import scrape.dragdown
from discord.commands import option
from discord.ext import commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

def logreturn(f):
    def wrapped(*args, **kwargs):
        logging.info(f'function called {args} {kwargs}')
        ret = f(*args, **kwargs)
        logging.info(f'function returned {ret}')
        return ret
    return wrapped

class Completions:
    def __init__(self, characters):
        self.characters = characters

    def matchprefix(iterator, pfx):
        if pfx in iterator:
            return [pfx]
        if matched := [item for item in iterator if pfx == item.lower()]:
            return matched
        if matched := [item for item in iterator if item.lower().startswith(pfx.lower())]:
            return matched
        return [item for item in iterator if any(word.lstrip('(').lower().startswith(pfx.lower())
                                     for word in item.split())]

    def skins(self, ctx: discord.AutocompleteContext):
        char = ctx.options['character']
        return Completions.matchprefix(characters[char].skins.keys(), ctx.value)

    def palettes(self, ctx: discord.AutocompleteContext):
        char = ctx.options['character']
        skin = ctx.options['skin']
        try:
            return Completions.matchprefix(characters[char].skins[skin].keys(), ctx.value)
        except:
            return []

    def attack(self, ctx: discord.AutocompleteContext):
        char = ctx.options['character']
        try:
            return Completions.matchprefix(characters[char].framedata.keys(), ctx.value)
        except:
            return []

    def attackhit(self, ctx: discord.AutocompleteContext):
        char = ctx.options['character']
        attack = ctx.options['attack']
        try:
            return Completions.matchprefix(characters[char].framedata[attack].keys(), ctx.value)
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
            autocomplete=completions.palettes,
            required=False, default='Default'
    )
    async def palette(self, ctx, character: str, skin: str, palette: str):
        logging.debug(f'{ctx.command}: {ctx.user}')
        logging.debug(f'{ctx.command}: {ctx.guild} ({ctx.guild_id}) {ctx.channel} ({ctx.channel_id})')
        try:
            c = characters[character]
            skin_ = c.skins[skin]
            palette_ = skin_[palette]
            embed = discord.Embed(title=f'{skin} {character} ({palette})',
                                  description=skin_.description,
                                  url=c.url + '#' + palette.replace(' ', '_'))
            embed.set_image(url=palette_.image().replace(' ', '_'))
            embed.set_footer(text=palette_.unlock)
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
            if data.get('images'):
                embed.set_image(url=data['images'])
            await ctx.respond(None, embed=embed)
        except KeyError as e:
            logging.info(f'{ctx.command}: No {character}/{attack}/{hit}', exc_info=e)
            await ctx.respond(f'Could not find {e} for {character}/{attack}/{hit}')


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
