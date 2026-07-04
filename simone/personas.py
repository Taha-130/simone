"""
Les personas de Simone : chacun est une CONTRAINTE TECHNIQUE objective, pas une
imitation de l'expérience vécue.
- aveugle  : ne perçoit QUE l'arbre d'accessibilité (jamais le rendu visuel).
- moteur   : n'agit QUE sur les éléments atteignables au clavier (Tab/Entrée).
- cognitif : dispose d'un "budget de confusion" ; chaque friction (jargon,
             libellés vagues, trop d'options identiques) le consomme ; à zéro,
             il abandonne — comme un utilisateur qui ferme l'onglet.
"""
from dataclasses import dataclass


@dataclass
class Persona:
    key: str
    display: str
    description: str
    max_steps: int = 12
    confusion_budget: float | None = None  # persona cognitif uniquement


PERSONAS = {
    "aveugle": Persona(
        key="aveugle", display="Simone — persona aveugle (lecteur d'écran)",
        description=("Tu ne perçois JAMAIS le rendu visuel. Tu ne connais de la page que "
                     "l'arbre d'accessibilité fourni (rôles + noms). Si un élément n'y "
                     "figure pas, il n'existe pas pour toi.")),
    "moteur": Persona(
        key="moteur", display="Simone — persona moteur (clavier seul)",
        description=("Tu ne peux pas utiliser de souris. Tu n'agis que sur les éléments "
                     "atteignables à la touche Tab, activés par Entrée.")),
    "cognitif": Persona(
        key="cognitif", display="Simone — persona cognitif (charge mentale limitée)",
        description=("Tu as une tolérance limitée à la complexité. Jargon technique, "
                     "libellés vagues ('cliquez ici', 'Suite', 'Procéder'), messages "
                     "d'erreur sans explication et listes d'options identiques te "
                     "coûtent de la patience. Budget épuisé = tu abandonnes."),
        confusion_budget=10.0),
}

# Frictions cognitives détectables automatiquement (heuristiques v1, à calibrer
# ensuite avec ergothérapeutes et utilisateurs réels — à assumer tel quel au jury)
JARGON = ["iban", "rib", "psp", "cryptogramme", "cvv2", "cvc2", "transactionnel", "réf."]
VAGUE = ["cliquez ici", "suite", "procéder", "découvrir", "en savoir plus", "ok"]


def cognitive_cost(page_state, chosen_name: str) -> tuple[float, list[str]]:
    """Retourne (coût, raisons) pour une étape du persona cognitif."""
    cost, reasons = 0.0, []
    text = page_state.raw_text.lower()
    names = [n.name.lower() for n in page_state.nodes if n.name]

    hits = [j for j in JARGON if j in text]
    if hits:
        cost += 1.5 * len(hits)
        reasons.append(f"jargon incompréhensible ({', '.join(hits[:4])})")
    dupes = len([x for x in set(names) if names.count(x) > 2 and x])
    if dupes:
        cost += 2.0
        reasons.append("plusieurs liens/boutons portent exactement le même nom")
    if chosen_name.lower() in VAGUE or not chosen_name:
        cost += 2.0
        reasons.append(f"libellé vague : « {chosen_name or 'sans nom'} » — où cela mène-t-il ?")
    if "erreur" in text and "car" not in text and "parce" not in text:
        cost += 1.5
        reasons.append("message d'erreur sans explication ni solution")
    return cost, reasons
