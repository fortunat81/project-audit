#!/usr/bin/env python3
"""English and French text the audit page needs that does not come from Claude's report:
the 43 launch-checklist items, plain-language descriptions of common finding rules, check
statuses and dimension names. Anything not listed here is shown as the tool printed it.
Standard library only (Python 3.8+)."""
import re

# (English, French) for each item of reviews/release-gate.md, by number
CHECKLIST = {
    1: ("No secrets in the code, its history or committed .env files.", "Aucun secret dans le code, son historique ou des fichiers .env versionnés."),
    2: ("No secret key inside the website or app people download.", "Aucune clé secrète dans le site ou l'application que les gens téléchargent."),
    3: ("Debug mode off, no test logins left.", "Mode débogage désactivé, aucun compte de test oublié."),
    4: ("Test and live keys are separate, and any key that ever leaked was replaced.", "Les clés de test et de production sont séparées, et toute clé qui a déjà fuité a été remplacée."),
    5: ("Login is handled by a trusted service, or passwords are hashed with a modern method.", "La connexion passe par un service reconnu, ou les mots de passe sont hachés avec une méthode moderne."),
    6: ("Login and password reset are rate-limited; reset links are single-use and short-lived.", "La connexion et la réinitialisation du mot de passe sont limitées en nombre d'essais ; les liens de réinitialisation sont à usage unique et de courte durée."),
    7: ("Session cookies are Secure and HttpOnly; logout really ends the session.", "Les cookies de session sont Secure et HttpOnly ; la déconnexion termine réellement la session."),
    8: ("Admin accounts use two-step sign-in.", "Les comptes administrateurs utilisent la connexion en deux étapes."),
    9: ("Every table, bucket and route checks who is asking.", "Chaque table, espace de stockage et route vérifie qui fait la demande."),
    10: ("Changing an ID in a URL or request never shows someone else's data.", "Changer un identifiant dans une adresse ou une requête ne montre jamais les données de quelqu'un d'autre."),
    11: ("Admin features are blocked on the server, not just hidden on screen.", "Les fonctions d'administration sont bloquées côté serveur, pas seulement cachées à l'écran."),
    12: ("One customer can never reach another customer's data.", "Un client ne peut jamais accéder aux données d'un autre client."),
    13: ("Prices, permissions and the \"paid\" status are decided on the server, never taken from the browser.", "Les prix, les droits et le statut « payé » sont décidés par le serveur, jamais repris du navigateur."),
    14: ("Payment and other webhooks verify their signature and are handled once.", "Les webhooks (paiement et autres) vérifient leur signature et ne sont traités qu'une fois."),
    15: ("Everything users type is checked on the server; no raw text goes into queries, commands or pages.", "Tout ce que les utilisateurs saisissent est vérifié côté serveur ; aucun texte brut n'entre dans des requêtes, des commandes ou des pages."),
    16: ("The server answers only the websites it should (no open CORS unless it is a public read-only API).", "Le serveur ne répond qu'aux sites prévus (pas de CORS ouvert, sauf API publique en lecture seule)."),
    17: ("Expensive or abusable actions are limited (AI calls, emails, exports, sign-ups).", "Les actions coûteuses ou abusables sont limitées (appels d'IA, courriels, exports, inscriptions)."),
    18: ("Only the personal data you need is collected, and the privacy notice matches what the site does.", "Seules les données personnelles nécessaires sont collectées, et l'avis de confidentialité correspond à ce que fait le site."),
    19: ("Traffic uses HTTPS and the browser protections are set.", "Le trafic utilise HTTPS et les protections du navigateur sont activées."),
    20: ("Logs and error reports contain no passwords, tokens or personal data.", "Les journaux et rapports d'erreurs ne contiennent ni mots de passe, ni jetons, ni données personnelles."),
    21: ("Test environments use fake data.", "Les environnements de test utilisent de fausses données."),
    22: ("A lockfile is committed, so installs are repeatable.", "Un fichier de verrouillage est versionné : les installations sont reproductibles."),
    23: ("No known serious vulnerabilities in packages.", "Aucune vulnérabilité grave connue dans les paquets."),
    24: ("Every package name is real and expected.", "Chaque nom de paquet est réel et attendu."),
    25: ("Automated workflows can't be tricked by outside text.", "Les flux automatisés ne peuvent pas être trompés par du texte venant de l'extérieur."),
    26: ("The code repository is private unless meant to be public, and sign-in to it uses two-step verification.", "Le dépôt de code est privé sauf intention contraire, et sa connexion utilise la vérification en deux étapes."),
    27: ("Databases and storage are not open to the public internet or to \"anyone signed in\".", "Les bases de données et le stockage ne sont ouverts ni à Internet ni à « tout utilisateur connecté »."),
    28: ("Containers don't run as root and use a pinned image version.", "Les conteneurs ne tournent pas en root et utilisent une version d'image précise."),
    29: ("The runtime (Node, Python) still gets security fixes.", "L'environnement d'exécution (Node, Python) reçoit encore des correctifs de sécurité."),
    30: ("Staging and preview sites are not public, or hold no real data.", "Les sites de test et d'aperçu ne sont pas publics, ou ne contiennent aucune donnée réelle."),
    31: ("There are automated tests, including some for login and access rules.", "Il existe des tests automatisés, dont certains pour la connexion et les règles d'accès."),
    32: ("Checks run on every change.", "Des vérifications s'exécutent à chaque modification."),
    33: ("The main journeys were tried on the live build.", "Les parcours principaux ont été essayés sur la version en ligne."),
    34: ("Source maps and debug files aren't published.", "Les fichiers de cartes source et de débogage ne sont pas publiés."),
    35: ("Backups are on and a restore was tried once.", "Les sauvegardes sont actives et une restauration a été essayée une fois."),
    36: ("Errors and downtime reach a person.", "Les erreurs et les pannes sont signalées à une personne."),
    37: ("There is a way back: the previous version can be restored quickly.", "Il existe un retour en arrière : la version précédente peut être restaurée rapidement."),
    38: ("Someone owns updates: who patches packages, how often, and what happens when a serious vulnerability is announced.", "Quelqu'un est responsable des mises à jour : qui corrige les paquets, à quelle fréquence, et que faire quand une faille grave est annoncée."),
    39: ("A handover note exists: where the keys live, who has access, what to do if one leaks, who owns the domain and hosting.", "Une note de passation existe : où sont les clés, qui a accès, que faire si l'une fuit, à qui appartiennent le domaine et l'hébergement."),
    40: ("Written threat model of the sensitive flows.", "Modèle de menaces écrit pour les parcours sensibles."),
    41: ("Independent penetration test of the live system, with fixes retested.", "Test d'intrusion indépendant du système en ligne, correctifs retestés."),
    42: ("Restore exercise with measured recovery time; incident plan with contacts.", "Exercice de restauration avec temps de reprise mesuré ; plan d'incident avec contacts."),
    43: ("Legal review of privacy and data-location obligations for the clients' regions.", "Revue juridique des obligations de confidentialité et de localisation des données pour les régions des clients."),
}

