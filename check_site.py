"""Contrôles sans dépendance externe pour le site Coach OLOU."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).parent
PUBLIC = ROOT / "dist"
EXPECTED = {
    "index.html",
    "a-propos.html",
    "services.html",
    "conferences.html",
    "realisations.html",
    "ressources.html",
    "contact.html",
    "404.html",
    "style.css",
    "site.js",
    "robots.txt",
    "assets/euloge-olou.png",
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: list[str] = []
        self.lang: str | None = None
        self.has_main = False
        self.has_css = False
        self.has_js = False
        self.has_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.lang = values.get("lang")
        if "id" in values and values["id"]:
            self.ids.append(values["id"])
        if tag == "main" and values.get("id") == "main":
            self.has_main = True
        if tag == "link" and values.get("href") == "style.css":
            self.has_css = True
        if tag == "script" and values.get("src") == "site.js":
            self.has_js = True
        if tag == "form":
            self.has_form = True
        for attribute in ("href", "src"):
            target = values.get(attribute)
            if target:
                self.links.append(target)


def local_target(source: Path, value: str) -> Path | None:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("#"):
        return None
    target = parsed.path or source.name
    return (source.parent / target).resolve()


def main() -> int:
    errors: list[str] = []
    actual = {
        path.relative_to(PUBLIC).as_posix()
        for path in PUBLIC.rglob("*")
        if path.is_file() and not path.name.startswith(".") and path.name != "_headers"
    }
    missing = sorted(EXPECTED - actual)
    if missing:
        errors.append(f"Fichiers manquants : {', '.join(missing)}")

    for page in sorted(PUBLIC.glob("*.html")):
        parser = PageParser()
        parser.feed(page.read_text(encoding="utf-8"))
        if parser.lang != "fr":
            errors.append(f"{page.name}: langue HTML absente ou incorrecte")
        if not parser.has_main:
            errors.append(f"{page.name}: élément main#main absent")
        if not parser.has_css:
            errors.append(f"{page.name}: style.css absent")
        if not parser.has_js:
            errors.append(f"{page.name}: site.js absent")
        if len(parser.ids) != len(set(parser.ids)):
            errors.append(f"{page.name}: identifiant HTML dupliqué")
        for value in parser.links:
            target = local_target(page, value)
            if target is not None and not target.is_file():
                errors.append(f"{page.name}: lien local introuvable -> {value}")

    contact = PUBLIC / "contact.html"
    if contact.is_file():
        contact_text = contact.read_text(encoding="utf-8")
        for required in ('name="name"', 'name="email"', 'name="message"', 'id="contactform"'):
            if required not in contact_text:
                errors.append(f"contact.html: élément requis absent -> {required}")

    if errors:
        print("ÉCHEC")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK : {len(list(PUBLIC.glob('*.html')))} pages HTML et leurs ressources sont cohérentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
