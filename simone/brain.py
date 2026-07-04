"""
Le « cerveau » de Simone : décide de la prochaine action et produit le monologue.
Deux implémentations :
 - LLMBrain  : Claude via l'API Anthropic (mode hackathon, nécessite ANTHROPIC_API_KEY)
 - MockBrain : politique heuristique déterministe (tests, démo de secours sans réseau)
L'interface est identique -> on peut basculer en un flag.
"""
import json
import os
import re
import time


class Decision(dict):
    """{action: click|fill|give_up, index: int, value: str, monologue: str}"""


ILLISIBLE = Decision(action="give_up", index=-1, value="",
                     monologue="Je n'arrive plus à raisonner sur cette page.",
                     reason_if_give_up="réponse LLM illisible")


RATE_LIMIT_HINTS = ("429", "rate limit", "resource_exhausted", "quota", "resourceexhausted")


def _call_with_retry(fn, retries: int = 3, delay: float = 1.5) -> str | None:
    """Exécute fn() (un appel API) avec retries sur erreurs transitoires. Les quotas
    gratuits (Gemini notamment) sont mesurés PAR MINUTE : un simple retry de
    quelques secondes ne suffit pas à laisser le quota se régénérer, donc on
    attend nettement plus longtemps quand l'erreur ressemble à un rate-limit."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            is_rate_limit = any(h in msg for h in RATE_LIMIT_HINTS)
            if attempt == retries:
                print(f"[simone] appel LLM échoué après {retries + 1} tentatives ({e})")
                return None
            wait = 20.0 if is_rate_limit else delay * (attempt + 1)
            print(f"[simone] appel LLM en erreur ({'rate-limit' if is_rate_limit else 'réseau'}), "
                 f"retry dans {wait:.0f}s ({e})")
            time.sleep(wait)
    return None


SYSTEM_TMPL = """Tu es Simone, un agent qui teste l'accessibilité d'un site web.
{persona_description}

OBJECTIF UTILISATEUR : {goal}

À chaque tour tu reçois l'état de la page (les seuls éléments que tu perçois).
Réponds UNIQUEMENT en JSON compact :
{{"monologue": "ce que tu ressens/cherches, à la 1re personne, 1-2 phrases, concret",
  "action": "click" | "fill" | "give_up",
  "index": <numéro de l'élément choisi ou -1>,
  "value": "<texte à saisir si fill, sinon vide>",
  "reason_if_give_up": "<pourquoi tu abandonnes>"}}
Règles : si aucun élément perceptible ne permet d'avancer vers l'objectif, tu
cherches encore 1 à 2 tours puis tu abandonnes en expliquant précisément ce qui
manque. Ton monologue doit être exploitable dans un rapport (précis, factuel).
IMPORTANT : "give_up" est réservé au cas où AUCUN élément perceptible ne permet
objectivement d'avancer. Ta fatigue/patience/budget n'est PAS de ton ressort :
elle est calculée par le système en dehors de ce que tu vois. Tant qu'une option
concrète existe pour progresser vers l'objectif, choisis-la — n'abandonne jamais
par lassitude simulée.
Un lien qui pointe vers une simple ancre sur la même page (ex: "#boutique") ne
te fait PAS progresser vers l'objectif s'il ne t'amène à rien de nouveau : si tu
l'as déjà essayé sans effet, choisis autre chose plutôt que de le recliquer.

EXEMPLE : si tu perçois "[0] link \"Boutique\"" et "[1] button \"Ajouter le
Casque Audio X au panier\"" et que ton objectif est d'acheter ce casque, la
bonne réponse est :
{{"monologue": "Je vois le bouton pour ajouter le Casque Audio X, exactement ce que je cherche.", "action": "click", "index": 1, "value": "", "reason_if_give_up": ""}}
"index" est TOUJOURS un nombre entier (jamais entre guillemets)."""


class LLMBrain:
    """Claude via l'API Anthropic — payant dès la première requête."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        import anthropic
        self.client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY
        self.model = model

    def decide(self, persona, goal, page_state, history) -> Decision:
        hist = "\n".join(f"- {h}" for h in history[-6:]) or "(début du parcours)"
        msg = f"HISTORIQUE :\n{hist}\n\n{page_state.describe_for_llm()}"

        def call():
            resp = self.client.messages.create(
                model=self.model, max_tokens=400,
                system=SYSTEM_TMPL.format(persona_description=persona.description, goal=goal),
                messages=[{"role": "user", "content": msg}])
            return resp.content[0].text

        raw = _call_with_retry(call)
        if raw is None:
            return Decision(action="give_up", index=-1, value="",
                            monologue="Je n'arrive plus à raisonner sur cette page.",
                            reason_if_give_up="API Claude indisponible (réseau/rate-limit)")
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return Decision(json.loads(m.group(0)))
        except Exception:
            return ILLISIBLE


