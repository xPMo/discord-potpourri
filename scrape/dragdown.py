#!python
import re
import requests
from bs4 import BeautifulSoup

class Wiki:
    def __init__(self, baseurl='https://dragdown.wiki/wiki/'):
        self.baseurl = baseurl
        self.session = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.__exit__(*args)

    def fetch(self, path):
        return self.session.get(self.baseurl + path, params={'action': 'raw'}).content.decode()

class Character:

    def __init__(self, wiki, path):
        self.wiki = wiki
        self.path = path

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
        start = self.data.find('{{Character')
        end   = self.data.find('\n}}', start)
        stats = (s.split('=') for s in self.data[start:end].split('|')[1:])
        self._stats = {k.strip(): v.strip() for k, v in stats}
        return self._stats

    @property
    def soup(self):
        if hasattr(self, '_soup'):
            return self._soup
        request = self.wiki.session.get(self.wiki.baseurl + self.path)
        self._soup = BeautifulSoup(request.content, features='html.parser')
        return self._soup

    @property
    def skins(self):
        #TODO: Can we extract this from self.page?
        # Seems unlikely, since it only has the source images, not the locations of the thumbnails
        if hasattr(self, '_skins'):
            return self._skins
        soup = self.soup
        self._skins = {}
        header = soup.find('span', {'id': 'Cosmetics'}).parent
        for obj in header.next_siblings:
            if obj.name == header.name:
                break
            for obj in obj.find_all(['h2', 'h3', 'h4', 'p', 'table']):
                match obj.name:
                    case 'h2' | 'h3' | 'h4':
                        skin = obj.get_text(strip=True)
                        self._skins[skin] = {}
                    case 'p':
                            self._skins[skin]['description'] = obj.get_text().strip()
                    case 'table':
                        palettes = {}
                        names, links, unlocks, *_ = obj.find_all('tr')
                        for n, l, u in zip(names.find_all('th'), links.find_all('td'), unlocks.find_all('td')):
                            palettes[n.get_text(strip=True)] = (
                                    l.a.get('href'),
                                    l.img.get('src'),
                                    u.get_text(strip=True)
                            )
                        self._skins[skin]['palettes'] = palettes
        return self._skins

    def get_palette(self, skin, palette='Default'):
        full, thumb, unlock = self.skins[skin]['palettes'][palette]
        return self.wiki.baseurl + full, 'https:' + thumb, unlock, self.skins[skin].get('description')

    def framedata(self):
        pass

def characterlist(wiki=Wiki()):
    text = wiki.fetch('Project:ROA2_Character_Select')
    pages = (char.group(1) for char in re.finditer(r'page=([^ |]*)', text))
    return {page.rsplit('/', 1)[1]: Character(wiki, page) for page in pages}

if __name__ == '__main__':
    import json
    with Wiki() as wiki:
        text = wiki.fetch('Project:ROA2_Character_Select')
        char = Character(wiki, 'RoA2/Loxodont')
        print(len(char.stats))
        print(json.dumps(char.stats, indent=4))

