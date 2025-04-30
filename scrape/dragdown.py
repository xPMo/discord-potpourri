#!python
import collections
import enum
import re
import itertools
import logging
import requests
import mwparserfromhell as mw

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

DEBUGGING = True
BASEURL = 'https://dragdown.wiki/wiki/'

class SparseList(list):
    def __setitem__(self, index, value):
        missing = index - len(self) + 1
        if missing > 0:
            self.extend([None] * missing)
        list.__setitem__(self, index, value)

    def __getitem__(self, index):
        try: return list.__getitem__(self, index)
        except IndexError: return None

class Wiki:
    def __init__(self):
        self.session = requests.Session()
        self._templates = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.__exit__(*args)

    def fetch(self, path):
        return self.session.get(BASEURL + path, params={'action': 'raw'})

    def get_template(self, path):
        if path in self._templates:
            return self._templates[path]
        request = self.fetch('Template:' + path)
        if not request.ok:
            return None
        page = mw.parse(request.content.decode())
        try:
            self._templates[path] = next(page.ifilter_tags(matches=lambda node: node.tag == 'includeonly')).contents
        except StopIteration:
            self._templates[path] = page
        return self._templates[path]

    @property
    def general_pages(self):
        if hasattr(self, '_general_pages'):
            return self._general_pages
        self._general_pages = {}
        subs = (card.get('page').value.strip() for card in self.get_template('RoA2_SysMech_Navigation').ifilter_templates(matches=lambda node: node.name == 'PageNavCard'))
        for sub in subs:
            if not sub:
                continue
            request = self.fetch(sub)
            if request.ok:
                self._general_pages[sub] = mw.parse(request.content.decode())
        return self._general_pages

    @property
    def topics(self):
        if hasattr(self, '_topics'):
            return self._topics
        self._topics = build_topics(self.general_pages)
        return self._topics

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
    def __init__(self, name, image, unlock):
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

class Topic:
    def __init__(self, title, url, body, caption=None, image=None):
        self.title = title
        self.url = url
        self.body = body
        self.caption = caption
        self.image = image

    def image_url(self):
        if self.image:
            return BASEURL + 'Special:Redirect/file/' + self.imagelink.title.removeprefix('File:')

