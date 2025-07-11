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
    def __init__(self, user_agent=None):
        self.session = requests.Session()
        if user_agent:
            self.session.headers.update({'User-Agent': user_agent})
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
    def glossary(self):
        if hasattr(self, '_glossary'):
            return self._glossary
        self._glossary = {}
        wikitext = mw.parse(self.fetch('RoA2/Glossary').content.decode())
        for node in wikitext.ifilter_templates(matches=lambda node: node.name == 'GlossaryData-ROA2'):
            # Skip if there's no term or summary
            try:
                term = node.get('term').value.strip()
                summary = nodes_to_text(node.get('summary').value.nodes, pagetitle='RoA2/Glossary', suppress_links=True).strip()
            except:
                logging.warning(f'Badly-formatted glossary entry {node.strip()}')
                continue

            aliases = []
            links = []
            if node.has('alias'):
                aliases = [alias.strip() for alias in node.get('alias').value.split(',')]
            if node.has('altLink'):
                links = [nodes_to_text([link], pagetitle='RoA2/Glossary', suppress_links=True)
                         for link in node.get('altLink').value.ifilter(
                            matches=lambda node: type(node) in [mw.nodes.Wikilink, mw.nodes.ExternalLink]
                         )]
            display = None
            if node.has('display'):
                display = node.get('display').value.strip().replace(' ', '_')
                display = BASEURL + 'Special:Redirect/file/' + display

            obj = GlossaryTerm(term, summary, aliases, links, display)
            self._glossary[term] = obj
            for alias in aliases:
                self._glossary[alias] = obj
        return self._glossary

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

class GlossaryTerm(collections.namedtuple('GlossaryTerm', ['term', 'summary', 'aliases', 'links', 'display'])):
    def url(self):
        return BASEURL + 'RoA2/Glossary#' + self.term.replace(' ', '_')

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
        match name:
            case None:
                self.name = ''
            case mw.nodes.Tag:
                self.name = name.contents.strip()
            case _:
                self.name = name.strip()
        if hasattr(image, 'contents'):
            self.imagelink = next(image.contents.ifilter_wikilinks(), None)
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
        return 'SkinPalette({!r}, {!r}, {!r})'.format(
                self.name, self.imagelink, self.unlock)

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
    def add_topic(topics, heading, parts, url=None, **kwargs):
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

    for pagetitle, code in pages.items():
        nodes = collections.deque(code.nodes)
        description = []
        parts = description
        heading = SparseList()
        heading[0] = pagetitle
        # TODO:
        # [ ] dynamically resolve templates
        while nodes:
            node = nodes.popleft()

            match node:
                case mw.nodes.Heading():
                    level = node.level
                    if level < 3:
                        # stash last topic
                        add_topic(topics, heading, parts)
                        # start new topic once text is resolved
                        heading = SparseList(heading[:node.level])
                        parts.append(None)
                        push([finish_heading(level)])
                        push(node.title.nodes)
                        continue
                case mw.nodes.Template():
                    match node.name.strip():
                        case 'TheoryBox':
                            add_topic(topics, heading, parts)
                            url = BASEURL + pagetitle + '#' + heading[-1]
                            heading.append(node.get('Title').value.strip())
                            caption = node.get('Oneliner').value.strip()
                            node.remove('Title')
                            node.remove('Oneliner')
                            params = node.params
                            subs = [subnode for param in node.params for subnode in param.value.nodes]
                            # When we finish with the TheoryBox, move to the next
                            nodes.appendleft(lambda: (add_topic(topics, heading, parts, url=url, caption=caption), heading.pop()))
                            push(subs)
                            continue
            resolve_node_generic(node, nodes, parts)

        add_topic(topics, heading, parts)
    return topics

def nodes_to_text(nodes, pagetitle=None, suppress_links=False):
    """This is the general purpose function for converting nodes into text.

    If a function must do something special like extract a table,
    copy the body of this function and insert your case *before* the resolve_node_generic call.

    See build_topics or Character.skins for implementations of this idea.
    """
    nodes = collections.deque(nodes)
    parts = []
    while nodes:
        resolve_node_generic(nodes.popleft(), nodes, parts, pagetitle=pagetitle, suppress_links=suppress_links)
    return ''.join(parts)

