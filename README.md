# SIMONE — POC hackathon
### Des agents IA testent votre site sous les contraintes réelles d'un utilisateur handicapé

Simone navigue un site avec trois personas :
- **aveugle** : ne perçoit QUE l'arbre d'accessibilité (ce que reçoit un lecteur d'écran). Un `<div onclick>` sans role ni nom n'existe littéralement pas pour elle.
- **moteur** : n'agit que sur les éléments atteignables au clavier (Tab/Entrée).
- **cognitif** : dispose d'un budget de confusion ; jargon, libellés vagues ("cliquez ici", "Suite"), erreurs sans explication le consomment ; à zéro, il abandonne.

Sortie : un **rapport métier HTML** (`out/rapport.html`) — taux de complétion par persona, point de blocage exact, monologue de l'agent, et manque à gagner mensuel estimé, avec le rappel réglementaire EAA.

## Installation
```bash
pip install playwright anthropic openai google-genai ollama streamlit
python -m playwright install chromium      # requis pour le mode réel
```

Cerveau LLM (au choix via `--brain` / sélecteur Streamlit, sinon MockBrain heuristique) :
```bash
export GEMINI_API_KEY=...        # gratuit, quota/jour limité : https://aistudio.google.com/apikey
export OPENAI_API_KEY=sk-...     # payant, ChatGPT
export ANTHROPIC_API_KEY=sk-...  # payant, Claude
# ou Ollama en local (gratuit ET illimité, aucune clé) :
brew install ollama && ollama serve && ollama pull llama3.2
```

## Interface web (recommandé pour tester/démontrer sans terminal)
```bash
streamlit run app.py
```
Formulaire dans le navigateur (site à tester, objectif, personas, choix du cerveau),
monologue affiché en direct, rapport HTML téléchargeable à la fin.

## Les 3 modes (du plus sûr au plus impressionnant)

**1. Démo de secours — zéro dépendance (fonctionne toujours, même sans réseau)**
```bash
python run_audit.py --site demo_site/site_ko --static --out out/rapport_site_ko.html
python run_audit.py --site demo_site/site_ok --static --out out/rapport_site_ok.html
```
Le site `site_ko` est volontairement inaccessible (CTA en `<div onclick>`, liens "cliquez ici", champs sans label, jargon bancaire) ; `site_ok` est la version corrigée. Résultat attendu : 0% de complétion vs 100%. Cerveau heuristique (MockBrain), déterministe.

**2. Vrai navigateur sur le site de démo (recommandé pour la présentation)**
```bash
python -m http.server 8000 --directory demo_site/site_ko &
python run_audit.py --url http://localhost:8000/index.html --out out/rapport.html
```
Playwright extrait le VRAI arbre d'accessibilité de Chromium (`page.accessibility.snapshot()`), le persona moteur parcourt le VRAI Tab order. Si `GEMINI_API_KEY` ou `ANTHROPIC_API_KEY` est défini, le cerveau est un LLM : monologues bien plus riches et adaptatifs — c'est la version à montrer.

**3. Site réel (l'effet maximal — à tester AVANT, jamais improvisé en live)**
```bash
python run_audit.py --url https://le-site-cible.fr --brain gemini \
  --goal "Trouver le formulaire de contact et l'envoyer" \
  --success-marker "message envoyé"
```
Règles d'or : tester le site cible 20 fois avant la démo ; définir un `--success-marker` fiable (texte qui n'apparaît QUE sur la page de succès) ; garder un screencast de la meilleure exécution en plan B.

## Architecture (pour l'étendre pendant le hackathon)
```
simone/a11y.py      extraction de l'arbre d'accessibilité (PlaywrightDriver / StaticDriver)
simone/personas.py  les contraintes de chaque persona + coûts de friction cognitive
simone/brain.py     décision : Claude / Gemini / ChatGPT / Ollama (local) / MockBrain (secours)
simone/agent.py     la boucle percevoir → décider → agir + journal
simone/report.py    le rapport métier HTML
run_audit.py        CLI
```

## Idées d'extension à annoncer en "prochaines étapes"
- Replay vidéo du parcours (Playwright sait enregistrer : `record_video_dir`)
- Persona senior (combinaison basse vision simulée + budget cognitif réduit)
- Monitoring continu : relancer l'audit à chaque déploiement (GitHub Action)
- Calibrage des personas par un panel rémunéré de testeurs en situation de handicap
- Export du rapport en PDF pour les directions juridiques (conformité EAA)

## Le pitch en une phrase
« Aujourd'hui, 99% des parcours web ne sont jamais testés du point de vue d'un utilisateur handicapé, faute de budget. Simone teste chaque nuit ce que personne ne testait jamais — et les testeurs humains experts valident et calibrent. »
