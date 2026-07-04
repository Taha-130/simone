"""
Extraction de l'« arbre d'accessibilité » — ce que reçoit réellement un lecteur d'écran.
Deux drivers interchangeables :
  - PlaywrightDriver : le vrai navigateur (à utiliser au hackathon).
  - StaticDriver     : simulateur sans navigateur (tests / secours), parse le HTML
                       et approxime les règles de calcul du nom accessible.
Un élément SANS nom accessible et SANS role interactif n'apparaît pas dans l'arbre :
c'est exactement pour ça que Simone (persona aveugle) ne "voit" pas un <div onclick>.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re

INTERACTIVE_ROLES = {"button", "link", "textbox", "checkbox", "radio", "combobox", "searchbox"}

# Libellés usuels des boutons de bandeaux cookies/consentement (FR + EN) : on les
# ferme au mieux avant de laisser l'agent percevoir la page, sinon ils bloquent
# systématiquement le persona dès la première étape sur la plupart des sites réels.
COOKIE_BUTTON_PATTERNS = [
    r"tout accepter", r"accepter tous les cookies", r"accepter et fermer",
    r"^accepter$", r"j'accepte", r"accepter les cookies",
    r"accept all", r"accept all cookies", r"^accept$", r"i agree",
    r"got it", r"agree and close",
]


@dataclass
class A11yNode:
    role: str
    name: str
    node_id: str            # identifiant interne pour agir dessus
    focusable: bool = True  # atteignable au clavier (Tab)
    meta: dict = field(default_factory=dict)

    def label(self) -> str:
        return f'{self.role} "{self.name}"' if self.name else f"{self.role} (sans nom)"


@dataclass
class PageState:
    url: str
    title: str
    nodes: list             # list[A11yNode] — l'arbre aplati, ordre du DOM
    raw_text: str = ""      # texte visible (pour le persona cognitif)

    MAX_NODES_FOR_LLM = 60  # borne le coût/tour sur les pages très denses (méga-menus...)

    def describe_for_llm(self) -> str:
        lines = [f"PAGE: {self.title} ({self.url})", "ÉLÉMENTS PERÇUS PAR LE LECTEUR D'ÉCRAN :"]
        if not self.nodes:
            lines.append("  (aucun élément interactif perceptible)")
        shown = self.nodes[:self.MAX_NODES_FOR_LLM]
        for i, n in enumerate(shown):
            focus = "" if n.focusable else " [NON atteignable au clavier]"
            lines.append(f"  [{i}] {n.label()}{focus}")
        if len(self.nodes) > self.MAX_NODES_FOR_LLM:
            lines.append(f"  … + {len(self.nodes) - self.MAX_NODES_FOR_LLM} autres éléments "
                        f"non affichés ici (page très dense)")
        return "\n".join(lines)


# ----------------------------------------------------------------------------
# Driver 1 : Playwright (le vrai) — à utiliser au hackathon
# ----------------------------------------------------------------------------
class PlaywrightDriver:
    """Nécessite : pip install playwright && python -m playwright install chromium"""

    def __init__(self, headless: bool = True):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self.page = self._browser.new_page()
        self._nodes_cache = []

    def goto(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass  # sites avec polling/tracking continu (Amazon...) n'idlent jamais
        self._dismiss_cookie_banner()
        self.page.wait_for_timeout(400)  # laisse le temps au contenu chargé en JS (SPA) d'apparaître

    def _dismiss_cookie_banner(self):
        """Best-effort : ferme un bandeau cookies/consentement s'il en détecte un."""
        import re as _re
        for pattern in COOKIE_BUTTON_PATTERNS:
            try:
                btn = self.page.get_by_role("button", name=_re.compile(pattern, _re.I)).first
                if btn.is_visible(timeout=800):
                    btn.click(timeout=800)
                    self.page.wait_for_timeout(200)
                    return
            except Exception:
                continue

    _ARIA_LINE = re.compile(r'^\s*-\s+([a-zA-Z]+)(?:\s+"([^"]*)")?(.*)$')

    def snapshot(self) -> PageState:
        """L'arbre d'accessibilité natif de Chromium : la vérité du lecteur d'écran.
        (page.accessibility a été retiré de Playwright -> on utilise aria_snapshot(),
        son remplaçant officiel, et on le parse.)"""
        yaml_tree = self.page.locator("body").aria_snapshot()
        nodes, counter = [], [0]
        for line in yaml_tree.splitlines():
            m = self._ARIA_LINE.match(line)
            if not m:
                continue
            role, name, extra = m.group(1), (m.group(2) or "").strip(), m.group(3) or ""
            if role not in INTERACTIVE_ROLES:
                continue
            nid = f"pw-{counter[0]}"; counter[0] += 1
            nodes.append(A11yNode(role=role, name=name, node_id=nid,
                                  focusable="[disabled]" not in extra,
                                  meta={"pw_name": name, "pw_role": role}))
        self._nodes_cache = nodes
        text = self.page.inner_text("body")[:4000]
        return PageState(url=self.page.url, title=self.page.title(), nodes=nodes, raw_text=text)

    def act(self, node: A11yNode, action: str, value: str = "") -> bool:
        """Agit via les sélecteurs de rôle ARIA — comme le ferait une techno d'assistance."""
        try:
            loc = self.page.get_by_role(node.meta["pw_role"], name=node.meta["pw_name"]).first
            if action == "click":
                loc.click(timeout=3000)
            elif action == "fill":
                loc.fill(value, timeout=3000)
            elif action == "press_enter":
                loc.press("Enter", timeout=3000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # l'action a réussi même si la page ne devient jamais idle
            return True
        except Exception:
            return False

    def keyboard_reachable(self):
        """Persona moteur : parmi les nœuds de la dernière snapshot, ceux réellement
        atteignables au Tab (tabindex >= 0, ni désactivé ni masqué). Renvoie les
        mêmes A11yNode que snapshot() (node_id compatibles), pas un relevé DOM à part."""
        reachable = []
        for n in self._nodes_cache:
            try:
                loc = self.page.get_by_role(n.meta["pw_role"], name=n.meta["pw_name"]).first
                ok = loc.evaluate("el => el.tabIndex >= 0 && !el.disabled && el.offsetParent !== null")
                if ok:
                    reachable.append(n)
            except Exception:
                continue
        return reachable

    def close(self):
        self._browser.close(); self._pw.stop()


# ----------------------------------------------------------------------------
# Driver 2 : simulateur statique (tests sans navigateur, plan B de démo)
# Approxime les règles du nom accessible (texte du bouton, label associé,
# alt d'image, aria-label). Un <div onclick> n'a NI role NI nom -> invisible.
# ----------------------------------------------------------------------------
class StaticDriver:
    def __init__(self, root: str):
        self.root = Path(root)
        self.url = ""
        self._html = ""
        self._doc_title = ""

    def goto(self, url: str):
        self.url = url
        p = self.root / url if not url.startswith("/") else Path(url)
        self._html = p.read_text(encoding="utf-8")
        m = re.search(r"<title>(.*?)</title>", self._html, re.S)
        self._doc_title = m.group(1).strip() if m else url

    def snapshot(self) -> PageState:
        html = re.sub(r"<!--.*?-->", "", self._html, flags=re.S)
        nodes, nid = [], [0]

        def add(role, name, focusable=True, **meta):
            nodes.append(A11yNode(role=role, name=re.sub(r"\s+", " ", name).strip(),
                                  node_id=f"st-{nid[0]}", focusable=focusable, meta=meta))
            nid[0] += 1

        # <a href> -> link ; nom = texte OU alt de l'image contenue (sinon vide)
        for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', html, re.S):
            attrs, inner = m.group(1), m.group(2)
            href = (re.search(r'href="([^"]*)"', attrs) or [None, ""])[1]
            name = re.sub(r"<[^>]+>", "", inner)
            if not name.strip():
                alt = re.search(r'alt="([^"]*)"', inner)
                name = alt.group(1) if alt else ""
            add("link", name, href=href)

        # <button> -> button ; nom = texte
        for m in re.finditer(r'<button\b([^>]*)>(.*?)</button>', html, re.S):
            onclick = (re.search(r'onclick="([^"]*)"', m.group(1)) or [None, ""])[1]
            add("button", re.sub(r"<[^>]+>", "", m.group(2)), onclick=onclick)

        # <input> -> textbox ; nom = <label for=id> associé, sinon RIEN
        # (un <span> adjacent n'est PAS un label : c'est le défaut classique)
        labels = {m.group(1): re.sub(r"<[^>]+>", "", m.group(2)).strip()
                  for m in re.finditer(r'<label\b[^>]*for="([^"]+)"[^>]*>(.*?)</label>', html, re.S)}
        for m in re.finditer(r'<input\b([^>]*)>', html):
            iid = (re.search(r'id="([^"]*)"', m.group(1)) or [None, ""])[1]
            add("textbox", labels.get(iid, ""), input_id=iid)

        # NB : les <div onclick> ne génèrent AUCUN nœud -> invisibles, comme en vrai.
        text = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return PageState(url=self.url, title=self._doc_title, nodes=nodes,
                         raw_text=re.sub(r"\s+", " ", text)[:4000])

    def act(self, node: A11yNode, action: str, value: str = "") -> bool:
        if action == "click" or action == "press_enter":
            target = node.meta.get("href") or ""
            onclick = node.meta.get("onclick", "")
            m = re.search(r"location\.href='([^']+)'", onclick)
            if m:
                target = m.group(1)
            if target and not target.startswith("#"):
                self.goto(target); return True
            if "document.title" in onclick:  # succès final simulé
                self._doc_title = re.search(r"document\.title='([^']+)'", onclick).group(1)
                return True
            return bool(target)  # ancre interne : "clic" sans navigation
        if action == "fill":
            return True
        return False

    def keyboard_reachable(self):
        return [n for n in self.snapshot().nodes if n.focusable]

    def close(self):
        pass
