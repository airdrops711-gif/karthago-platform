"""Extract the translatable strings of the project into ``.po`` files.

The build box of the platform has no GNU gettext tools (``xgettext``
and ``msgfmt`` are not installed and the container runs unprivileged),
so the extraction is done with Django's own machinery:

* the templates are walked with ``django.template.base.Lexer``, so
  ``{% trans %}``, ``{% translate %}`` and ``{% blocktrans %}`` are
  found exactly where Django finds them, and the msgids are built the
  same way Django builds them (the ``%(name)s`` placeholders, the
  ``trimmed`` option, the plural forms);
* the Python sources are walked with the ``ast`` module, so
  ``gettext()``, ``gettext_lazy()``, ``ugettext*()`` and
  ``ngettext()`` are found;
* the catalogues are written and compiled with ``polib``, which handles
  the ``.po``/``.mo`` formats without the C tools.

The French catalogue is the source language: its ``msgid`` is the
French string. The Arabic catalogue carries the translation.
"""
import ast
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template.base import Lexer, TokenType
from django.utils.text import smart_split, unescape_string_literal
from django.utils.translation import get_language_info
from django.utils.translation import trim_whitespace

try:
    import polib
except ImportError:  # pragma: no cover - the dependency is declared
    raise CommandError("polib is required: pip install polib")


#: The Python functions that mark a translatable string.
GETTEXT_FUNCTIONS = {
    "_",
    "gettext",
    "gettext_lazy",
    "ugettext",
    "ugettext_lazy",
    "ngettext",
    "ngettext_lazy",
    "ungettext",
    "ungettext_lazy",
    "pgettext",
    "pgettext_lazy",
    "npgettext",
    "npgettext_lazy",
}

#: The plural rules of the supported languages.
#:
#: Django's own language information does not carry them, but the
#: catalogues do need them: without the right ``Plural-Forms`` header
#: the Arabic catalogue falls back to the two-forms rule of English.
PLURAL_FORMS = {
    "ar": (
        "nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : "
        "n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5;"
    ),
    "fr": "nplurals=2; plural=(n > 1);",
}

#: Directories never walked for translatable strings.
SKIP_DIRS = {
    ".git",
    "venv",
    "staticfiles",
    "node_modules",
    "__pycache__",
    "locale",
    "media",
    "static",
}


class StringOccurrence:
    """One translatable string, with the places where it appears."""

    def __init__(self, msgid, context="", plural=""):
        self.msgid = msgid
        self.context = context
        self.plural = plural
        self.locations = []
        self.comments = []

    @property
    def key(self):
        return (self.context, self.msgid)

    def add_location(self, filename, lineno):
        location = f"{filename}:{lineno}"
        if location not in self.locations:
            self.locations.append(location)

    def add_comment(self, comment):
        if comment and comment not in self.comments:
            self.comments.append(comment)


