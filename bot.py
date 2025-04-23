#!python
import discord
import logging
import os
import random
import scrape.dragdown
from bs4 import BeautifulSoup
from discord.commands import option
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

load_dotenv('.env')
token = os.environ['BOT_TOKEN']

## Bot
intents = discord.Intents.default()
bot = discord.Bot()
bot.default_command_integration_types.add(discord.IntegrationType.user_install)

def prefix_match_key(prefix, dictionary):
    '''
    :param dictionary: expected to itemize() into key-value pairs, where key is a lowercase string
    :return list[T]: the matching items
    '''
    return [v for k, v in dictionary.items() if any(s.startswith(prefix.lower()) for s in [k, *k.split()])]

def list_complete(dictionary, get_name):
    def completer(ctx: discord.AutocompleteContext):
        return [get_name(v) for v in prefix_match_key(ctx.value, dictionary)]
    return completer

@bot.event
async def on_ready():
    logging.info(f'We have logged in as {bot.user}')

@bot.slash_command(name='ping', description='Are you still there?')
async def ping(ctx):
    logging.debug(f'{ctx.command}: {ctx.user}')
    logging.debug(f'{ctx.command}: {ctx.guild} ({ctx.guild_id}) {ctx.channel} ({ctx.channel_id})')
    await ctx.respond(f'**Pong!** ({round(1000 * bot.latency, 1)}ms)')

rivals2characters = scrape.dragdown.characterlist()

def rivals2_palette_complete(ctx: discord.AutocompleteContext):
    char = ctx.options['character']
    skin = ctx.options['skin']
    try:
        return [k for k in rivals2characters[char].skins[skin].keys()
                if k.lower().startswith(ctx.value.lower())]
    except:
        return []

def rivals2_skin_complete(ctx: discord.AutocompleteContext):
    char = ctx.options['character']
    try:
        return [k for k in rivals2characters[char].skins.keys()
                if k.lower().startswith(ctx.value.lower())]
    except:
        return []

@bot.slash_command(name='palette', description='Get a Rivals 2 palette')
@option('character', description='Rivals 2 Character',
        autocomplete=discord.utils.basic_autocomplete(rivals2characters.keys())
)
@option('skin', description='Choose a skin',
        autocomplete=rivals2_skin_complete
)
@option('palette', description='Choose a palette',
        autocomplete=rivals2_palette_complete
)
async def r2pallete(ctx, character: str, skin: str, palette: str):
    logging.debug(f'{ctx.command}: {ctx.user}')
    logging.debug(f'{ctx.command}: {ctx.guild} ({ctx.guild_id}) {ctx.channel} ({ctx.channel_id})')
    try:
        full, thumb, unlock = rivals2characters[character].skins[skin][palette]
        embed = discord.Embed(title=f'{skin} {character} ({palette})')
        embed.url = scrape.dragdown.DOMAIN + full
        embed.set_image(url='https:' + thumb)
        embed.set_footer(text=unlock)
        await ctx.respond(None, embed=embed)
    except KeyError as e:
        logging.info(f'{ctx.command}: No {character}/{skin}/{palette}', exc_info=e)
        await ctx.respond(f'Could not find {e} for {character}/{skin}/{palette}')
# Not ready yet
#@bot.slash_command(name='deck', description='Draw from a deck of cards')

bot.run(token)
