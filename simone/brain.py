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


class Decision(dict):
    """{action: click|fill|give_up, index: int, value: str, monologue: str}"""


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
manque. Ton monologue doit être exploitable dans un rapport (précis, factuel)."""


class LLMBrain:
    """Claude via l'API Anthropic — payant dès la première requête."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        import anthropic
        self.client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY
        self.model = model

    def decide(self, persona, goal, page_state, history) -> Decision:
        hist = "\n".join(f"- {h}" for h in history[-6:]) or "(début du parcours)"
        msg = f"HISTORIQUE :\n{hist}\n\n{page_state.describe_for_llm()}"
        resp = self.client.messages.create(
            model=self.model, max_tokens=400,
            system=SYSTEM_TMPL.format(persona_description=persona.description, goal=goal),
            messages=[{"role": "user", "content": msg}])
        raw = resp.content[0].text
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return Decision(json.loads(m.group(0)))
        except Exception:
            return Decision(action="give_up", index=-1, value="",
                            monologue="Je n'arrive plus à raisonner sur cette page.",
                            reason_if_give_up="réponse LLM illisible")


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
        resp = self.client.models.generate_content(
            model=self.model, contents=msg,
            config={"system_instruction": system})
        raw = resp.text or ""
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return Decision(json.loads(m.group(0)))
        except Exception:
            return Decision(action="give_up", index=-1, value="",
                            monologue="Je n'arrive plus à raisonner sur cette page.",
                            reason_if_give_up="réponse LLM illisible")


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


def get_brain(provider: str = "auto"):
    """provider : 'auto' | 'claude' | 'gemini' | 'mock'."""
    if provider == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider = "claude"
        elif os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            provider = "gemini"
        else:
            provider = "mock"
    if provider == "claude":
        try:
            return LLMBrain()
        except Exception as e:
            print(f"[simone] Claude indisponible ({e}) -> MockBrain")
    elif provider == "gemini":
        try:
            return GeminiBrain()
        except Exception as e:
            print(f"[simone] Gemini indisponible ({e}) -> MockBrain")
    return MockBrain()
