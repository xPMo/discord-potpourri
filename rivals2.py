#!python
import discord
import logging
import scrape.dragdown
import re
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
    stripword = re.compile(r'\b[^ a-zA-Z]*|[^ a-zA-Z]*\b')

    @classmethod
    def matchprefix(cls, iterator, pfx):
        if pfx in iterator:
            return [pfx]
        if matched := [item for item in iterator if pfx == item.lower()]:
            return matched
        stripped = {re.sub(Completions.stripword, '', item.lower()): item for item in iterator}
        matched = {stripped[key] for key in stripped if key.startswith(pfx.lower())}
        matched.update(stripped[key] for key in stripped if any(word.startswith(pfx.lower()) for word in key.split()))
        if matched:
            return matched
        return [x for x in iterator if pfx in x]

    @classmethod
    def completer(cls, getlist, *names):
        def complete(ctx: discord.AutocompleteContext):
            it = getlist(*(ctx.options[name] for name in names))
            return Completions.matchprefix(it, ctx.value)
        return complete

wiki = scrape.dragdown.Wiki()
characters = scrape.dragdown.characterlist(wiki)
emotes = scrape.dragdown.emotelist(wiki)

logging.info(f'Fetched {len(characters)} characters and {len(emotes)} emotes')

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
            autocomplete=Completions.completer(lambda char: characters[char].skins.keys(), 'character')
    )
    @option('palette', description='Choose a palette',
            autocomplete=Completions.completer(lambda char, skin: characters[char].skins[skin].keys(), 'character', 'skin'),
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
            embed.set_footer(text=palette_.unlock, icon_url = skin_.rarity.icon_url())
            await ctx.respond(None, embed=embed)
        except KeyError as e:
            logging.info(f'{ctx.command}: No {character}/{skin}/{palette}', exc_info=e)
            await ctx.respond(f'Could not find {e} for {character}/{skin}/{palette}')

    @discord.slash_command(name='framedata', description='Get frame data for a particular move')
    @option('character', description='Rivals 2 Character',
            autocomplete=discord.utils.basic_autocomplete(characters.keys())
    )
    @option('attack', description='Choose an attack',
            autocomplete=Completions.completer(lambda char: characters[char].framedata.keys(), 'character'),
    )
    @option('hit', description='Choose the variant/hit of the attack',
            autocomplete=Completions.completer(lambda char, attack: characters[char].framedata[attack].keys(), 'character', 'attack'),
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

    @discord.slash_command(name='topic', description='Get a topic from a character page')
    @option('character', description='Rivals 2 Character',
            autocomplete=discord.utils.basic_autocomplete(['General', *characters.keys()])
    )
    @option('topic', description='Choose a topic',
            autocomplete=Completions.completer(lambda char: ({'General': wiki} | characters)[char].topics.keys(), 'character'),
    )
    async def topic(self, ctx, character: str, topic: str):
        try:
            data = ({'General': wiki} | characters)[character].topics[topic]
            embed = discord.Embed(title=f'{topic}', description=data[:4000])
            await ctx.respond(None, embed=embed)
        except KeyError as e:
            logging.info(f'{ctx.command}: No {character}/{topic}', exc_info=e)
            await ctx.respond(f'Could not find {e} for {character}/{topic}')

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
            logging.info(f'{ctx.command}: No {character}', exc_info=e)
            await ctx.respond(f'Could not find stats for {character}')

    @discord.slash_command(name='emote', description='Get a Rivals 2 Emote!')
    @option('name', description='Name of the emote',
            autocomplete=Completions.completer(emotes.keys)
            )
    async def emote(self, ctx, name: str):
        logging.debug(f'{ctx.command}: {ctx.user}')
        logging.debug(f'{ctx.command}: {ctx.guild} ({ctx.guild_id}) {ctx.channel} ({ctx.channel_id})')
        try:
            emote = emotes[name]
            url   = emote.url()
            await ctx.respond(f'**{emote.text}**\n-# [{emote.unlock.replace("\n", " - ")}]({url})')
        except KeyError as e:
            logging.info(f'{ctx.command}: No emote {name}', exc_info=e)
            await ctx.respond(f'Could not find {name}')


def setup(bot):
    bot.add_cog(Cog(bot, characters))
