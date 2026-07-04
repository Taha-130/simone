"""Rapport métier HTML : le livrable que voit le jury / le client."""
from datetime import date

# Hypothèses de calcul du manque à gagner — SOURCÉES, à adapter par client.
POP = {
    "aveugle":  {"share": 0.026, "label": "déficience visuelle (1,7 M en France)"},
    "moteur":   {"share": 0.035, "label": "limitation motrice des membres supérieurs"},
    "cognitif": {"share": 0.080, "label": "troubles cognitifs / DYS / illettrisme numérique"},
}

CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#f6f7fb;color:#1a1a2e}
.wrap{max-width:960px;margin:0 auto;padding:32px}
header{background:#1a1a2e;color:#fff;padding:28px 32px}
h1{margin:0;font-size:26px} .sub{color:#a8b2d1;margin-top:6px}
.kpis{display:flex;gap:16px;margin:24px 0}
.kpi{flex:1;background:#fff;border-radius:10px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.kpi .v{font-size:30px;font-weight:700} .ok{color:#1b9e77} .ko{color:#e94560}
.card{background:#fff;border-radius:10px;padding:22px;margin:16px 0;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.b-ok{background:#e0f2ec;color:#1b9e77}.b-ko{background:#fde8ec;color:#e94560}
.step{border-left:3px solid #d5d9e8;margin:10px 0;padding:6px 12px;font-size:14px}
.step.fail{border-color:#e94560;background:#fff5f7}
.mono{font-style:italic;color:#333} .meta{color:#888;font-size:12px}
.friction{color:#b45309;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:8px 10px;border-bottom:1px solid #eee;text-align:left}
.gain{font-size:15px;background:#1a1a2e;color:#fff;border-radius:10px;padding:20px}
.gain b{color:#ffd166}
footer{color:#888;font-size:12px;padding:20px 32px}
"""


def euros(x):
    return f"{x:,.0f} €".replace(",", " ")


def render(results, site_name, monthly_visitors=100_000, conversion=0.02, basket=90):
    total = len(results)
    fails = [r for r in results if not r.success]
    completion = 100 * (total - len(fails)) / total if total else 0

    lost = 0.0
    rows = []
    for r in results:
        share = POP[r.persona_key]["share"]
        seg_visitors = monthly_visitors * share
        seg_lost = 0 if r.success else seg_visitors * conversion * basket
        lost += seg_lost
        rows.append((r, seg_visitors, seg_lost))

    h = [f"<html><head><meta charset='utf-8'><title>Rapport Simone — {site_name}</title>",
         f"<style>{CSS}</style></head><body>",
         "<header><h1>SIMONE — Rapport d'accessibilité d'usage</h1>",
         f"<div class='sub'>Site audité : <b>{site_name}</b> · Parcours : "
         f"« {results[0].goal} » · {date.today():%d/%m/%Y} · "
         "Conformité European Accessibility Act (EAA)</div></header><div class='wrap'>"]

    h.append("<div class='kpis'>")
    h.append(f"<div class='kpi'><div class='v {'ok' if completion==100 else 'ko'}'>"
             f"{completion:.0f}%</div>taux de complétion du parcours<br>"
             f"<span class='meta'>{total-len(fails)}/{total} personas aboutissent</span></div>")
    h.append(f"<div class='kpi'><div class='v ko'>{len(fails)}</div>personas bloqués"
             f"<br><span class='meta'>{', '.join(f.persona_key for f in fails) or '—'}</span></div>")
    h.append(f"<div class='kpi'><div class='v ko'>{euros(lost)}</div>manque à gagner mensuel estimé"
             f"<br><span class='meta'>{monthly_visitors:,} visites/mois, conv. {conversion:.0%}, "
             f"panier {basket} €</span></div>")
    h.append("</div>")

    for r, seg_v, seg_l in rows:
        badge = ("<span class='badge b-ok'>PARCOURS RÉUSSI</span>" if r.success
                 else "<span class='badge b-ko'>PARCOURS IMPOSSIBLE</span>")
        h.append(f"<div class='card'><h2>{r.persona_display}</h2>{badge} "
                 f"<span class='meta'>{r.n_steps} étapes · segment : "
                 f"{POP[r.persona_key]['label']} (~{seg_v:,.0f} visites/mois)</span>")
        if not r.success:
            h.append(f"<p><b>Point de blocage :</b> {r.fail_reason}</p>"
                     f"<p><b>Impact :</b> {euros(seg_l)} de ventes perdues par mois "
                     f"sur ce segment.</p>")
        if r.budget_left is not None:
            h.append(f"<p class='meta'>Budget de confusion restant : {max(r.budget_left,0):.1f}/10</p>")
        h.append("<h3>Journal du parcours (monologue de Simone)</h3>")
        for s in r.steps:
            cls = "step" + ("" if s.ok else " fail")
            fr = (f"<div class='friction'>⚠ frictions : {' ; '.join(s.frictions)}</div>"
                  if s.frictions else "")
            h.append(f"<div class='{cls}'><span class='mono'>« {s.monologue} »</span>"
                     f"<div class='meta'>{s.page} — action : {s.action}"
                     f"{' → ' + s.target if s.target else ''}</div>{fr}</div>")
        h.append("</div>")

    h.append("<div class='gain'>⚖ <b>Rappel réglementaire :</b> depuis juin 2025, "
             "l'European Accessibility Act impose l'accessibilité des services "
             "e-commerce, bancaires et de transport dans toute l'UE. Un parcours "
             "d'achat infranchissable constitue un risque de non-conformité en plus "
             "du manque à gagner ci-dessus.</div>")
    h.append("<footer>Simone v0.1 (POC hackathon) — les personas sont des contraintes "
             "techniques objectives calibrées, non des simulations de l'expérience vécue. "
             "La validation finale est réalisée par des testeurs experts en situation de "
             "handicap. Hypothèses de population : DREES/INSEE, à affiner par secteur."
             "</footer></div></body></html>")
    return "".join(h)