# Plain-language descriptions of rule names that tools print, by exact name
RULES = {
    "env-style-secret": ("A line like NAME=value whose name says it is a secret (key, token, password).", "Une ligne du type NOM=valeur dont le nom indique un secret (clé, jeton, mot de passe)."),
    "generic-api-key": ("Text that looks like an API key or token.", "Du texte qui ressemble à une clé d'API ou à un jeton."),
    "aws-access-token": ("An Amazon Web Services access key.", "Une clé d'accès Amazon Web Services."),
    "github-pat": ("A GitHub personal access token.", "Un jeton d'accès personnel GitHub."),
    "stripe-access-token": ("A Stripe secret key.", "Une clé secrète Stripe."),
    "jwt": ("A login token (JWT) written into the code.", "Un jeton de connexion (JWT) écrit dans le code."),
    "private-key": ("A private cryptographic key.", "Une clé cryptographique privée."),
    "eval-detected": ("eval() runs text as code. If visitors can influence that text, they can run their own code.", "eval() exécute du texte comme du code. Si des visiteurs peuvent influencer ce texte, ils peuvent exécuter leur propre code."),
    "detect-eval-with-expression": ("eval() is called on a computed value; if it can contain visitor input it is dangerous.", "eval() est appelé sur une valeur calculée ; si elle peut contenir une saisie de visiteur, c'est dangereux."),
    "detect-child-process": ("The code starts operating-system commands. Visitor input must never reach them.", "Le code lance des commandes du système. Aucune saisie de visiteur ne doit y arriver."),
    "react-insecure-request": ("A request uses plain http:// instead of https://.", "Une requête utilise http:// simple au lieu de https://."),
    "github-actions-mutable-action-tag": ("A GitHub Action is referenced by a movable tag instead of an exact commit.", "Une action GitHub est référencée par une étiquette modifiable au lieu d'un commit précis."),
    "run-shell-injection": ("A workflow puts outside text straight into a shell command.", "Un flux de travail place du texte extérieur directement dans une commande shell."),
    "express-sequelize-injection": ("Visitor input may reach a database query unchecked (SQL injection).", "Une saisie de visiteur peut arriver sans contrôle dans une requête de base de données (injection SQL)."),
    "tainted-sql-string": ("A database query is built by joining text, which allows SQL injection.", "Une requête de base de données est construite en collant du texte, ce qui permet l'injection SQL."),
    "detect-non-literal-regexp": ("A pattern is built from variable text, which can be slow or abused.", "Un motif est construit à partir d'un texte variable, ce qui peut être lent ou détourné."),
    "dangerous-template-string": ("Page text is built from unchecked input (cross-site scripting).", "Le texte d'une page est construit à partir d'une saisie non contrôlée (injection de scripts)."),
    "render-template-string": ("A page template is built from text at run time (cross-site scripting).", "Un modèle de page est construit à partir de texte à l'exécution (injection de scripts)."),
    "raw-html-format": ("HTML is built by joining text, which allows cross-site scripting.", "Du HTML est construit en collant du texte, ce qui permet l'injection de scripts."),
    "detected-jwt-token": ("A login token (JWT) appears in the code.", "Un jeton de connexion (JWT) apparaît dans le code."),
    "missing-integrity": ("A script or style loaded from another site has no integrity check.", "Un script ou un style chargé depuis un autre site n'a pas de contrôle d'intégrité."),
    "unpinned-uses": ("A GitHub Action is not pinned to an exact commit.", "Une action GitHub n'est pas figée sur un commit précis."),
    "cache-poisoning": ("A workflow that publishes results also restores a cache that could have been tampered with.", "Un flux de travail qui publie des résultats restaure aussi un cache qui pourrait avoir été altéré."),
    "artipacked": ("The checkout step keeps the repository credentials available to later steps.", "L'étape de récupération du code garde les identifiants du dépôt disponibles pour les étapes suivantes."),
    "template-injection": ("Outside text is placed into a workflow command (injection).", "Du texte extérieur est placé dans une commande de flux de travail (injection)."),
    "excessive-permissions": ("A workflow has more permissions than it needs.", "Un flux de travail a plus de permissions que nécessaire."),
    "DEBUG-ON": ("Debug mode is switched on, which shows internals to visitors.", "Le mode débogage est activé, ce qui montre des détails internes aux visiteurs."),
    "TEST-ACCOUNT": ("A test or default login is left in the code.", "Un compte de test ou par défaut est resté dans le code."),
    "CORS-OPEN": ("The server answers requests from every website.", "Le serveur répond aux requêtes de tous les sites."),
    "COOKIE-FLAGS": ("A session cookie is missing the Secure or HttpOnly protection.", "Un cookie de session n'a pas la protection Secure ou HttpOnly."),
    "DOCKER-ROOT": ("The container runs as the administrator (root).", "Le conteneur s'exécute en administrateur (root)."),
    "DOCKER-UNPINNED": ("The container's base image has no version tag.", "L'image de base du conteneur n'a pas d'étiquette de version."),
    "RUNTIME-EOL": ("The runtime version no longer receives security fixes.", "La version de l'environnement d'exécution ne reçoit plus de correctifs de sécurité."),
    "NO-LOCKFILE": ("No lockfile: installs are not repeatable and the dependency check cannot run.", "Pas de fichier de verrouillage : les installations ne sont pas reproductibles et la vérification des dépendances ne peut pas tourner."),
    "NO-TESTS": ("No automated tests were found.", "Aucun test automatisé trouvé."),
    "NO-CI": ("Nothing runs automatically on each change.", "Rien ne s'exécute automatiquement à chaque modification."),
    "SOURCEMAPS-COMMITTED": ("A source map is in the repository; it can reveal your original code if published.", "Une carte source est dans le dépôt ; elle peut révéler votre code d'origine si elle est publiée."),
    "ASTRO-SET-HTML": ("Raw HTML is written into the page. The value must never contain visitor input.", "Du HTML brut est écrit dans la page. La valeur ne doit jamais contenir de saisie de visiteur."),
    "CLIENT-VISIBLE": ("A secret-looking variable is bundled into the code every visitor downloads.", "Une variable qui ressemble à un secret est incluse dans le code que chaque visiteur télécharge."),
    "IN APP CONFIG (bundled)": ("A secret-looking setting is in the app config, which is bundled into the app.", "Un réglage qui ressemble à un secret est dans la configuration de l'application, qui est incluse dans l'application."),
    "COMMITTED TO GIT (rotate what it held)": ("A .env file is committed to git. Whatever it held must be replaced.", "Un fichier .env est versionné dans git. Tout ce qu'il contenait doit être remplacé."),
    "NOT GIT-IGNORED (one 'git add .' from being committed)": ("A .env file is not ignored by git and could be committed by accident.", "Un fichier .env n'est pas ignoré par git et pourrait être versionné par erreur."),
}

