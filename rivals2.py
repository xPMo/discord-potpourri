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
    stripword = re.compile(r'\b[^ a-zA-Z0-9]*|[^ a-zA-Z0-9]*\b')

    @classmethod
    def matchprefix(cls, iterator, pfx):
        if not pfx:
            return iterator
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
class FramedataIgnore:
    keys = { 'attack', 'caption', 'character', 'hitboxes', 'images', 'name', }
    values = {'N/A', 'Default', 'SpecifiedAngle', ''}
    pairs = {
        ('hitboxCaption',  ''),
        ('hitboxCaption',  None),
        ('landlag',  'N/A'),
        ('shieldAdv',  ''),
        ('damage',  '3%'),
        ('baseKb',  '4.0'),
        ('kbScale',  '0.0'),
        ('autoFloorhugFlag',  'False'),
        ('isProjectileFlag',  'False'),
        ('isArticleFlag',  'False'),
        ('bReverseCat',  'N/A'),
        ('hitpauseMulti',  '1.0'),
        ('extraOppHitpause',  '0'),
        ('hitpauseMovementStrength',  '1.0'),
        ('ssdiMulti',  '1.0'),
        ('asdiMulti',  '1.0'),
        ('reverseHitFlag',  'True'),
        ('forceFlinchFlag',  'False'),
        ('groundTechableFlag',  'True'),
        ('breakProjectileFlag',  'Default'),
        ('weightIndependentFlag',  'False'),
        ('knockbackFlipper',  'SpecifiedAngle'),
        ('hitstunMulti',  '1.0'),
        ('hitfallHitstunMulti',  '1.0'),
        ('parryReaction',  'Stun'),
        ('grabPartnerInteraction',  'None'),
        ('extraShieldStun',  '0'),
        ('shieldDamageMulti',  '1.0'),
        ('shieldPushbackMulti',  '1.0'),
        ('shieldHitpauseMulti',  '1.0'),
        ('fullChargeKbMulti',  '1.0'),
        ('fullChargeDamageMulti',  '1.0'),
        ('forceTumbleFlag',  'False'),
        ('notes', ''),
    }

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
    @option('palette', description='(Optional) Choose a palette',
            autocomplete=Completions.completer(lambda char, skin: characters[char].skins[skin].keys(), 'character', 'skin'),
            required=False, default=None
    )
    async def palette(self, ctx, character: str, skin: str, palette: str):
        logging.debug(f'{ctx.command}: {ctx.user}')
        logging.debug(f'{ctx.command}: {ctx.guild} ({ctx.guild_id}) {ctx.channel} ({ctx.channel_id})')
        try:
            c = characters[character]
            skin_ = c.skins[skin]
            description = skin_.description
            if palette:
                palettes = [skin_[palette]]
                title = f'{skin} {character} ({palette})'
            else:
                title = f'{skin} {character}'
                palettes = [*skin_.values()]
            # pycord: limit embeds in a response to 10.
            for i in range(0, len(palettes), 10):
                embeds = []
                for pal in palettes[i:i+10]:
                    embed = discord.Embed(title=title,
                                          description=description,
                                          url=c.url + '#' + skin.replace(' ', '_'))
                    embed.set_image(url=pal.image().replace(' ', '_'))
                    embed.set_footer(text=pal.unlock, icon_url=skin_.rarity.icon_url() if skin_.rarity else None)
                    embeds.append(embed)
                await ctx.respond(None, embeds=embeds)
                # Less clutter on subsequent embed groups
                description = None
                title = f'{skin} {character} (continued)'

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
            c = characters[character]
            data = c.framedata[attack][hit]
            embed = discord.Embed(title=f'{character} {data["attack"]} ({data["name"]})',
                                  url=c.url + '#' + data["attack"].replace(' ', '_'),
                                  description='\n'.join([f'- {k}: {v}' for k, v in data.items()
                                                         if k not in FramedataIgnore.keys
                                                         and v not in FramedataIgnore.values
                                                         and (k, v) not in FramedataIgnore.pairs
                                                         ])
                                  )
            if 'caption' in data:
                embed.set_footer(text=' / '.join(data['caption']), icon_url = c.icon_url if hasattr(c, 'icon_url') else None)
            if not 'images' in data:
                await ctx.respond(None, embed=embed)
            else:
                embeds = [embed]
                for image in data['images']:
                    embeds.append(discord.Embed(title=embed.title, url=embed.url).set_image(url=image))
                await ctx.respond(None, embeds=embeds)
        except KeyError as e:
            logging.info(f'{ctx.command}: No {character}/{attack}/{hit}', exc_info=e)
            await ctx.respond(f'Could not find {e} for {character}/{attack}/{hit}')

    @discord.slash_command(name='topic', description='Get a topic from a character page')
    @option('character', description='Rivals 2 Character',
            autocomplete=discord.utils.basic_autocomplete(['General', *characters.keys()])
    )
    @option('fulltopic', description='Choose a topic',
            autocomplete=Completions.completer(lambda char: ({'General': wiki} | characters)[char].topics.keys(), 'character'),
    )
    async def topic(self, ctx, character: str, topic: str):
        try:
            c   = ({'General': wiki} | characters)[character]
            obj = c.topics[topic]
            embed = discord.Embed(title=obj.title, url = obj.url, description=obj.body[:4000])
            embed.set_footer(text=obj.caption, icon_url = c.icon_url if hasattr(c, 'icon_url') else None)
            await ctx.respond(None, embed=embed)
        except KeyError as e:
            logging.info(f'{ctx.command}: No {character}/{topic}', exc_info=e)
            await ctx.respond(f'Could not find {e} for {character}/{topic}')

    @discord.slash_command(name='glossary', description='Get the definition of a term from the glossary')
    @option('term', description='The term to look up',
            autocomplete=Completions.completer(wiki.glossary.keys)
    )
    async def glossary(self, ctx, term: str):
        try:
            obj = wiki.glossary[term]
            text = [f'**[{obj.term}](<{obj.url()}>)**: {obj.summary}']
            #embed = discord.Embed(title=obj.term, url=obj.url(), description=obj.summary)
            if obj.display:
                text.append(f' [(video)]({obj.display})')
            if obj.links:
                text.extend(['\n-# **See also**: ', ', '.join(obj.links)])
                #embed.add_field(name='See also', value=', '.join(obj.links))
            if obj.aliases:
                text.extend(['\n-# (Also known as ', ', '.join(repr(alias) for alias in obj.aliases), ')' ])
                #embed.add_field(name='Also known as', value=', '.join(obj.aliases))
            await ctx.respond(''.join(text))
            #await ctx.respond(embed=embed)
        except KeyError as e:
            logging.info(f'{ctx.command}: No glossary term {term}', exc_info=e)
            await ctx.respond(f'Could not find {e} for glossary term {term}')

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
