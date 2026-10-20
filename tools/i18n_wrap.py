#!/usr/bin/env python3
"""Wrap the hardcoded text of the Django templates in translation tags.

The tool walks the raw HTML of every template and turns the human
readable text nodes into ``{% trans %}`` (plain text) or
``{% blocktrans %}`` (text with variables) tags.

The rules are conservative on purpose — a broken template is much worse
than an untranslated string:

* the content of ``<script>``, ``<style>``, ``<textarea>`` and of the
  HTML comments is never touched;
* the ``{% verbatim %}`` blocks are never touched;
* the attributes are only translated for the few attributes that hold a
  user facing label (``placeholder``, ``title``, ``aria-label``,
  ``alt``) and only when the value holds no variable;
* a text node is translated only when it holds at least one letter, so
  the separators, the bullet points and the icons stay as they are.

The tool is idempotent: a template that is already wrapped is left
alone.
"""
import argparse
import re
import sys
from pathlib import Path

#: The attributes holding a user facing label.
TRANSLATABLE_ATTRIBUTES = ("placeholder", "title", "aria-label", "alt")

#: The elements whose content is never translatable.
RAW_ELEMENTS = ("script", "style", "textarea", "code", "pre")

#: The elements whose content is a single word and stays as it is.
VOID_ELEMENTS = (
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
)


def _find_tag_end(source, start):
    """Return the index just after the ``>`` of the tag starting at ``start``."""
    index = start
    quote = None
    while index < len(source):
        char = source[index]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == ">":
            return index + 1
        index += 1
    return len(source)


def _split_attributes(tag_body):
    """Split the body of a tag into its attributes.

    Returns a list of ``(name, value, quote)`` tuples; the value is
    ``None`` for a boolean attribute.
    """
    attributes = []
    index = 0
    length = len(tag_body)
    while index < length:
        while index < length and tag_body[index].isspace():
            index += 1
        if index >= length:
            break
        start = index
        while index < length and not tag_body[index].isspace() and tag_body[index] != "=":
            index += 1
        name = tag_body[start:index]
        if not name:
            index += 1
            continue
        # Look for the value.
        probe = index
        while probe < length and tag_body[probe].isspace():
            probe += 1
        if probe < length and tag_body[probe] == "=":
            probe += 1
            while probe < length and tag_body[probe].isspace():
                probe += 1
            if probe < length and tag_body[probe] in "\"'":
                quote = tag_body[probe]
                end = tag_body.find(quote, probe + 1)
                if end == -1:
                    value = tag_body[probe + 1:]
                    index = length
                else:
                    value = tag_body[probe + 1:end]
                    index = end + 1
            else:
                end = probe
                while end < length and not tag_body[end].isspace():
                    end += 1
                value = tag_body[probe:end]
                index = end
            attributes.append((name, value, quote))
        else:
            attributes.append((name, None, None))
            index = probe
    return attributes


def _escape_literal(text):
    """Escape a text for a single quoted template literal."""
    return text.replace("\\", "\\\\").replace("'", "\\'")


def _has_letter(text):
    return any(char.isalpha() for char in text)


def _is_already_wrapped(source):
    """True when the template already uses the translation tags."""
    return "{% trans" in source or "{% translate" in source


def wrap_source(source):
    """Return the template with its text nodes wrapped in trans tags."""
    output = []
    index = 0
    length = len(source)
    raw_depth = 0
    raw_tag = None

    while index < length:
        # 1. The HTML comments are copied as they are.
        if source.startswith("<!--", index):
            end = source.find("-->", index)
            end = length if end == -1 else end + 3
            output.append(source[index:end])
            index = end
            continue

        # 2. The Django tags are copied as they are, except the
        #    verbatim and comment blocks, whose content is left
        #    untouched: they are never rendered.
        if source.startswith("{%", index):
            end = source.find("%}", index)
            end = length if end == -1 else end + 2
            block = source[index:end]
            command = block[2:-2].strip().split(" ")[0] if len(block) > 4 else ""
            if command in ("verbatim", "comment") and not command.startswith("end"):
                # Copy the whole block as it is.
                close = source.find("{%% end%s %%}" % command, index)
                close = length if close == -1 else close + len(
                    "{%% end%s %%}" % command
                )
                output.append(source[index:close])
                index = close
                continue
            output.append(block)
            index = end
            continue

        # 3. The Django variables are copied as they are, but they are
        #    kept inside the text run so a sentence can be wrapped in a
        #    single blocktrans.
        if source.startswith("{{", index):
            end = source.find("}}", index)
            end = length if end == -1 else end + 2
            output.append(source[index:end])
            index = end
            continue

        # 4. The HTML tags are handled: the translatable attributes are
        #    wrapped, the raw elements switch the raw mode on.
        if source[index] == "<":
            end = _find_tag_end(source, index)
            tag = source[index:end]
            lowered = tag.lower()
            name_match = re.match(r"<\s*([a-zA-Z0-9-]+)", lowered)
            name = name_match.group(1) if name_match else ""

            if raw_depth:
                output.append(tag)
                if lowered.startswith(f"</{raw_tag}"):
                    raw_depth = 0
                    raw_tag = None
                index = end
                continue

            if name in RAW_ELEMENTS and not lowered.startswith(f"</"):
                output.append(tag)
                raw_depth = 1
                raw_tag = name
                index = end
                continue

            output.append(_wrap_tag(tag))
            index = end
            continue

        # 5. The text: it is collected until the next tag.
        end = index
        while end < length and source[end] not in "<{":
            end += 1
        if end == index:
            # A stray "{" or "%" that opens nothing: it is copied as
            # it is, and the scan always moves forward.
            output.append(source[index])
            index += 1
            continue
        text = source[index:end]
        if raw_depth:
            output.append(text)
        else:
            output.append(_wrap_text(text))
        index = end

    return "".join(output)