class StringCollector:
    """Collects the translatable strings of the whole project."""

    def __init__(self):
        self.strings = {}

    def add(self, msgid, location=None, comment=None, context="", plural=""):
        if not msgid or not msgid.strip():
            return
        occurrence = self.strings.get((context, msgid))
        if occurrence is None:
            occurrence = StringOccurrence(msgid, context, plural)
            self.strings[(context, msgid)] = occurrence
        elif plural and not occurrence.plural:
            occurrence.plural = plural
        if location:
            occurrence.add_location(*location)
        occurrence.add_comment(comment)

    # -- templates ------------------------------------------------------
    def scan_template_file(self, name, source, collector):
        """Extract the translatable strings of one template source.

        The Django lexer is used, so the msgids are built exactly the
        way Django builds them at render time.
        """
        try:
            tokens = Lexer(source).tokenize()
        except Exception:
            return

        index = 0
        tokens = list(tokens)
        while index < len(tokens):
            token = tokens[index]
            if token.token_type != TokenType.BLOCK:
                index += 1
                continue

            bits = token.contents.split()
            command = bits[0] if bits else ""

            if command in ("trans", "translate"):
                self._scan_trans(name, token, collector)
                index += 1
                continue

            if command in ("blocktrans", "blocktranslate"):
                index = self._scan_blocktrans(name, tokens, index, collector)
                continue

            index += 1

    def _scan_trans(self, name, token, collector):
        """Extract the string of a ``{% trans %}`` / ``{% translate %}``."""
        bits = list(smart_split(token.contents))
        if len(bits) < 2:
            return

        literal = self._literal(bits[1])
        if literal is None:
            return

        context = ""
        for index, bit in enumerate(bits):
            if bit == "context" and index + 1 < len(bits):
                context = self._literal(bits[index + 1]) or ""
                break

        collector.add(literal, (name, token.lineno), context=context)

    @staticmethod
    def _literal(bit):
        """Return the unquoted value of a string literal.

        Django reads the literals of the template tags with
        ``unescape_string_literal``, so the extractor does the same:
        a quote escaped with a backslash is a quote, not the end of the
        string.
        """
        if not bit or bit[0] not in "\"'":
            return None
        try:
            return unescape_string_literal(bit)
        except ValueError:
            return None

    def _scan_blocktrans(self, name, tokens, index, collector):
        """Extract the strings of a ``{% blocktrans %}`` block.

        The singular and the plural are rebuilt the way Django does it:
        the text nodes are concatenated, the variables become
        ``%(name)s`` placeholders and the ``trimmed`` option collapses
        the whitespace.
        """
        token = tokens[index]
        bits = list(smart_split(token.contents))
        trimmed = "trimmed" in bits
        context = ""
        for position, bit in enumerate(bits):
            if bit == "context" and position + 1 < len(bits):
                context = self._literal(bits[position + 1]) or ""
                break

        # Walk the tokens until the end of the block, splitting on the
        # {% plural %} tag.
        singular_parts = []
        plural_parts = []
        current = singular_parts
        index += 1

        while index < len(tokens):
            inner = tokens[index]
            if inner.token_type == TokenType.BLOCK:
                command = inner.contents.split()[0] if inner.contents.split() else ""
                if command in ("endblocktrans", "endblocktranslate"):
                    index += 1
                    break
                if command == "plural":
                    current = plural_parts
                    index += 1
                    continue
            current.append(inner)
            index += 1

        singular = self._render_block(singular_parts, trimmed)
        if singular:
            collector.add(singular, (name, token.lineno), context=context)

        if plural_parts:
            plural = self._render_block(plural_parts, trimmed)
            if plural:
                # The plural shares the msgid of the singular: Django
                # stores it in the "Plural-Forms" field of the entry.
                key = (context, singular)
                occurrence = collector.strings.get(key)
                if occurrence is not None:
                    occurrence.plural = plural

        return index

    @staticmethod
    def _render_block(parts, trimmed):
        """Rebuild the msgid of a blocktrans body."""
        message = ""
        for part in parts:
            if part.token_type == TokenType.TEXT:
                message += part.contents.replace("%", "%%")
            elif part.token_type == TokenType.VAR:
                message += "%%(%s)s" % part.contents
        if trimmed:
            message = trim_whitespace(message)
        return message.replace("%%", "%")

    def scan_template_files(self, collector):
        """Scan every template of the project."""
        for root in self.template_dirs:
            root_path = Path(root)
            if not root_path.exists():
                continue
            for path in sorted(root_path.rglob("*.html")):
                relative = path.relative_to(root_path).as_posix()
                source = path.read_text(encoding="utf-8")
                self.scan_template_file(relative, source, collector)

    # -- python ---------------------------------------------------------
    def scan_python(self, path, relative, collector):
        """Extract the translatable strings of a Python file."""
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            else:
                continue
            if name not in GETTEXT_FUNCTIONS:
                continue

            if not node.args:
                continue
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(
                first.value, str
            ):
                continue

            msgid = first.value
            context = ""
            plural = ""

            if name.startswith("pgettext") and len(node.args) > 1:
                ctx_node = node.args[1]
                if isinstance(ctx_node, ast.Constant):
                    context = ctx_node.value
            elif name.startswith("n") and len(node.args) > 1:
                plural_node = node.args[1]
                if isinstance(plural_node, ast.Constant) and isinstance(
                    plural_node.value, str
                ):
                    plural = plural_node.value

            collector.add(
                msgid, (relative, node.lineno), context=context, plural=plural
            )