def build_topics(pages):
    """
    Manual parsing.

    This is probably bad style, but it works. Use a stack of nodes, parsing headings and
    text directly, and pushing template/link subnodes back onto the stack.

    There are particular templates (like TheoryBox) which should become their own topic.
    We finish the last topic immediately, then push a function onto the stack first for
    cleanup/topic creation before pushing the template's subnodes.

    We *don't* want this to be recursive, because:
    - if a template generates a heading, it needs to affect all following nodes
    - we can only handle links which hold text
    """
    topics = {}
    def push(new):
        nodes.extendleft(reversed(new))
    def add_topic(heading, parts, url=None, **kwargs):
        if text := ''.join(parts).strip():
            name = [heading[0].rsplit('/', 1)[-1]] + heading[1:]
            name = ' > '.join([x.strip() for x in name if x]).replace('\\', '')
            if not url:
                url = BASEURL + heading[0] + '#' + heading[-1].strip().replace('\\', '')
            topics[name] = Topic(
                    name,
                    url.replace(' ', '_'),
                    text,
                    **kwargs
                    )
        parts.clear()

    def finish_heading(level):
        """
        The tail of parts contains our heading, pop things off until we encounter None

        There's *probably* only one item, but better safe than sorry!
        """
        def finish():
            this_heading = []
            part = parts.pop()
            while part is not None:
                this_heading.append(part)
                part = parts.pop()
            heading[level] = ''.join(reversed(this_heading))
        return finish

    for title, code in pages.items():
        nodes = collections.deque(code.nodes)
        parts = []
        heading = SparseList()
        heading[0] = title
        current_link = None
        # TODO:
        # [ ] dynamically resolve templates
        while nodes:
            node = nodes.popleft()
            match node:
                case str():
                    parts.append(node)
                case mw.nodes.Heading():
                    level = node.level
                    if level < 3:
                        # stash last topic
                        add_topic(heading, parts)
                        # start new topic once text is resolved
                        heading = SparseList(heading[:node.level])
                        parts.append(None)
                        push([finish_heading(level)])
                        push(node.title.nodes)
                    else:
                        parts.append('\n' + '#' * node.level + ' ')
                        push(['\n'])
                        push(node.title.nodes)
                case mw.nodes.Text():
                    # append text
                    if part := node.value.rstrip('\n'):
                        if current_link:
                            part = re.sub(r'(?=[\]\\])', r'\\', part)
                            current_link = re.sub(r'(?=[\(\)\\])', r'\\', current_link.replace(' ', '_'))
                            part.replace
                            parts.append(f'[{part}]({current_link})')
                            current_link = None
                        else:
                            parts.append(re.sub(r'(?=[-_\(\)\[\]\\*])', r'\\', part))
                case mw.nodes.Wikilink():
                    title = node.title.strip()
                    if title.startswith('File:'):
                        current_link = BASEURL + 'Special:Redirect/file/' + title.removeprefix('File:')
                        if node.text and node.text.nodes and  '|' in node.text.nodes[0]:
                            node.text.nodes.pop(0)
                    elif title.startswith('#'):
                        current_link = BASEURL + heading[0] + title
                    else:
                        current_link = BASEURL + title
                    if not node.text or not node.text.strip():
                        push(node.title.nodes)
                    else:
                        push(node.text.nodes)
                case mw.nodes.external_link.ExternalLink():
                    if node.title:
                        current_link = node.url.strip()
                        push(node.title.nodes)
                    else:
                        push(node.url.nodes)
                case mw.nodes.Tag():
                    match node.tag.strip():
                        case 'table':
                            pass
                        case 'br':
                            parts.append('\n')
                        case 'b':
                            parts.append('**')
                            nodes.appendleft('**')
                            push(node.contents.nodes)
                        case 'i':
                            parts.append('*')
                            nodes.appendleft('*')
                            push(node.contents.nodes)
                        case 'big' | 'dd':
                            parts.append('\n')
                            push(node.contents.nodes)
                        case 'li':
                            if len(parts) and parts[-1] == '\n- ':
                                parts[-1] = '\n  - '
                            else:
                                parts.append('\n- ')
                        case 'table':
                            pass
                        case _:
                            if DEBUGGING:
                                nodes.appendleft('>')
                                push(node.contents.nodes)
                                nodes.appendleft('|')
                                push(node.tag.nodes)
                                nodes.appendleft('<')
                case mw.nodes.Template():
                    match node.name.strip():
                        # TODO: custom handling for various templates
                        case 'Notation':
                            name = node.params[0].value.strip()
                            parts.append({
                                'Attack': '🟢 Attack',
                                'Grab': '🟣 Grab',
                                'Jump': '🔵 Jump',
                                'Special': '🔴 Special',
                                'Strong': '🟠 Strong',
                                'Shield': '⚪ Shield',
                                'Parry': '⚪ Parry',
                                'Left': '🢀',
                                'Up': '🢁',
                                'Right': '🢂',
                                'Down': '🢃',
                                'UpLeft': '🢄',
                                'UpRight': '🢅',
                                'DownRight': '🢆',
                                'DownLeft': '🢇',
                                'LeftTap': '🢀(Tap)',
                                'UpTap': '🢁(Tap)',
                                'RightTap': '🢂(Tap)',
                                'DownTap': '🢃(Tap)',
                             }.get(name) or name)
                        case 'clrr' | 'StockIcon':
                            push(node.params[1].value.nodes)
                        case 'tt':
                            nodes.appendleft(')')
                            push(node.params[1].value.nodes)
                            nodes.appendleft(' (')
                            push(node.params[0].value.nodes)
                        case 'special' | 'aerial' | 'strong' | 'grab' | 'tilt' | 'ShopRarity':
                            params = node.params
                            subs = [subnode for param in node.params for subnode in param.value.nodes]
                            push(subs)
                        case 'ROA2_DT':
                            parts.append(' *Deadzone Threshold*')
                        case 'TheoryBox':
                            add_topic(heading, parts)
                            url = BASEURL + heading[0] + '#' + heading[-1]
                            heading.append(node.get('Title').value.strip())
                            caption = node.get('Oneliner').value.strip()
                            node.remove('Title')
                            node.remove('Oneliner')
                            params = node.params
                            subs = [subnode for param in node.params for subnode in param.value.nodes]
                            # When we finish with the TheoryBox, move to the next
                            nodes.appendleft(lambda: (add_topic(heading, parts, url=url, caption=caption), heading.pop()))
                            push(subs)
                        case _:
                            # default behavior for templates:
                            # ignore template name, push all params[].nodes[] onto the stack
                            parts.append(f' :{node.name}: ')
                            params = node.params
                            subs = [subnode for param in node.params for subnode in param.value.nodes]
                            push(subs)
                case _ if callable(node):
                    node()
                case _:
                    pass
        add_topic(heading, parts)
    return topics

class Character:

    def __init__(self, wiki, path):
        self.wiki = wiki
        self.path = path
        self.url  = BASEURL + path
        self.icon_url = BASEURL + 'Special:Redirect/file/' + '_'.join(path.split('/')) + '_Stock.png'

    @property
    def page(self):
        if hasattr(self, '_page'):
            return self._page
        self._page = mw.parse(self.wiki.fetch(self.path).content.decode())
        return self._page

    """"
    Single flat dict, since completion works well
    """
    @property
    def topics(self):
        if hasattr(self, '_topics'):
            return self._topics
        self._topics = build_topics(self.pages)
        return self._topics

    @property
    def pages(self):
        if hasattr(self, '_pages'):
            return self._pages
        self._pages = {}
        subs = (x.title.removeprefix('{{{charMainPage}}}') for x in self.wiki.get_template('CharLinks').ifilter_wikilinks())
        for sub in subs:
            sub = self.path + sub
            if not sub:
                continue
            request = self.wiki.fetch(sub)
            if request.ok:
                self._pages[sub] = mw.parse(request.content.decode())
        return self._pages

    @property
    def data(self):
        if hasattr(self, '_data'):
            return self._data
        self._data = self.wiki.fetch(self.path + '/Data').content.decode()
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
        page = self.page
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
                        palettes = (SkinPalette(*col) for col in table_by_columns(node))
                        if len(description):
                            description = ' '.join(description)
                        else:
                            description = None
                        self._skins[skin] = Skin({palette.name: palette for palette in palettes},
                                        description=description, rarity=rarity)
        return self._skins

def characterlist(wiki=Wiki()):
    text = wiki.fetch('Project:ROA2_Character_Select').content.decode()
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
    tables = mw.parse(wiki.fetch('RoA2/Emotes').content.decode()).ifilter_tags(matches=lambda node: node.tag == 'table')
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
        char = Character(wiki, 'RoA2/Maypul')
        print(char.topics['Techniques - Wrap'])