# Rule names that follow a pattern
RULE_PATTERNS = [
    (re.compile(r"^TS\d+$"), "A type error reported by the TypeScript compiler.", "Une erreur de type signalée par le compilateur TypeScript."),
    (re.compile(r"^complex-or-long-function:"), "A function that is long or has many branches, so it is harder to change safely.", "Une fonction longue ou avec beaucoup de branches, donc plus difficile à modifier sans risque."),
    (re.compile(r"\(\d+ advisories\)$"), "A package version with known security advisories.", "Une version de paquet avec des avis de sécurité connus."),
    (re.compile(r"^@typescript-eslint/no-unused-vars$"), "A variable or import that is never used.", "Une variable ou un import qui n'est jamais utilisé."),
]


def describe_rule(rule):
    """(english, french) for a rule name, or None when it is not in the glossary."""
    rule = str(rule)
    if rule in RULES:
        return RULES[rule]
    for pattern, en, fr in RULE_PATTERNS:
        if pattern.search(rule):
            return en, fr
    return None


STATUS_WORDS = {
    "clean": ("clean", "propre"), "findings": ("findings", "constats"), "done": ("measured", "mesuré"),
    "partial": ("partial", "partiel"), "skipped": ("skipped", "ignoré"), "failed-to-run": ("failed to run", "échec d'exécution"),
    "timeout": ("timed out", "délai dépassé"), "unavailable": ("unavailable", "indisponible"),
}

