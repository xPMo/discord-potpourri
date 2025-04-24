#!python
import discord
import logging
import os
import random
import scrape.dragdown
from bs4 import BeautifulSoup
from discord.commands import option
from discord.ext import commands
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

load_dotenv('.env')
token = os.environ['BOT_TOKEN']

## Bot
intents = discord.Intents.default()
bot = discord.Bot()
bot.default_command_integration_types.add(discord.IntegrationType.user_install)

bot.load_extension('rivals2')

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

bot.run(token)