class GeminiBrain:
    """Gemini via l'API Google (google-genai) — niveau gratuit disponible sur
    https://aistudio.google.com/apikey (clé perso, quotas limités mais sans CB)."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        from google import genai
        self.client = genai.Client()  # lit GEMINI_API_KEY (ou GOOGLE_API_KEY)
        self.model = model

    def decide(self, persona, goal, page_state, history) -> Decision:
        hist = "\n".join(f"- {h}" for h in history[-6:]) or "(début du parcours)"
        msg = f"HISTORIQUE :\n{hist}\n\n{page_state.describe_for_llm()}"
        system = SYSTEM_TMPL.format(persona_description=persona.description, goal=goal)

        def call():
            resp = self.client.models.generate_content(
                model=self.model, contents=msg,
                config={"system_instruction": system})
            return resp.text or ""

        raw = _call_with_retry(call)
        if raw is None:
            return Decision(action="give_up", index=-1, value="",
                            monologue="Je n'arrive plus à raisonner sur cette page.",
                            reason_if_give_up="API Gemini indisponible (réseau/rate-limit)")
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return Decision(json.loads(m.group(0)))
        except Exception:
            return ILLISIBLE


class OpenAIBrain:
    """ChatGPT via l'API OpenAI — payant dès la première requête (clé perso)."""

    def __init__(self, model: str = "gpt-4o-mini"):
        import openai
        self.client = openai.OpenAI()  # lit OPENAI_API_KEY
        self.model = model

    def decide(self, persona, goal, page_state, history) -> Decision:
        hist = "\n".join(f"- {h}" for h in history[-6:]) or "(début du parcours)"
        msg = f"HISTORIQUE :\n{hist}\n\n{page_state.describe_for_llm()}"
        system = SYSTEM_TMPL.format(persona_description=persona.description, goal=goal)

        def call():
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system},
                         {"role": "user", "content": msg}])
            return resp.choices[0].message.content or ""

        raw = _call_with_retry(call)
        if raw is None:
            return Decision(action="give_up", index=-1, value="",
                            monologue="Je n'arrive plus à raisonner sur cette page.",
                            reason_if_give_up="API OpenAI indisponible (réseau/rate-limit)")
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return Decision(json.loads(m.group(0)))
        except Exception:
            return ILLISIBLE


class OllamaBrain:
    """LLM local via Ollama (https://ollama.com) — gratuit ET illimité : tourne sur
    ta machine, aucune clé API, aucun quota, fonctionne même sans internet une fois
    le modèle téléchargé. Prérequis : `ollama serve` lancé + modèle déjà tiré
    (`ollama pull llama3.2`). Plus lent et moins fin qu'un modèle cloud."""

    def __init__(self, model: str = "llama3.2"):
        import ollama
        self.client = ollama.Client()  # http://localhost:11434 par défaut
        self.model = model

    def decide(self, persona, goal, page_state, history) -> Decision:
        hist = "\n".join(f"- {h}" for h in history[-6:]) or "(début du parcours)"
        msg = f"HISTORIQUE :\n{hist}\n\n{page_state.describe_for_llm()}"
        system = SYSTEM_TMPL.format(persona_description=persona.description, goal=goal)

        def call():
            resp = self.client.chat(model=self.model, messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": msg},
            ], options={"temperature": 0.2, "repeat_penalty": 1.3})
            return resp["message"]["content"]

        raw = _call_with_retry(call, retries=1, delay=2.0)
        if raw is None:
            return Decision(action="give_up", index=-1, value="",
                            monologue="Je n'arrive plus à raisonner sur cette page.",
                            reason_if_give_up="Ollama indisponible (serveur lancé ? modèle téléchargé ?)")
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return Decision(json.loads(m.group(0)))
        except Exception:
            return ILLISIBLE