# Reasons the scripts print after the status word: (regex on the whole text, French replacement)
STATUS_PHRASES = [
    (r"dependencies not installed \(offer: scan\.sh --install-deps\)", "dépendances non installées (proposer : scan.sh --install-deps)"),
    (r"not installed \((.*)\)", r"non installé (\1)"),
    (r"no lockfile found", "aucun fichier de verrouillage trouvé"),
    (r"no lockfile \(run: npm i --package-lock-only\)", "pas de fichier de verrouillage (lancer : npm i --package-lock-only)"),
    (r"not an npm lockfile \(osv-scanner covers it\)", "ce n'est pas un fichier de verrouillage npm (osv-scanner le couvre)"),
    (r"no SQL migrations", "aucune migration SQL"),
    (r"not applicable", "sans objet"),
    (r"untrusted mode: (.*)", r"mode non fiable : \1"),
    (r"no ESLint config in the project \(looked for (.*)\)", r"pas de configuration ESLint dans le projet (cherché : \1)"),
    (r"Astro's generated types are missing, so tsc would report false errors \(run: npx astro sync, then scan again\)",
     "les types générés par Astro manquent : tsc signalerait de fausses erreurs (lancer : npx astro sync, puis relancer l'analyse)"),
    (r"partial: more project folders found: (.*) \(the checks that need a project folder ran only here; audit each folder separately\)",
     r"partiel : d'autres dossiers de projet ont été trouvés : \1 (les vérifications qui ont besoin d'un dossier de projet n'ont tourné qu'ici ; auditez chaque dossier séparément)"),
    (r"done: each project folder was scanned separately by --all: (.*)", r"mesuré : chaque dossier de projet a été analysé séparément par --all : \1"),
    (r"project files changed while the scan was running, so results may mix two versions \(run the scan again\)",
     "les fichiers du projet ont changé pendant l'analyse : les résultats peuvent mélanger deux versions (relancer l'analyse)"),
    (r"(\d+) error\(s\), some files not fully scanned \(see errors in semgrep\.json\)", r"\1 erreur(s) : certains fichiers n'ont pas été analysés en entier (voir les erreurs dans semgrep.json)"),
    (r"JavaScript files left out because lizard crashed on one \(see lizard-crash\.err\); (.*)", r"fichiers JavaScript exclus car lizard a planté sur l'un d'eux (voir lizard-crash.err) ; \1"),
    (r"turned off in \.audit\.conf", "désactivé dans .audit.conf"),
    (r"no node or python available to read semgrep\.json", "ni node ni python pour lire semgrep.json"),
    (r"see (.*\.err)", r"voir \1"),
]

