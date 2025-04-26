#!python
import collections
import enum
import re
import itertools
import logging
import requests
import mwparserfromhell as mw

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

BASEURL = 'https://dragdown.wiki/wiki/'
class Wiki:
    def __init__(self):
        self.session = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.__exit__(*args)

    def fetch(self, path):
        return self.session.get(BASEURL + path, params={'action': 'raw'}).content.decode()

def table_by_columns(node):
    ret = {}
    headings = node.contents.ifilter_tags(matches=lambda node: node.tag == 'th')
    rows = node.contents.ifilter_tags(matches=lambda node: node.tag == 'tr')
    return itertools.zip_longest([heading.contents.strip() for heading in headings], *[row.contents.nodes for row in rows])

def parsetemplate(template):
    match template.name:
        case 'ShopRarity':
            return Rarity(template.params[0].strip())

class Rarity(enum.StrEnum):
    UNKNOWN = 'Unknown',
    COMMON  = 'Common',
    RARE    = 'Rare',
    EPIC    = 'Epic',
    LEGEND  = 'Legendary'

    @classmethod
    def from_template(cls, template):
        try:
            return cls(template.params[0].strip())
        except:
            return cls('Unknown')

    def icon_url(self):
        return BASEURL + 'Special:Redirect/file/RoA2_Rarity_' +  self + '.png'

class Skin(dict):
    def __init__(self, *args, description=None, rarity=Rarity('Common'), **kwargs):
        self.description = description
        self.rarity      = rarity
        super().__init__(*args, **kwargs)

class SkinPalette:
    def __init__(self, wiki, name, image, unlock):
        self.wiki = wiki
        match name:
            case None:
                self.name = ''
            case mw.nodes.Tag:
                self.name = name.contents.strip()
            case _:
                self.name = name.strip()
        if hasattr(image, 'contents'):
            self.imagelink = image.contents.filter_wikilinks()[0]
        else:
            self.imagelink = image
        if hasattr(unlock, 'contents'):
            self.unlock = unlock.contents.strip()
        else:
            self.unlock = unlock

    def image(self, thumb=None):
        url = BASEURL + 'Special:Redirect/file/' + self.imagelink.title.removeprefix('File:')
        if thumb == True:
            return url + '?width=' + re.match('^[0-9]*', self.imagelink.text.nodes[0].value).group()
        if isinstance(thumb, int) and thumb > 0:
            return url + '?width=' + str(thumb)
        return url

    def __repr__(self):
        return 'SkinPalette({!r}, {!r}, {!r}, {!r})'.format(
                self.wiki, self.name, self.imagelink, self.unlock)

class Character:

    def __init__(self, wiki, path):
        self.wiki = wiki
        self.path = path
        self.url  = BASEURL + path

    @property
    def page(self):
        if hasattr(self, '_page'):
            return self._page
        self._page = self.wiki.fetch(self.path)
        return self._page

    @property
    def data(self):
        if hasattr(self, '_data'):
            return self._data
        self._data = self.wiki.fetch(self.path + '/Data')
        return self._data

    @property
    def stats(self):
        if hasattr(self, '_stats'):
            return self._stats
        data  = self.data
        start = data.find('{{Character')
        end   = data.find('\n}}', start)
        stats = (s.split('=') for s in data[start:end].split('|')[1:])
        self._stats = {k.strip(): v.strip() for k, v in stats}
        return self._stats

    @property
    def framedata(self):
        if hasattr(self, '_framedata'):
            return self._framedata
        self._framedata = {}
        data = (x for x in mw.parse(self.data).filter_templates() if x.name.startswith("FrameData"))
        for code in data:
            hitbox = {param.name.strip(): param.value.strip() for param in code.params}
            if hitbox.get('images'):
                hitbox['images'] = BASEURL + 'Special:Redirect/file/' + hitbox['images']
            if hitbox['attack'] not in self._framedata:
                self._framedata[hitbox['attack']] = {hitbox['name']: hitbox}
            else:
                self._framedata[hitbox['attack']][hitbox['name']] = hitbox
        return self._framedata

    @property
    def skins(self):
        if hasattr(self, '_skins'):
            return self._skins
        page = mw.parse(self.page)
        head = next(page.ifilter_headings(matches=lambda node: node.title.strip() == 'Cosmetics'))
        self._skins = {}
        # ASSUMPTION: Page ordered as
        # Heading
        # (Optional) skin description
        # - with {{ShopRarity}}, otherwise assumed common
        # Table
        # - th: palette name
        # - tr.td: palette image
        # - tr.td: palette unlock text
        for node in page.nodes[page.index(head) + 1:]:
            match type(node):
                case mw.nodes.heading.Heading:
                    if node.level == head.level:
                        break
                    skin = node.title.strip()
                    description = []
                    rarity = None
                case str() | mw.nodes.Text:
                    if node := node.strip():
                        description.append(node)
                case mw.nodes.Template:
                    # unreachable
                    if node.name == 'ShopRarity':
                        rarity = Rarity.from_template(node)
                        description.append(str(rarity))
                case mw.nodes.Tag:
                    if node.tag == 'table':
                        # Assumption: th name, tr.td image, tr.td unlock criteria
                        palettes = (SkinPalette(self.wiki, *col) for col in table_by_columns(node))
                        if len(description):
                            description = ' '.join(description)
                        else:
                            description = None
                        self._skins[skin] = Skin({palette.name: palette for palette in palettes},
                                        description=description, rarity=rarity)
        return self._skins

def characterlist(wiki=Wiki()):
    text = wiki.fetch('Project:ROA2_Character_Select')
    pages = (char.group(1) for char in re.finditer(r'page=([^ |]*)', text))
    return {page.rsplit('/', 1)[1]: Character(wiki, page) for page in pages}

class Emote:
    def __init__(self, wiki, row):
        match row:
            case name, rarity, text, unlock, filename:
                self.unlock = unlock.contents.strip()
            case name, rarity, text, filename:
                self.unlock='Unknown'
        self.wiki = wiki
        self.name = name.contents.strip().title()
        self.rarity = Rarity.from_template(rarity.contents.nodes[0])
        self.text   = text.contents.strip()
        self.filename = filename.contents.nodes[0]

    def url(self):
        return BASEURL + 'Special:Redirect/file/' + self.filename.title.removeprefix('File:')

def emotelist(wiki=Wiki()):
    tables = mw.parse(wiki.fetch('RoA2/Emotes')).ifilter_tags(matches=lambda node: node.tag == 'table')
    tables = (table.contents.ifilter_tags(matches=lambda node: node.tag == 'tr') for table in tables)
    rows   = (row.contents.ifilter_tags(matches=lambda node: node.tag in ('td', 'th')) for row in itertools.chain(*tables))
    emotes = {}
    for row in rows:
        row = [*row]
        try:
            emote = Emote(wiki, row)
            emotes[f'{emote.name.title()} "{emote.text}"'] = emote
        except Exception as e:
            logging.info(f'Failed for row {row}')
    return emotes

if __name__ == '__main__':
    import json
    with Wiki() as wiki:
        char = Character(wiki, 'RoA2/Loxodont')
        char.page
        print(len(char.framedata))