class Command(BaseCommand):
    help = (
        "Extract the translatable strings of the project into the .po "
        "catalogues and compile them into .mo files (no gettext tools "
        "required)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--locale",
            action="append",
            dest="locales",
            help="Locale to update (default: every locale of LANGUAGES).",
        )
        parser.add_argument(
            "--no-compile",
            action="store_true",
            help="Only write the .po files, do not compile them.",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        locale_dir = base_dir / "locale"

        collector = StringCollector()
        collector.template_dirs = [base_dir / "templates"]

        # 1. The templates.
        collector.scan_template_files(collector)

        # 2. The Python sources.
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = Path(root) / filename
                relative = path.relative_to(base_dir).as_posix()
                collector.scan_python(path, relative, collector)

        locales = options.get("locales") or [
            code for code, _name in settings.LANGUAGES
        ]

        for code in locales:
            self._write_catalog(
                locale_dir, code, collector, compile_it=not options["no_compile"]
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Extracted {len(collector.strings)} strings for "
                f"{len(locales)} locale(s)."
            )
        )

    def _write_catalog(self, locale_dir, code, collector, compile_it=True):
        """Write (and compile) the catalogue of one locale."""
        try:
            info = get_language_info(code)
        except KeyError:
            raise CommandError(f"Unknown language code: {code}")

        directory = locale_dir / code / "LC_MESSAGES"
        directory.mkdir(parents=True, exist_ok=True)
        po_path = directory / "django.po"
        mo_path = directory / "django.mo"

        catalog = polib.pofile(str(po_path)) if po_path.exists() else polib.POFile()

        # Index the existing entries, so a translation already written
        # by hand survives an extraction.
        existing = {}
        for entry in catalog:
            existing[(entry.msgctxt or "", entry.msgid)] = entry

        for (context, msgid), occurrence in collector.strings.items():
            key = (context, msgid)
            entry = existing.get(key)
            if entry is None:
                entry = polib.POEntry(
                    msgid=msgid,
                    msgctxt=context or None,
                    msgstr="",
                )
                catalog.append(entry)
            entry.occurrences = [
                (location.rsplit(":", 1)[0], location.rsplit(":", 1)[1])
                for location in occurrence.locations
            ]
            if occurrence.plural:
                entry.msgid_plural = occurrence.plural
            if occurrence.comments and not entry.comment:
                entry.comment = "\n".join(occurrence.comments)

        # The entries that disappeared from the code are flagged as
        # obsolete rather than deleted: a translation may be needed
        # again after a rollback.
        for entry in catalog:
            if (entry.msgctxt or "", entry.msgid) not in collector.strings:
                entry.obsolete = True

        catalog.metadata = {
            "Project-Id-Version": "Karthago Commerce",
            "Report-Msgid-Bugs-To": "",
            "POT-Creation-Date": "",
            "PO-Revision-Date": "",
            "Last-Translator": "Karthago",
            "Language-Team": "Karthago",
            "Language": info.get("name", code),
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
            "Plural-Forms": PLURAL_FORMS.get(
                code, "nplurals=2; plural=(n != 1);"
            ),
        }
        for key, value in list(catalog.metadata.items()):
            if not value:
                catalog.metadata.pop(key, None)

        catalog.save(str(po_path))
        self.stdout.write(
            f"  {po_path.relative_to(settings.BASE_DIR)}: {len(catalog)} entries"
        )

        if compile_it:
            catalog.save_as_mofile(str(mo_path))
            self.stdout.write(f"  {mo_path.relative_to(settings.BASE_DIR)}: compiled")