def _wrap_tag_with_django(name, body, tag):
    """Rebuild a tag whose body holds Django markup.

    The Django blocks are replaced by opaque placeholders, the
    attributes are processed as usual, then the placeholders are put
    back untouched.
    """
    placeholders = []

    def _hide(match):
        placeholders.append(match.group(0))
        return "@@django%d@@" % (len(placeholders) - 1)

    hidden = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", _hide, body, flags=re.DOTALL)

    rebuilt = _wrap_tag(f"<{name}{hidden}>", hide_marker="@@django")
    rebuilt = re.sub(r"@@django(\d+)@@", lambda m: placeholders[int(m.group(1))], rebuilt)
    return rebuilt


def _wrap_tag(tag, hide_marker=None):
    """Wrap the translatable attributes of an HTML tag.

    ``hide_marker`` is the prefix of the placeholders standing for the
    Django markup: an attribute holding one of them is left alone,
    because a Django tag cannot live inside a trans tag.
    """
    match = re.match(r"<\s*([a-zA-Z0-9-]+)(.*?)>$", tag, re.DOTALL)
    if not match:
        return tag
    name = match.group(1)
    body = match.group(2)
    if not body:
        return tag

    # A tag holding Django markup (``{% if %}`` inside an ``<option>``
    # for instance) is rebuilt part by part: the Django parts are
    # copied as they are, the HTML parts are processed.
    if "{%" in body:
        return _wrap_tag_with_django(name, body, tag)

    closing = body.rstrip()
    suffix = body[len(closing):]
    trailing_slash = ""
    if closing.endswith("/"):
        closing = closing[:-1]
        trailing_slash = "/"

    attributes = _split_attributes(closing)
    rebuilt = []
    for attribute_name, value, quote in attributes:
        lowered = attribute_name.lower()
        if (
            value
            and lowered in TRANSLATABLE_ATTRIBUTES
            and _has_letter(value)
            and "{{" not in value
            and "{%" not in value
            and "\n" not in value
            and not (hide_marker and hide_marker in value)
        ):
            rebuilt.append(
                f'{attribute_name}="{{% trans \'{_escape_literal(value)}\' %}}"'
            )
        elif value is None:
            rebuilt.append(attribute_name)
        else:
            mark = quote or '"'
            rebuilt.append(f"{attribute_name}={mark}{value}{mark}")

    return f"<{name} {' '.join(rebuilt)}{trailing_slash}{suffix}>"


def _wrap_text(text):
    """Wrap a text node in a trans tag.

    The surrounding whitespace is kept outside of the tag, so the
    layout of the page does not move when the string is translated.
    """
    if not text.strip():
        return text
    if not _has_letter(text):
        return text

    stripped = text.strip()
    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]

    # The text holds a variable: it becomes a blocktrans.
    if "{{" in stripped and "}}" in stripped:
        return "{%% blocktrans %%}%s{%% endblocktrans %%}" % stripped

    # The text is a single line: it becomes a trans tag.
    if "\n" not in stripped:
        return "%s{%% trans '%s' %%}%s" % (
            leading,
            _escape_literal(stripped),
            trailing,
        )

    # The text spans several lines: it becomes a trimmed blocktrans.
    return "%s{%% blocktrans trimmed %%}%s{%% endblocktrans %%}%s" % (
        leading,
        stripped,
        trailing,
    )


def _ensure_i18n_load(wrapped):
    """Make sure the template loads the ``i18n`` tag library.

    The tag is loaded at the top of the template, next to the other
    ``{% load %}`` statements, or on its own line when the template has
    none.
    """
    if "{% load" in wrapped:
        # The load tags are merged into the first one.
        def _merge(match):
            libraries = match.group(1)
            names = [part.strip() for part in re.split(r"[,\s]+", libraries) if part.strip()]
            if "i18n" not in names:
                names.append("i18n")
            # Django's ``{% load %}`` splits libraries on whitespace, not commas.
            return "{%% load %s %%}" % " ".join(names)

        return re.sub(r"\{%\s*load\s+([^%]*?)\s*%\}", _merge, wrapped, count=1)

    # No load tag at all: one is added after the ``{% extends %}`` tag,
    # because Django wants the extends to be the very first tag.
    extends = re.match(r"\s*\{%\s*extends\s+[^%]*?%\}", wrapped)
    if extends:
        cut = extends.end()
        return wrapped[:cut] + "\n{% load i18n %}" + wrapped[cut:]

    return "{% load i18n %}\n" + wrapped


def process_file(path, dry_run=False):
    """Wrap the text of one template. Returns True when it changed."""
    source = path.read_text(encoding="utf-8")
    wrapped = source
    if not _is_already_wrapped(source):
        wrapped = wrap_source(source)
    # The tag library is always checked, even on an already wrapped
    # template: a hand written one may miss it.
    with_load = _ensure_i18n_load(wrapped)
    if with_load == source:
        return False
    if not dry_run:
        path.write_text(with_load, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="templates")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    changed = []
    for path in sorted(root.rglob("*.html")):
        if process_file(path, args.dry_run):
            changed.append(path)
    print(f"{len(changed)} template(s) wrapped:")
    for path in changed:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
