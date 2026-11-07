"""Readable text for external calendar HTML; never used for write-back."""
import re
from html.parser import HTMLParser


class _DescriptionText(HTMLParser):
    blocks = {'p', 'div', 'li', 'ul', 'ol', 'tr', 'h1', 'h2', 'h3', 'h4', 'blockquote'}
    ignored = {'script', 'style', 'iframe', 'object', 'template'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in self.ignored:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag in {'ul', 'ol', 'li'}:
            if self.parts and not self.parts[-1].endswith('\n'):
                self.parts.append('\n')
        elif tag == 'br' or tag in self.blocks:
            self.parts.append('\n')
        if tag == 'li':
            self.parts.append('• ')
        if tag == 'td':
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if self.hidden:
            if tag in self.hidden:
                self.hidden = self.hidden[:self.hidden.index(tag)]
            return
        if tag in {'ul', 'ol', 'li'}:
            if self.parts and not self.parts[-1].endswith('\n'):
                self.parts.append('\n')
        elif tag in self.blocks:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def readable_google_description(description):
    """Remove markup while retaining line breaks, list items and decoded text.

    The result must still be assigned with textContent, never innerHTML. Decoded
    entities can themselves contain literal angle brackets.
    """
    parser = _DescriptionText()
    parser.feed(description or '')
    parser.close()
    text = ''.join(parser.parts).replace('\r\n', '\n').replace('\r', '\n')
    text = '\n'.join(re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.split('\n'))
    return re.sub(r'\n{3,}', '\n\n', text).strip()
