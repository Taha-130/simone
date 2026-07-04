"""Interface Streamlit pour SIMONE — démo sans terminal après le lancement.
Lancer avec : streamlit run app.py
"""
import os
import time
from pathlib import Path

import streamlit as st

from simone.agent import run_persona
from simone.brain import GeminiBrain, LLMBrain, OpenAIBrain, get_brain
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

    goal = st.text_input("Objectif du parcours",
                         "Trouver un produit et l'ajouter au panier" if mode == "URL réelle"
                         else "Acheter le Casque Audio X et finaliser la commande")
    success_marker = st.text_input("Texte prouvant le succès (success-marker)",
                                   "ajouté au panier" if mode == "URL réelle" else "commande confirmée")
    st.caption("⚠ Le texte de succès doit correspondre à l'objectif : s'il décrit une étape "
              "plus loin que l'objectif demandé, l'agent abandonne en pensant avoir fini.")
    personas = st.multiselect("Personas", ["aveugle", "moteur", "cognitif"],
                              default=["aveugle", "moteur", "cognitif"])
    provider = st.radio("Cerveau", ["gemini", "claude", "openai", "ollama", "mock"], index=0,
                       format_func=lambda p: {"gemini": "Gemini (gratuit, quota/jour limité)",
                                              "claude": "Claude (payant, clé Anthropic)",
                                              "openai": "ChatGPT (payant, clé OpenAI)",
                                              "ollama": "Ollama local (gratuit, illimité, ton Mac)",
                                              "mock": "Aucun — heuristique déterministe"}[p])
    api_key, model = "", None
    if provider == "gemini":
        api_key = st.text_input("GEMINI_API_KEY", type="password",
                                help="Clé gratuite : https://aistudio.google.com/apikey — "
                                     "jamais enregistrée, utilisée pour cette session seulement.")
        model = st.selectbox("Modèle Gemini", ["gemini-2.5-flash", "gemini-2.5-flash-lite",
                                               "gemini-2.0-flash"],
                             help="Chaque modèle a son propre quota gratuit par jour. Change de "
                                  "modèle si tu vois 'quota dépassé' — le quota du jour est "
                                  "compté séparément pour chacun.")
    elif provider == "claude":
        api_key = st.text_input("ANTHROPIC_API_KEY", type="password",
                                help="Utilisée uniquement pour cette session, jamais enregistrée.")
    elif provider == "openai":
        api_key = st.text_input("OPENAI_API_KEY", type="password",
                                help="Utilisée uniquement pour cette session, jamais enregistrée.")
        model = st.text_input("Modèle OpenAI", "gpt-4o-mini")
    elif provider == "ollama":
        model = st.text_input("Modèle Ollama", "llama3.2",
                              help="Doit déjà être téléchargé (`ollama pull llama3.2`) et "
                                   "`ollama serve` doit tourner. Aucune clé, gratuit et illimité.")
    visitors = st.number_input("Visiteurs mensuels (estimation du manque à gagner)",
                               value=100_000, step=1_000)
    max_steps = st.slider("Nombre d'étapes max par persona", min_value=6, max_value=40, value=12,
                         help="Augmente pour un parcours réel plus long qu'en démo.")
    force_continue = st.checkbox("Lancer quand même si le pré-check ne voit rien",
                                 help="Sinon l'audit s'arrête tout de suite si 0 élément "
                                      "interactif est perçu, au lieu de faire tourner les "
                                      "3 personas pour rien pendant plusieurs minutes.")
    check = st.button("🔍 Vérifier le site (quelques secondes)", use_container_width=True)
    launch = st.button("▶️ Lancer l'audit complet", type="primary", use_container_width=True)


def make_driver():
    if mode == "URL réelle":
        from simone.a11y import PlaywrightDriver
        return PlaywrightDriver(), url, url
    from simone.a11y import StaticDriver
    site = "demo_site/site_ko" if "ko" in mode else "demo_site/site_ok"
    return StaticDriver(site), "index.html", Path(site).name


if check:
    driver, start, _ = make_driver()
    try:
        with st.spinner("Chargement du site…"):
            driver.goto(start)
            state = driver.snapshot()
    finally:
        driver.close()
    st.write(f"**{state.title or '(sans titre)'}** — `{state.url}`")
    n = len(state.nodes)
    if n == 0:
        st.error("0 élément interactif perçu dès la première page. Le site est probablement "
                 "bloqué (anti-bot), nécessite une connexion, ou charge son contenu trop tard "
                 "pour être vu par Playwright. Lancer l'audit complet échouera très "
                 "probablement pour les 3 personas.")
    else:
        st.success(f"{n} éléments interactifs perçus — le site semble exploitable.")
        with st.expander("Aperçu des éléments perçus"):
            for node in state.nodes[:15]:
                st.write(f"- {node.label()}")

if launch:
    if not personas:
        st.error("Sélectionne au moins un persona.")
        st.stop()
    if provider in ("gemini", "claude", "openai") and not api_key:
        st.error("Ce cerveau nécessite une clé API, ou choisis 'Aucun — heuristique déterministe'.")
        st.stop()

    if provider == "gemini" and api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    elif provider == "claude" and api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    elif provider == "openai" and api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    brain = get_brain(provider, model=model)

    driver, start, name = make_driver()

    with st.spinner("Pré-check rapide du site…"):
        driver.goto(start)
        precheck_state = driver.snapshot()
    if len(precheck_state.nodes) == 0 and not force_continue:
        st.error("0 élément interactif perçu dès la première page — probablement bloqué "
                 "(anti-bot, connexion requise, ou contenu chargé trop tard). L'audit "
                 "échouerait pour les 3 personas. Coche « Lancer quand même » pour forcer.")
        driver.close()
        st.stop()

    is_llm = isinstance(brain, (LLMBrain, GeminiBrain, OpenAIBrain))
    results = []
    try:
        for i, p in enumerate(personas):
            with st.status(f"Persona « {p} » en cours…", expanded=True) as status:
                r = run_persona(driver, brain, p, goal, start, success_marker, max_steps=max_steps)
                for s in r.steps:
                    st.write(f"« {s.monologue} »")
                    if s.frictions:
                        st.caption("⚠ " + " ; ".join(s.frictions))
                label = f"{p} : {'✔ réussi' if r.success else '✘ bloqué'} en {r.n_steps} étapes"
                status.update(label=label, state="complete" if r.success else "error")
            results.append(r)
            if mode != "URL réelle":
                driver.goto(start)
            if is_llm and i < len(personas) - 1:
                with st.spinner("Pause de quelques secondes (quota gratuit)…"):
                    time.sleep(5)
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
