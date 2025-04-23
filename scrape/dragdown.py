#!python
import requests
from bs4 import BeautifulSoup

DOMAIN = 'https://dragdown.wiki'

class Character:

    def __init__(self, url):
        self.url = url

    @property
    def soup(self):
        if hasattr(self, '_soup'):
            return self._soup
        with requests.Session() as s:
            request = s.get(DOMAIN + self.url)
            self._soup = BeautifulSoup(request.content, features='html.parser')
            return self._soup

    @property
    def skins(self):
        if hasattr(self, '_skins'):
            return self._skins
        soup = self.soup
        self._skins = {}
        header = soup.find('span', {'id': 'Cosmetics'}).parent
        for obj in header.next_siblings:
            match obj.name:
                case header.name:
                    break
                case 'h2' | 'h3' | 'h4':
                    skin = obj.get_text(strip=True)
                case 'table':
                    palettes = {}
                    names, links, unlocks, *_ = obj.find_all('tr')
                    for n, l, u in zip(names.find_all('th'), links.find_all('td'), unlocks.find_all('td')):
                        palettes[n.get_text(strip=True)] = (
                                l.a.get('href'),
                                l.img.get('src'),
                                u.get_text(strip=True)
                        )
                    self._skins[skin] = palettes
        return self._skins

def characterlist():
    with requests.Session() as s:
        request = s.get(DOMAIN + '/wiki/Dragdown:ROA2_Character_Select?action=edit')
        soup = BeautifulSoup(request.content, features='html.parser')
        textarea = soup.find('textarea')
        text = textarea.contents[0]
        return {word.rsplit('/', 1)[1]: Character(word.replace('page=','/wiki/'))
                for word in  text.split() if word.startswith('page=')}

if __name__ == '__main__':
    pass
