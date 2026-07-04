#!/usr/bin/env python3
"""
SIMONE — POC d'audit d'accessibilité par agents IA.
Usage :
  python run_audit.py --site demo_site/site_ko --static          # démo sans navigateur
  python run_audit.py --url https://exemple.com --goal "..."     # vrai site (Playwright)
Options : --llm force le cerveau Claude (sinon auto si ANTHROPIC_API_KEY présent)
"""
import argparse, sys
from pathlib import Path
from simone.agent import run_persona
from simone.brain import get_brain
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
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--out", default="out/rapport.html")
    ap.add_argument("--visitors", type=int, default=100000)
    a = ap.parse_args()

    if a.static:
        from simone.a11y import StaticDriver
        driver = StaticDriver(a.site)
        start, name = "index.html", Path(a.site).name
    else:
        from simone.a11y import PlaywrightDriver
        driver = PlaywrightDriver()
        start, name = a.url, a.url

    brain = get_brain(True if a.llm else None)
    results = []
    for p in a.personas.split(","):
        print(f"→ {p} : lancement du parcours…")
        r = run_persona(driver, brain, p.strip(), a.goal, start, a.success_marker)
        print(f"   {'✔ réussi' if r.success else '✘ bloqué'} en {r.n_steps} étapes"
              + (f" — {r.fail_reason[:90]}" if not r.success else ""))
        results.append(r)
        if a.static:  # réinitialiser la navigation entre personas
            driver.goto(start)
    driver.close()

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(render(results, name, monthly_visitors=a.visitors),
                           encoding="utf-8")
    print(f"\nRapport : {a.out}")
    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