def resolve_node_generic(node, nodes: collections.deque, parts: list, pagetitle=None, suppress_links=False):
    """
    Generic code for resolving a single node.
    Pushes to :nodes:, and builds the resulting markdown-ish string on :parts:
    Put this in a loop while the deque of nodes is non-empty

    Pass :pagetitle: to resolve #heading links correctly
    """
    def push(new):
        nodes.extendleft(reversed(new))
    def finish_link(link):
        def finish():
            text = []
            part = parts.pop()
            while part is not None:
                text.append(part)
                part = parts.pop()
            text = ''.join(reversed(text))
            text = re.sub(r'(?=[\]\\])', r'\\', text)
            if suppress_links:
                parts.append(f'[{text}](<{link}>)')
            else:
                parts.append(f'[{text}]({link})')
        return finish
    match node:
        case mw.nodes.Heading():
            parts.append('\n' + '#' * node.level + ' ')
            push(['\n'])
            push(node.title.nodes)

        case mw.nodes.Template():
            match node.name.strip():
                # TODO: custom handling for various templates
                case 'Notation':
                    name = node.params[0].value.strip()
                    parts.append({
                        #'Attack': '🟢 Attack',
                        #'Grab': '🟣 Grab',
                        #'Jump': '🔵 Jump',
                        #'Special': '🔴 Special',
                        #'Strong': '🟠 Strong',
                        #'Shield': '⚪ Shield',
                        #'Parry': '⚪ Parry',
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
                case 'RoA2_FTilt_Arrows':
                    parts.append('🢀 / 🢂')
                case 'RoA2_DTilt_Arrow':
                    parts.append('🢃')

                case 'clr' | 'clrr':
                    push(node.params[1].value.nodes)

                case 'StockIcon':
                    parts.append(None)
                    try:
                        link = BASEURL + node.params.get('LinkOverride').value.strip()
                    except:
                        link = BASEURL + node.params[0].value.strip() + '/' + node.params[1].value.strip()
                    push([finish_link(re.sub(r'(?=[\(\)\\])', r'\\', link.replace(' ', '_')))])
                    try:
                        push(node.params.get('Label').value.nodes)
                    except:
                        push(node.params[1].value.nodes)
                case 'term' | 'Term':
                    parts.append(None)
                    link = BASEURL + node.params[0].value.strip() + 'Glossary#' + node.params[1].value.strip()
                    push([finish_link(re.sub(r'(?=[\(\)\\])', r'\\', link.replace(' ', '_')))])
                    try:
                        push(node.params[2].value.nodes)
                    except:
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
                case 'ROA2 Move Card':
                    # TODO: use context to embed move details
                    parts.append('\n')
                    push(node.get('description').value.nodes)

                case _:
                    # default behavior for templates:
                    # ignore template name, push all params[].nodes[] onto the stack
                    if DEBUGGING:
                        parts.append('{' + str(node.name) + '}')
                    params = node.params
                    subs = [subnode for param in node.params for subnode in param.value.nodes]
                    push(subs)

        case str():
            parts.append(node)

        case mw.nodes.Text():
            # append text
            if part := node.value.rstrip('\n'):
                parts.append(re.sub(r'(?=[_\(\)\[\]\\*])', r'\\', part))
        case mw.nodes.Wikilink():
            title = node.title.strip()
            if title.startswith('File:'):
                link = BASEURL + 'Special:Redirect/file/' + title.removeprefix('File:')
                if node.text and node.text.nodes and  '|' in node.text.nodes[0]:
                    node.text.nodes.pop(0)
            elif title.startswith('#') and pagetitle:
                link = BASEURL + pagetitle + title
            else:
                link = BASEURL + title
            if not node.text or not node.text.strip():
                push(node.title.nodes)
            else:
                parts.append(None)
                push([finish_link(re.sub(r'(?=[\(\)\\])', r'\\', link.replace(' ', '_')))])
                push(node.text.nodes)

        case mw.nodes.external_link.ExternalLink():
            if node.title:
                link = node.url.strip()
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

        case _ if callable(node):
            node()

        case _:
            pass

class Character:

    def __init__(self, wiki, path):
        self.wiki = wiki
        self.path = path
        self.url  = BASEURL + path
        self.icon_url = BASEURL + 'Special:Redirect/file/' + '_'.join(path.split('/')) + '_Stock.png'
        self.image_url = BASEURL + 'Special:Redirect/file/' + '_'.join(path.split('/')) + '_Portrait.png'

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
        data = mw.parse(self.data).ifilter_templates(matches=lambda node: node.name.startswith("FrameData"))
        for code in data:
            hitbox = {}
            for param in code.params:
                name  = param.name.strip()
                if name == 'images':
                    hitbox['images'] = [BASEURL + 'Special:Redirect/file/' + x.strip() for x in str(param.value).split('\\')]
                    continue
                hitbox[param.name.strip()] = nodes_to_text(param.value.nodes).strip()

            if 'caption' in hitbox:
                hitbox['caption'] = [x.strip() for x in re.split(r'\s\\\\\s', hitbox['caption'])]

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
        nodes = collections.deque(page.nodes[page.index(head) + 1:])
        description = []
        while nodes:
            node = nodes.popleft()
            match node:
                case mw.nodes.heading.Heading():
                    if node.level == head.level:
                        break
                    skin = node.title.strip()
                    description = []
                    rarity = None
                    continue
                case mw.nodes.Template():
                    if node.name == 'ShopRarity':
                        rarity = Rarity.from_template(node)
                case mw.nodes.Tag():
                    if node.tag == 'table':
                        # Assumption: th name, tr.td image, tr.td unlock criteria
                        palettes = (SkinPalette(*col) for col in table_by_columns(node))
                        if len(description):
                            description = ''.join(description)
                        else:
                            description = None
                        self._skins[skin] = Skin({palette.name: palette for palette in palettes},
                                        description=description, rarity=rarity)
                        continue
            resolve_node_generic(node, nodes, description)
        return self._skins

def characterlist(wiki=Wiki()):
    text = wiki.fetch('Project:ROA2_Character_Select').content.decode()
    names = (char.group(1) for char in re.finditer(r'character=([^ |]*)', text))
    return {name: Character(wiki, 'RoA2/' + name) for name in names}

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

