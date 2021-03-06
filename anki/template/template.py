import re
import cgi
import collections
from anki.utils import stripHTML

clozeReg = r"\{\{c%s::(.*?)(::(.*?))?\}\}"


modifiers = {}
def modifier(symbol):
    """Decorator for associating a function with a Mustache tag modifier.

    @modifier('P')
    def render_tongue(self, tag_name=None, context=None):
        return ":P %s" % tag_name

    {{P yo }} => :P yo
    """
    def set_modifier(func):
        modifiers[symbol] = func
        return func
    return set_modifier


def get_or_attr(obj, name, default=None):
    try:
        return obj[name]
    except KeyError:
        return default
    except:
        try:
            return getattr(obj, name)
        except AttributeError:
            return default


class Template(object):
    # The regular expression used to find a #section
    section_re = None

    # The regular expression used to find a tag.
    tag_re = None

    # Opening tag delimiter
    otag = '{{'

    # Closing tag delimiter
    ctag = '}}'

    def __init__(self, template, context=None):
        self.template = template
        self.context = context or {}
        self.compile_regexps()

    def render(self, template=None, context=None, encoding=None):
        """Turns a Mustache template into something wonderful."""
        template = template or self.template
        context = context or self.context

        template = self.render_sections(template, context)
        result = self.render_tags(template, context)
        if encoding is not None:
            result = result.encode(encoding)
        return result

    def compile_regexps(self):
        """Compiles our section and tag regular expressions."""
        tags = { 'otag': re.escape(self.otag), 'ctag': re.escape(self.ctag) }

        section = r"%(otag)s[\#|^]([^\}]*)%(ctag)s(.+?)%(otag)s/\1%(ctag)s"
        self.section_re = re.compile(section % tags, re.M|re.S)

        tag = r"%(otag)s(#|=|&|!|>|\{)?(.+?)\1?%(ctag)s+"
        self.tag_re = re.compile(tag % tags)

    def render_sections(self, template, context):
        """Expands sections."""
        while 1:
            match = self.section_re.search(template)
            if match is None:
                break

            section, section_name, inner = match.group(0, 1, 2)
            section_name = section_name.strip()

            # check for cloze
            m = re.match("c[qa]:(\d+):(.+)", section_name)
            if m:
                # get full field text
                txt = get_or_attr(context, m.group(2), None)
                m = re.search(clozeReg%m.group(1), txt)
                if m:
                    it = m.group(1)
                else:
                    it = None
            else:
                it = get_or_attr(context, section_name, None)

            replacer = ''
            # if it and isinstance(it, collections.Callable):
            #     replacer = it(inner)
            if it and not hasattr(it, '__iter__'):
                if section[2] != '^':
                    replacer = inner
            elif it and hasattr(it, 'keys') and hasattr(it, '__getitem__'):
                if section[2] != '^':
                    replacer = self.render(inner, it)
            elif it:
                insides = []
                for item in it:
                    insides.append(self.render(inner, item))
                replacer = ''.join(insides)
            elif not it and section[2] == '^':
                replacer = inner

            template = template.replace(section, replacer)

        return template

    def render_tags(self, template, context):
        """Renders all the tags in a template for a context."""
        while 1:
            match = self.tag_re.search(template)
            if match is None:
                break

            tag, tag_type, tag_name = match.group(0, 1, 2)
            tag_name = tag_name.strip()
            try:
                func = modifiers[tag_type]
                replacement = func(self, tag_name, context)
                template = template.replace(tag, replacement)
            except SyntaxError:
                return u"{{invalid template}}"

        return template

    @modifier('{')
    def render_tag(self, tag_name, context):
        """Given a tag name and context, finds, escapes, and renders the tag."""
        raw = get_or_attr(context, tag_name, '')
        if not raw and raw is not 0:
            return ''
        return re.sub("^<span.+?>(.*)</span>", "\\1", raw)

    @modifier('!')
    def render_comment(self, tag_name=None, context=None):
        """Rendering a comment always returns nothing."""
        return ''

    @modifier(None)
    def render_unescaped(self, tag_name=None, context=None):
        """Render a tag without escaping it."""
        if tag_name.startswith("text:"):
            tag = tag_name[5:]
            txt = get_or_attr(context, tag)
            if txt:
                return stripHTML(txt)
            return ""
        elif (tag_name.startswith("cq:") or
              tag_name.startswith("ca:") or
              tag_name.startswith("cactx:")):
            m = re.match("c(.+):(\d+):(.+)", tag_name)
            (type, ord, tag) = (m.group(1), m.group(2), m.group(3))
            txt = get_or_attr(context, tag)
            if txt:
                return self.clozeText(txt, ord, type)
            return ""
        return get_or_attr(context, tag_name, '{unknown field %s}' % tag_name)

    def clozeText(self, txt, ord, type):
        reg = clozeReg
        m = re.search(reg%ord, txt)
        if not m:
            # cloze doesn't exist; return empty
            return ""
        # replace chosen cloze with type
        if type == "q":
            if m.group(2):
                txt = re.sub(reg%ord, "<span class=cloze>[...(\\3)]</span>", txt)
            else:
                txt = re.sub(reg%ord, "<span class=cloze>[...]</span>", txt)
        elif type == "actx":
            txt = re.sub(reg%ord, "<span class=cloze>\\1</span>", txt)
        else:
            # just the answers
            ans = re.findall(reg%ord, txt)
            ans = ["<span class=cloze>"+a[0]+"</span>" for a in ans]
            ans = ", ".join(ans)
            # but we want to preserve the outer field styling
            return re.sub("(^<span.+?>)(.*)</span>", "\\1"+ans+"</span>", txt)
        # and display other clozes normally
        return re.sub(reg%".*?", "\\1", txt)

    @modifier('=')
    def render_delimiter(self, tag_name=None, context=None):
        """Changes the Mustache delimiter."""
        self.otag, self.ctag = tag_name.split(' ')
        self.compile_regexps()
        return ''