DIMENSIONS = {
    "security": ("security", "sécurité"), "quality": ("quality", "qualité"), "architecture": ("architecture", "architecture"),
    "modularity": ("modularity", "modularité"), "spaghettiness": ("spaghettiness", "code spaghetti"),
    "scalability": ("scalability", "mise à l'échelle"), "documentation": ("documentation", "documentation"),
    "general": ("general", "général"),
}


def translate_status(status):
    """{'en': ..., 'fr': ...} for a manifest status such as 'skipped: not installed (pip install x)'."""
    head, sep, rest = status.partition(":")
    head_key = head.strip()
    if head_key not in STATUS_WORDS:
        return {"en": status, "fr": status}
    en_word, fr_word = STATUS_WORDS[head_key]
    if not sep:
        return {"en": en_word, "fr": fr_word}
    rest = rest.strip()
    fr_rest = rest
    for pattern, replacement in STATUS_PHRASES:
        new, n = re.subn(r"^" + pattern + r"$", replacement, rest)
        if n:
            fr_rest = new
            break
    return {"en": "%s: %s" % (en_word, rest), "fr": "%s : %s" % (fr_word, fr_rest)}


def translate_dimensions(text):
    """'security,quality' -> {'en': ..., 'fr': ...}"""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    return {"en": ", ".join(DIMENSIONS.get(p, (p, p))[0] for p in parts), "fr": ", ".join(DIMENSIONS.get(p, (p, p))[1] for p in parts)}
