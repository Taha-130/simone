"""Interface Streamlit pour SIMONE — démo sans terminal après le lancement.
Lancer avec : streamlit run app.py
"""
import os
from pathlib import Path

import streamlit as st

from simone.agent import run_persona
from simone.brain import get_brain
from simone.report import render

st.set_page_config(page_title="SIMONE", page_icon="🦮", layout="wide")
st.title("SIMONE — agents IA qui testent l'accessibilité d'un site")

with st.sidebar:
    st.header("Configuration")
    mode = st.radio("Site à tester", ["Démo locale — site_ko (inaccessible)",
                                       "Démo locale — site_ok (accessible)",
                                       "URL réelle"])
    url = ""
    if mode == "URL réelle":
        url = st.text_input("URL de départ", "https://www.saucedemo.com")

    goal = st.text_input("Objectif du parcours", "Trouver un produit et l'ajouter au panier")
    success_marker = st.text_input("Texte prouvant le succès (success-marker)",
                                   "ajouté au panier" if mode == "URL réelle" else "commande confirmée")
    personas = st.multiselect("Personas", ["aveugle", "moteur", "cognitif"],
                              default=["aveugle", "moteur", "cognitif"])
    provider = st.radio("Cerveau", ["gemini", "claude", "mock"], index=0,
                       format_func=lambda p: {"gemini": "Gemini (gratuit, clé Google AI Studio)",
                                              "claude": "Claude (payant, clé Anthropic)",
                                              "mock": "Aucun — heuristique déterministe"}[p])
    api_key = ""
    if provider == "gemini":
        api_key = st.text_input("GEMINI_API_KEY", type="password",
                                help="Clé gratuite : https://aistudio.google.com/apikey — "
                                     "jamais enregistrée, utilisée pour cette session seulement.")
    elif provider == "claude":
        api_key = st.text_input("ANTHROPIC_API_KEY", type="password",
                                help="Utilisée uniquement pour cette session, jamais enregistrée.")
    visitors = st.number_input("Visiteurs mensuels (estimation du manque à gagner)",
                               value=100_000, step=1_000)
    launch = st.button("Lancer l'audit", type="primary", use_container_width=True)

if launch:
    if not personas:
        st.error("Sélectionne au moins un persona.")
        st.stop()
    if provider != "mock" and not api_key:
        st.error("Ce cerveau nécessite une clé API, ou choisis 'Aucun — heuristique déterministe'.")
        st.stop()

    if provider == "gemini" and api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    elif provider == "claude" and api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    brain = get_brain(provider)

    if mode == "URL réelle":
        from simone.a11y import PlaywrightDriver
        driver = PlaywrightDriver()
        start, name = url, url
    else:
        from simone.a11y import StaticDriver
        site = "demo_site/site_ko" if "ko" in mode else "demo_site/site_ok"
        driver = StaticDriver(site)
        start, name = "index.html", Path(site).name

    results = []
    try:
        for p in personas:
            with st.status(f"Persona « {p} » en cours…", expanded=True) as status:
                r = run_persona(driver, brain, p, goal, start, success_marker)
                for s in r.steps:
                    st.write(f"« {s.monologue} »")
                    if s.frictions:
                        st.caption("⚠ " + " ; ".join(s.frictions))
                label = f"{p} : {'✔ réussi' if r.success else '✘ bloqué'} en {r.n_steps} étapes"
                status.update(label=label, state="complete" if r.success else "error")
            results.append(r)
            if mode != "URL réelle":
                driver.goto(start)
    finally:
        driver.close()

    html = render(results, name, monthly_visitors=visitors)
    out_path = Path("out/rapport_streamlit.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    st.success("Audit terminé — rapport ci-dessous.")
    st.download_button("Télécharger le rapport HTML", html,
                       file_name="rapport_simone.html", mime="text/html")
    st.components.v1.html(html, height=1400, scrolling=True)