class MockBrain:
    """Politique déterministe : cherche des éléments dont le nom matche l'objectif.
    Suffisante pour la démo de secours ; le LLM fait bien mieux sur cas réels."""

    STEP_KEYWORDS = [  # progression type d'un achat
        (["casque", "panier", "ajouter", "boutique"], "trouver le produit et l'ajouter au panier"),
        (["panier", "paiement", "commander", "passer"], "accéder au paiement"),
        (["valider", "commande", "payer", "confirmer"], "valider la commande"),
    ]

    def decide(self, persona, goal, page_state, history) -> Decision:
        stage = min(sum(1 for h in history if "PAGE->" in h), len(self.STEP_KEYWORDS) - 1)
        keywords, intent = self.STEP_KEYWORDS[stage]

        # Remplir les champs identifiés avant de valider (persona sait taper)
        for i, n in enumerate(page_state.nodes):
            if n.role == "textbox" and n.name and f"fill:{n.node_id}" not in history:
                return Decision(action="fill", index=i, value="TEST",
                                monologue=f"Je remplis le champ « {n.name} ».")

        best, best_score = -1, 0
        for i, n in enumerate(page_state.nodes):
            if n.role not in ("link", "button"):
                continue
            if persona.key == "moteur" and not n.focusable:
                continue
            score = sum(1 for k in keywords if k in n.name.lower())
            if score > best_score:
                best, best_score = i, score

        if best >= 0:
            n = page_state.nodes[best]
            return Decision(action="click", index=best, value="",
                            monologue=f"Je veux {intent} — je trouve {n.label()}, j'y vais.")

        # Rien de perceptible qui matche : décrire ce que Simone "voit" vraiment
        named = [n for n in page_state.nodes if n.name]
        vague = sum(1 for n in page_state.nodes if n.name.lower() in
                    ("cliquez ici", "en savoir plus", "suite", "découvrir"))
        if len(history) < 2:
            desc = (f"Je perçois {len(page_state.nodes)} éléments dont {len(named)} nommés"
                    + (f", {vague} s'appellent juste « cliquez ici » ou équivalent" if vague else "")
                    + f". Rien qui ressemble à « {' / '.join(keywords[:2])} ». Je continue à chercher.")
            return Decision(action="click", index=-1, value="", monologue=desc)
        reason = (f"aucun élément perceptible ne permet de {intent}. "
                  f"Sur cette page je ne perçois que : "
                  + "; ".join(n.label() for n in page_state.nodes[:8]))
        return Decision(action="give_up", index=-1, value="",
                        monologue=f"J'abandonne : {reason}", reason_if_give_up=reason)


def get_brain(provider: str = "auto", model: str | None = None):
    """provider : 'auto' | 'claude' | 'gemini' | 'openai' | 'ollama' | 'mock'.
    model : surcharge le modèle par défaut (utile pour changer de quota gratuit
    Gemini : chaque modèle a son propre compteur de requêtes/jour)."""
    if provider == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider = "claude"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            provider = "gemini"
        else:
            provider = "mock"
    if provider == "claude":
        try:
            return LLMBrain(**({"model": model} if model else {}))
        except Exception as e:
            print(f"[simone] Claude indisponible ({e}) -> MockBrain")
    elif provider == "gemini":
        try:
            return GeminiBrain(**({"model": model} if model else {}))
        except Exception as e:
            print(f"[simone] Gemini indisponible ({e}) -> MockBrain")
    elif provider == "openai":
        try:
            return OpenAIBrain(**({"model": model} if model else {}))
        except Exception as e:
            print(f"[simone] OpenAI indisponible ({e}) -> MockBrain")
    elif provider == "ollama":
        try:
            return OllamaBrain(**({"model": model} if model else {}))
        except Exception as e:
            print(f"[simone] Ollama indisponible ({e}) -> MockBrain")
    return MockBrain()
