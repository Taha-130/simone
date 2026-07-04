#!/usr/bin/env python3
"""
SIMONE — POC d'audit d'accessibilité par agents IA.
Usage :
  python run_audit.py --site demo_site/site_ko --static          # démo sans navigateur
  python run_audit.py --url https://exemple.com --goal "..."     # vrai site (Playwright)
Options : --llm force le cerveau Claude (sinon auto si ANTHROPIC_API_KEY présent)
"""
import argparse, sys, time
from pathlib import Path
from simone.agent import run_persona
from simone.brain import GeminiBrain, LLMBrain, OpenAIBrain, get_brain
from simone.report import render


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="dossier HTML local (mode --static) ")
    ap.add_argument("--url", help="URL de départ (mode Playwright)")
    ap.add_argument("--static", action="store_true", help="driver simulé sans navigateur")
    ap.add_argument("--goal", default="Acheter le Casque Audio X et finaliser la commande")
    ap.add_argument("--success-marker", default="commande confirmée",
                    help="texte/titre qui prouve le succès")
    ap.add_argument("--personas", default="aveugle,moteur,cognitif")
    ap.add_argument("--brain", choices=["auto", "claude", "gemini", "openai", "ollama", "mock"],
                    default="auto",
                    help="'auto' détecte la clé API présente (ANTHROPIC/OPENAI/GEMINI_API_KEY)")
    ap.add_argument("--model", default=None,
                    help="modèle du brain choisi (ex: gemini-2.5-flash-lite si le quota "
                         "journalier de gemini-2.5-flash est dépassé — quota séparé par modèle)")
    ap.add_argument("--out", default="out/rapport.html")
    ap.add_argument("--visitors", type=int, default=100000)
    ap.add_argument("--max-steps", type=int, default=None,
                    help="dépasse la limite par défaut (12) pour un parcours réel plus long")
    ap.add_argument("--check", action="store_true",
                    help="pré-check rapide (1 page, sans lancer les personas) puis quitte")
    a = ap.parse_args()

    if a.static:
        from simone.a11y import StaticDriver
        driver = StaticDriver(a.site)
        start, name = "index.html", Path(a.site).name
    else:
        from simone.a11y import PlaywrightDriver
        driver = PlaywrightDriver()
        start, name = a.url, a.url

    if a.check:
        driver.goto(start)
        state = driver.snapshot()
        driver.close()
        print(f"{state.title or '(sans titre)'} — {state.url}")
        print(f"{len(state.nodes)} élément(s) interactif(s) perçu(s).")
        if not state.nodes:
            print("Probablement bloqué (anti-bot), connexion requise, ou contenu chargé trop tard.")
            return 1
        for n in state.nodes[:15]:
            print(f"  - {n.label()}")
        return 0

    brain = get_brain(a.brain, model=a.model)
    is_llm = isinstance(brain, (LLMBrain, GeminiBrain, OpenAIBrain))
    results = []
    personas_list = a.personas.split(",")
    for i, p in enumerate(personas_list):
        print(f"→ {p} : lancement du parcours…")
        r = run_persona(driver, brain, p.strip(), a.goal, start, a.success_marker,
                        max_steps=a.max_steps)
        print(f"   {'✔ réussi' if r.success else '✘ bloqué'} en {r.n_steps} étapes"
              + (f" — {r.fail_reason[:90]}" if not r.success else ""))
        results.append(r)
        if a.static:  # réinitialiser la navigation entre personas
            driver.goto(start)
        if is_llm and i < len(personas_list) - 1:
            time.sleep(5)  # laisse respirer le quota gratuit avant le prochain persona
    driver.close()

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(render(results, name, monthly_visitors=a.visitors),
                           encoding="utf-8")
    print(f"\nRapport : {a.out}")
    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
