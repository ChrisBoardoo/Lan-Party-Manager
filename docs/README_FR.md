<div align="center">

<img src="../assets/images/favicon_LPM.png" alt="Logo LAN Party Manager" width="200" height="200" />

# LAN Party Manager

**Gestion d'événements auto-hébergée pour LAN parties** — invitations, tournois, trésorerie,
médias et streams en direct, le tout sur votre propre matériel. D'un Raspberry Pi à un NUC.

[![Version](https://img.shields.io/badge/version-1.4.1-FF3D00?style=flat-square)](#)
[![Licence](https://img.shields.io/badge/licence-AGPL--3.0-4C566A?style=flat-square)](../LICENSE)
[![Plateforme](https://img.shields.io/badge/plateforme-amd64%20%7C%20arm64%20(Pi%204%2F5)-555?style=flat-square)](#)
[![Docker](https://img.shields.io/badge/Docker-multi--arch-2496ED?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/r/crosswax/lanpartymanager-backend)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20FR-3B82F6?style=flat-square)](#localisation)

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/)

**Français** · [English](README.md)

</div>

---

Une application unique, privée et auto-hébergée pour tout ce dont une LAN party a besoin : protéger
l'inscription derrière des codes d'invitation par événement, gérer les RSVP avec dates d'arrivée et
de départ, organiser des tournois à élimination directe et en toutes rondes, répartir les frais
partagés au prorata, mettre en avant des streams Twitch, rassembler une galerie photo/vidéo partagée
et conserver un journal d'activité et d'audit complet — le tout en **français et en anglais**. Aucun
compte cloud, aucune télémétrie, aucun abonnement. Les données de votre équipe restent sur votre machine.

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Stack technique](#stack-technique)
- [Démarrage rapide](#démarrage-rapide)
- [Configuration](#configuration)
- [Développement](#développement)
- [Référence API](#référence-api)
- [Rôles et permissions](#rôles-et-permissions)
- [Répartition des coûts au prorata](#répartition-des-coûts-au-prorata)
- [Dépannage](#dépannage)
- [Application de bureau (Windows)](#application-de-bureau-windows)
- [Structure du projet](#structure-du-projet)
- [Localisation](#localisation)
- [Licence](#licence)

---

## Fonctionnalités

| | |
|---|---|
| **Connexion flexible** | Connectez-vous avec **votre pseudo ou votre e-mail** ; **SSO Discord** optionnel pour une connexion et une inscription en un clic ; **mot de passe oublié / réinitialisation** en libre-service par e-mail (SMTP). Les joueurs lient/délient Discord depuis leur profil ; les admins le configurent dans les Réglages. |
| **Gestion de l'équipe** | Inscription protégée par un code d'invitation par événement (6 caractères, places liées à la capacité de l'événement) ; profils, tailles de t-shirt, avatars WebP, pages de profil joueur. |
| **Calendrier des LAN** | Planifiez des événements avec dates, lieu, description et capacité optionnelle ; RSVP avec dates d'arrivée/départ bornées à la fenêtre de l'événement et décompte en direct des participants ; code d'invitation partageable par QR pour chaque événement ; **ajout au calendrier** (lien Google Agenda ou fichier `.ics`) pour chaque événement. |
| **Craving Chat** | Un chat de groupe léger par événement, réservé aux participants confirmés, ouvert de 30 jours avant l'événement à 15 jours après. Réponses, fenêtre d'auto-édition de 10 minutes, une réaction emoji par personne, autocomplétion des mentions @, aperçus de liens, message épinglé par un admin, indicateur « en train d'écrire… » en direct, et recherche dans les messages. Des raccourcis tapés comme `<3`, `:)`, `xD` et `:rofl:` s'affichent en emoji. Activé par défaut ; un admin peut le désactiver et régler la fenêtre. |
| **Planification (vue calendrier)** | Proposez des jeux pour un événement et **votez sur les heures** pour y jouer via une heatmap jour × heure — dans les limites de la présence de chacun — puis un organisateur **verrouille** le planning. Deux bascules indépendantes (proposer / voter). Optionnel. |
| **Matériel BYO** | « Qui apporte quoi » par événement : les membres **annoncent** le matériel qu'ils apportent, les admins publient des **demandes** (« il nous faut un 4ᵉ écran ») qu'un membre peut **réclamer**, et un casier de matériel personnel reprend le kit habituel d'un membre en un clic pour le prochain événement. Optionnel. |
| **Checklist de préparation** | Une checklist de préparation **privée**, par membre et par événement — 9 objets pré-remplis (ordinateur, écran, câbles, casque…) plus jusqu'à 10 champs personnalisés, avec reprise en un clic de « votre liste habituelle » depuis le dernier événement. Personne d'autre que le propriétaire ne peut jamais la voir, pas même un admin. Optionnel. |
| **Mini-Jeux** | Jeux d'arcade intégrés avec un **classement persistant par joueur**, pour faire revenir le crew entre deux LAN. Livré avec *Neon Survivor* (un roguelite) ; le schéma est multi-jeux, d'autres peuvent donc être ajoutés sans migration. Seules les parties solo sont classées — une partie coop à deux dure mécaniquement plus longtemps. Les scores sont vérifiés côté serveur contre un jeton de partie et le temps réellement écoulé. Optionnel. |
| **Ludothèque et recherche de jeux** | Chaque membre tient sa ludothèque (favoris, nombre de joueurs, liste de souhaits), importable depuis un compte Steam lié. La recherche classe les coéquipiers par jeux en commun et liste ce que tout un groupe possède, pour une session qui démarre sans le tour de « qui l'a ? ». Optionnel. |
| **Riot ID et stats LoL** | Les membres renseignent leur Riot ID ; l'application de bureau capture les parties de League of Legends jouées pendant une LAN, et la page Jeux affiche les stats par événement et globales. Les envois sont limités et bornés, une partie ne compte pour un membre que si sa propre application l'a envoyée, et un admin peut retirer une partie qui ne devrait pas compter. Optionnel. |
| **XP et niveaux** | XP et niveaux du crew dérivés à la lecture des tournois, des présences, du chat et des médias — rien n'est stocké, rien à migrer — avec un classement sur le Hub et le détail sur chaque profil. Un tournoi ne rapporte d'XP que si les deux camps ont des comptes liés. Optionnel. |
| **Cartes à collectionner et boosters** | Dépensez de l'XP en boosters qui révèlent des cartes du crew (l'Épique toujours en dernier) ; la collection de chaque membre est une vitrine que tout le crew peut parcourir. Achat et ouverture sont atomiques — un double clic ne dépense jamais deux fois. Optionnel, nécessite l'XP. |
| **Contrat mensuel** | Une série d'objectifs pour le mois, qui rapporte de l'XP une fois le nombre requis atteint, avec la progression de chaque membre calculée à partir de ce qu'il fait déjà. Optionnel, nécessite l'XP. |
| **Trophées et votes** | Des trophées définis par le crew et décernés par événement — par vote des participants (ouverture, clôture, relance des retardataires, révélation) ou par un admin. Les brouillons restent réservés aux admins jusqu'à la révélation ; les trophées d'un membre font sa vitrine. Optionnel. |
| **Courses** | Une liste de courses par événement : les participants ajoutent des articles, désignent qui achète, cochent ce qui est acheté, ou importent toute une liste d'un coup. Optionnel. |
| **WiFi invités (QR)** | Les admins saisissent une fois le SSID, la sécurité et le mot de passe du lieu ; la page de l'événement et le kiosque affichent un QR code WiFi à scanner. Un SSID vide le masque. |
| **Verrou des présences** | Dès le premier jour d'un événement, les membres ne peuvent plus changer leur réponse (409 avec un message clair) ; un trésorier ou un admin la fixe pour eux, avec trace d'audit et notification — le prorata repose ainsi sur les nuits réelles. |
| **Trésorerie** | Suivi des dépenses par catégorie, **répartition automatique au prorata** selon les nuits de présence, règlement entre pairs (P2P) et export CSV en un clic. |
| **Lots** | Présentez les lots (photo + description) par événement pour récompenser les vainqueurs des tournois. Activer les Lots masque la Trésorerie — les équipes qui offrent des lots ne partagent généralement pas les dépenses. Optionnel. |
| **Sponsors** | Bannières de sponsors (image ou vidéo) avec lien cliquable, affichées sur les pages événement, tournois et profil joueur. Optionnel. |
| **Arène / Tournois** | Événements par équipe ou solo/individuel ; **arbres à élimination directe et toutes rondes** (classement V/D/N/Pts) ; têtes de série par équipe ; **tirage aléatoire des équipes** (taille fixe, relance à volonté, restants placés à la main) ; suivi des scores en direct ; **signalement des scores depuis le téléphone** (les joueurs signalent, l'organisateur confirme) ; vue plein écran de l'arbre pour la projection. |
| **Streams en direct** | Intégration des chaînes **et clips** Twitch ; statut en direct + nombre de spectateurs via l'API Twitch Helix ; iframe de chat optionnelle. |
| **Galerie média** | Espace photo/vidéo partagé ; envois taggés par événement ; **réactions en emoji** ; suppression groupée (admin) ; miniatures vidéo générées par ffmpeg ; lightbox intégrée. |
| **Ma configuration** | Une vitrine du PC gaming d'un membre sur son profil — composants, champs personnalisés, jusqu'à 5 photos, réactions en emoji des coéquipiers — avec un lien public optionnel qu'il crée et révoque lui-même. Optionnel. |
| **Rétrospective d'après-événement** | Page de temps forts générée automatiquement pour un événement terminé — champion, MVP, nuits passées, meilleures photos, dépenses et badges — dérivée à la volée depuis les autres fonctionnalités, rien n'est dupliqué. Lien de partage public optionnel (n'inclut jamais les montants). Optionnel. |
| **Kiosque / Grand écran** | Un affichage ambiant, en lecture seule, pour la salle de LAN, autorisé par un jeton révocable (aucune connexion personnelle sur l'écran partagé). Fait défiler activité, classements, streams et planning, plus le **#LoveWall** : dernières photos/vidéos révélées en animation, coup de cœur épinglé, emojis de réaction en direct, et un « drop » plein écran quand quelqu'un poste pendant la LAN (désactivable par un admin). Optionnel. |
| **Activité et Panthéon** | Fil des 20 événements les plus récents sur le tableau de bord, plus un classement des joueurs par taux de victoire issu des tournois terminés. |
| **Annonces et présence** | **Bannière PA** admin (info/alerte, expiration auto, relais Discord optionnel) affichée dans toute l'app ; la liste du HUB montre **qui est en ligne** via un heartbeat léger du navigateur. |
| **Journal d'audit** | Trace réservée aux admins des actions sensibles — création/suppression d'événement, suppression de tournoi, codes d'invitation, chaque écriture de dépense et de règlement, changements de rôle, désactivation/suppression de membre, réinitialisations de mot de passe, annonces, retrait d'une partie LoL — avec auteur et horodatage. |
| **Réglages admin** | Identifiants Twitch + SSO Discord, SMTP (e-mails de réinitialisation), devise, bascules d'activation par fonctionnalité, et sauvegarde en un clic de la BDD + envois au format `tar.gz`. |
| **Accès par rôle** | Rôles Admin, Trésorier et Utilisateur appliqués côté serveur pour chaque route — pas seulement masqués dans l'interface. |

### Pour quelle taille de LAN ?

LPM est conçu pour un crew de 10 à 50 personnes qui se retrouve quelques fois par an, et c'est là
qu'il est chez lui. Ce que disent les chiffres :

- Un Raspberry Pi 4 sur carte SD fait tourner toute la pile à cette taille avec de la marge : les
  écritures se comptent en quelques-unes par minute au pic d'une LAN, et SQLite en mode WAL en
  absorbe des centaines par seconde.
- L'XP, les cartes, la rétrospective et le panthéon sont dérivés à la lecture de ce que le crew fait
  déjà : ils n'ajoutent aucune ligne. Un crew de 20 reste à quelques mégaoctets de base après des
  années.
- À 250 personnes avec sponsors, ce qui cède en premier n'est pas la base : le worker uvicorn unique
  sur un Pi, le chat qui relaie chaque message à 250 connexions WebSocket, les miniatures ffmpeg sur
  le Pi et le `fsync` de la carte SD. La réponse est un Pi 5 sur NVMe ou une petite machine x86 et
  plus de workers, pas un autre moteur de base de données.
- `DATABASE_URL` est une variable d'environnement et SQLAlchemy + Alembic parlent PostgreSQL, pour le
  jour où plusieurs conteneurs backend, une centaine d'écrivains simultanés ou une base de plusieurs
  Go se présenteront. Rien de tout cela n'est en vue à l'échelle d'un crew.

---

## Stack technique

| Couche    | Technologie                                                             |
|-----------|-------------------------------------------------------------------------|
| Backend   | Python 3.11, FastAPI, SQLAlchemy 2, SQLite (mode WAL), migrations Alembic |
| Auth      | JWT (HS256), mots de passe Bcrypt, SSO Discord OAuth2 optionnel         |
| Frontend  | React 18, TypeScript, Tailwind CSS, Vite                                |
| Exécution | Docker Compose, Nginx (frontend + fichiers statiques), Uvicorn (API)    |
| Média     | Pillow (traitement d'images), ffmpeg (miniatures vidéo)                 |
| Externe   | API Twitch Helix + Discord OAuth2 via httpx (optionnel, configuré par l'admin) |

Des images multi-architectures sont publiées pour `linux/amd64` et `linux/arm64` : la même stack
tourne sur un Raspberry Pi 4/5 comme sur un serveur x86, sans modification.

---

## Démarrage rapide

### Prérequis

- [Docker](https://docs.docker.com/get-docker/) et Docker Compose v2
- Port `3001` libre sur votre hôte (plus `8000` en boucle locale seulement si vous compilez depuis les sources)

### Option A — Depuis Docker Hub (le plus rapide, sans build)

```bash
# 1. Créer un répertoire de travail
mkdir lanpartymanager && cd lanpartymanager
mkdir -p data uploads

# 2. Créer le fichier docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  backend:
    image: crosswax/lanpartymanager-backend:latest
    # Pas de ports: — le Nginx du frontend le joint par le réseau Docker.
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    environment:
      # Facultatif — absente ou vide, le backend génère une clé aléatoire au premier
      # démarrage et la garde dans ./data/secret_key. Les valeurs d'exemple connues
      # et les clés de moins de 16 caractères sont refusées au démarrage.
      SECRET_KEY: ""
      DATABASE_URL: sqlite:///./data/lanparty.db
      UPLOAD_DIR: /app/uploads
    restart: unless-stopped

  frontend:
    image: crosswax/lanpartymanager-frontend:latest
    ports:
      - "3001:80"
    volumes:
      - ./uploads:/app/uploads
    depends_on:
      - backend
    restart: unless-stopped
EOF

# 3. Démarrer
docker compose up -d
```

> Images sur Docker Hub : [`crosswax/lanpartymanager-backend`](https://hub.docker.com/r/crosswax/lanpartymanager-backend) · [`crosswax/lanpartymanager-frontend`](https://hub.docker.com/r/crosswax/lanpartymanager-frontend)

### Portainer et autres interfaces de stack

Portainer transforme `${VAR:-défaut}` en chaîne vide au lieu de la valeur par défaut : écrivez des
valeurs littérales dans la stack. Deux autres habitudes qui payent sur une machine auto-hébergée :

- Épinglez les deux lignes `image:` à un numéro de version (`crosswax/lanpartymanager-backend:1.4.1`,
  pas `:latest`). Une mise à jour devient une modification délibérée, et revenir en arrière consiste
  à remettre le numéro précédent. Chaque version est poussée sous les deux tags.
- Si le conteneur backend ne résout plus les noms (liaison Discord et Steam en échec toutes les deux,
  mails qui ne partent pas), ajoutez `dns: [1.1.1.1, 9.9.9.9]` au service backend.

### Option B — Compilation depuis les sources

```bash
git clone https://github.com/ChrisBoardoo/Lan-Party-Manager.git
cd Lan-Party-Manager
# Facultatif : sans .env, le backend génère sa propre clé dans ./data/secret_key
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" > .env
docker compose up --build
```

La première compilation prend ~3 à 5 minutes (installation des dépendances Python + ffmpeg,
compilation de l'application React).

### Accès

| Service     | URL                          |
|-------------|------------------------------|
| Frontend    | http://localhost:3001        |
| API         | http://localhost:3001/api    |
| Docs de l'API | http://localhost:8000/docs — compilation depuis les sources uniquement, en boucle locale |

> Le backend n'est jamais publié sur le réseau : toutes les requêtes passent par le Nginx du
> frontend, qui plafonne la taille des requêtes et transmet l'IP du client sur laquelle reposent les
> limites de tentatives de connexion. Publier le port `8000` sur toutes les interfaces contournerait
> les deux (et les ports publiés par Docker passent devant le pare-feu de l'hôte).

> **Important :** `SECRET_KEY` signe tous les jetons de session. Laissez-la vide et le backend en génère
> une aléatoire (gardée dans `./data/secret_key`), ou fournissez la vôtre, aléatoire et d'au moins
> 32 caractères. Les valeurs d'exemple connues et les clés de moins de 16 caractères sont refusées
> au démarrage.

### Utiliser votre propre reverse proxy (Nginx, Caddy, Traefik…)

Si vous placez votre propre reverse proxy devant le conteneur `frontend` (par exemple pour
servir votre propre domaine en HTTPS), assurez-vous qu'il transmet le schéma d'origine de la
requête :

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

Le backend fait confiance à cet en-tête (`--proxy-headers`) pour construire des URLs `https://`
correctes — sans lui, toute redirection émise par FastAPI (par exemple un slash final manquant)
revient en `http://`, ce que les navigateurs et clients HTTP refusent ensuite de transmettre
avec le jeton de connexion, ce qui casse la requête suivante.

**Indiquez au frontend d'où se connecte votre proxy.** La connexion, l'inscription et la
réinitialisation de mot de passe sont limitées par IP client. Derrière un proxy, toutes les requêtes
arrivent au conteneur `frontend` depuis l'adresse du proxy : son Nginx ne croit donc que le
`X-Forwarded-For` du proxy, jamais celui d'un client, que n'importe qui pourrait falsifier pour
contourner les limites. Renseignez l'adresse du proxy sur le service `frontend` :

```yaml
  frontend:
    environment:
      LPM_TRUSTED_PROXIES: "172.16.0.0/12"   # adresses/CIDR, séparées par des espaces ou des virgules
```

La valeur par défaut, `172.16.0.0/12`, couvre un proxy qui tourne en conteneur Docker sur la même
machine (l'installation habituelle de Nginx Proxy Manager). Mettez l'adresse réseau de votre proxy
s'il tourne sur une autre machine, ou `none` si rien n'est placé devant. **Vérifiez les logs du
backend après le déploiement** : les requêtes doivent montrer les IP de vos visiteurs. Si toutes
affichent la même adresse privée, c'est celle de votre proxy : ajoutez-la ici, sinon tout le crew
partage une seule limite de connexion.

### Health checks & sauvegardes automatiques

Les deux images embarquent un `healthcheck:` (voir `docker-compose.yml`) afin que
`docker compose ps` et les orchestrateurs de conteneurs puissent distinguer une instance
bloquée d'une instance fonctionnelle — le contrôle du backend interroge réellement la base de
données (`GET /health`) plutôt que de simplement confirmer que le processus tourne. Le backend
prend aussi un instantané de la base + des fichiers uploadés dans `./data/backups/` une fois
par jour (03h00, heure locale), en conservant les 7 derniers par défaut — en plus, et non à la
place, du bouton « Exporter les données » dans Settings. Réglable ou désactivable via les
variables d'environnement `BACKUP_ENABLED` / `BACKUP_KEEP_COUNT`.

### Premier compte administrateur

Ouvrez http://localhost:3001/register — le **premier** compte inscrit devient automatiquement
**administrateur**. Toute inscription suivante nécessite un code d'invitation généré depuis un événement.

### SSO Discord (optionnel)

Pour permettre aux joueurs de se connecter avec Discord :

1. Créez une application sur [discord.com/developers](https://discord.com/developers/applications) → **OAuth2**. Copiez le **Client ID** et le **Client Secret** (l'application demande automatiquement les scopes `identify` + `email`).
2. Dans LPM, allez dans **Réglages** (admin) : renseignez `app_base_url` (section E-mail), puis, sous **Connexion Discord (SSO)**, collez le Client ID + Secret et activez-le. Le panneau affiche l'URI de redirection exacte.
3. Dans Discord → **OAuth2 → Redirects**, ajoutez cette URI exacte — `{app_base_url}/api/auth/discord/callback` — et cliquez sur **Save Changes**.

Un bouton « Continuer avec Discord » apparaît alors sur les pages de connexion et d'inscription. Les
nouveaux utilisateurs Discord ont toujours besoin d'un code d'invitation valide (sauf le premier
compte/admin) ; les comptes existants sont liés automatiquement lorsque l'e-mail vérifié de Discord
correspond. Les identifiants sont stockés en base (`app_settings`), jamais dans `.env`.

---

## Configuration

### Référence Docker Compose

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "127.0.0.1:8000:8000"   # boucle locale uniquement — ne jamais publier le backend sur le réseau
    volumes:
      - ./data:/app/data        # Base de données SQLite (persistée)
      - ./uploads:/app/uploads  # Avatars, médias, miniatures (persistés)
    environment:
      SECRET_KEY: ${SECRET_KEY:-}
      DATABASE_URL: sqlite:///./data/lanparty.db
      UPLOAD_DIR: /app/uploads

  frontend:
    build: ./frontend
    ports:
      - "3001:80"
    volumes:
      - ./uploads:/app/uploads  # Nginx sert les envois directement (sans passer par Python)
    depends_on:
      - backend
```

### Variables d'environnement

| Variable       | Défaut                         | Description                                    |
|----------------|--------------------------------|------------------------------------------------|
| `SECRET_KEY`   | *(générée)*                    | Secret de signature JWT — vide = clé aléatoire générée au premier démarrage, gardée dans `./data/secret_key` |
| `DATABASE_URL` | `sqlite:///./data/lanparty.db` | Chaîne de connexion SQLAlchemy                 |
| `UPLOAD_DIR`   | `/app/uploads`                 | Répertoire des avatars, médias et miniatures   |
| `LPM_TRUSTED_PROXIES` (frontend) | `172.16.0.0/12` | D'où se connecte votre reverse proxy — voir [Utiliser votre propre reverse proxy](#utiliser-votre-propre-reverse-proxy-nginx-caddy-traefik) |

> Les identifiants Twitch et Discord ne sont **pas** des variables d'environnement — ils sont
> stockés en base via la page **Réglages** (admin), et survivent donc aux reconstructions sans jamais
> atterrir dans `.env`.

### Données persistées

Ces répertoires hôtes sont montés comme volumes Docker et survivent aux redémarrages/reconstructions :

```
./data/      → Base de données SQLite (lanparty.db)
./uploads/   → Avatars, fichiers médias et miniatures vidéo
  ├── media/       images et vidéos envoyées
  └── thumbnails/  miniatures vidéo auto-générées (ffmpeg)
```

Créez-les avant le premier démarrage si vous voulez une propriété explicite :

```bash
mkdir -p data uploads
```

### Compilation manuelle (sans Compose)

<details>
<summary>Commandes <code>docker build</code> backend / frontend</summary>

```bash
# Backend
cd backend
docker build -t lanparty-backend .
docker run -p 127.0.0.1:8000:8000 \
  -v $(pwd)/../data:/app/data \
  -v $(pwd)/../uploads:/app/uploads \
  lanparty-backend

# Frontend
cd frontend
docker build -t lanparty-frontend .
docker run -p 3001:80 \
  -v $(pwd)/../uploads:/app/uploads \
  lanparty-frontend
```

> Le montage du volume uploads est requis pour que Nginx serve directement avatars, médias et miniatures.

</details>

---

## Développement

Lancez la stack sans Docker pour une boucle édition/rechargement rapide.

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

> Sans Docker, `ffmpeg` doit être installé pour la génération des miniatures vidéo (`apt install ffmpeg` / `brew install ffmpeg`).

### Frontend

```bash
cd frontend
npm install
npm run dev   # Serveur de dev Vite sur http://localhost:5173
```

> Le serveur de dev Vite relaie `/api` vers `http://localhost:8000` — aucune config CORS nécessaire en local.

### Tests et vérifications

```bash
cd backend && pytest -n auto               # suite de tests backend (~20 s avec xdist)
cd backend && ruff check .                 # lint backend
cd frontend && npm run test && npm run lint && npm run build
python scripts/check_i18n_parity.py        # parité des traductions EN/FR
python scripts/check_version_sync.py       # cohérence de version (16 emplacements, desktop compris)
```

---

## Référence API

Toutes les routes sont préfixées par `/api`. Documentation interactive sur `/docs` (Swagger) et `/redoc`.
Les endpoints de liste acceptent la pagination `?limit=` et `?offset=`.

### Authentification

| Méthode | Chemin                        | Accès    | Description                                                            |
|---------|-------------------------------|----------|-----------------------------------------------------------------------|
| POST    | `/api/auth/register`          | Public   | Inscription (code d'invitation + dates d'arrivée/départ requis après le premier utilisateur ; RSVP automatique dans l'événement) |
| POST    | `/api/auth/login`             | Public   | Connexion avec `identifier` (**pseudo ou e-mail**) + mot de passe, renvoie un JWT |
| GET     | `/api/auth/me`                | Requis   | Informations de l'utilisateur courant                                 |
| GET     | `/api/auth/invite-required`   | Public   | Renvoie `{ required: bool }`                                          |
| POST    | `/api/auth/forgot-password`   | Public   | Envoie un lien de réinitialisation par e-mail si l'adresse correspond à un compte (SMTP) |
| POST    | `/api/auth/reset-password`    | Public   | Définit un nouveau mot de passe à partir d'un jeton de réinitialisation valide |
| GET     | `/api/auth/discord/config`    | Public   | Renvoie `{ enabled: bool }` — le SSO Discord est-il configuré ?       |
| GET     | `/api/auth/discord/authorize` | Public   | Démarre la connexion/inscription Discord (`?code=` invitation optionnelle) |
| POST    | `/api/auth/discord/link-ticket` | Requis | Confirme le mot de passe du compte ; renvoie un ticket de 5 minutes pour `/discord/link` |
| GET     | `/api/auth/discord/link`      | Requis   | Démarre la liaison de Discord au compte courant (`code` = le ticket)  |
| DELETE  | `/api/auth/discord/link`      | Requis   | Délie Discord (refusé si le compte n'a pas de mot de passe)           |
| GET     | `/api/auth/discord/callback`  | Public   | Cible de redirection OAuth2 — finalise la connexion/liaison, renvoie le JWT |

### Utilisateurs

| Méthode | Chemin                   | Accès           | Description                       |
|---------|--------------------------|-----------------|-----------------------------------|
| GET     | `/api/users/`            | Tous            | Lister tous les utilisateurs      |
| GET     | `/api/users/{id}`        | Tous            | Récupérer un utilisateur          |
| PUT     | `/api/users/{id}`        | Soi ou admin    | Modifier le profil                |
| POST    | `/api/users/{id}/avatar` | Soi ou admin    | Envoyer un avatar (converti en WebP) |
| PUT     | `/api/users/{id}/role`   | Admin uniquement | Changer le rôle d'un utilisateur  |

### Dépenses

| Méthode | Chemin                  | Accès             | Description                                                        |
|---------|-------------------------|-------------------|-------------------------------------------------------------------|
| GET     | `/api/expenses/`        | Tous              | Lister les dépenses                                               |
| GET     | `/api/expenses/prorata` | Tous              | Répartition au prorata (`?event_id=` optionnel, par défaut l'événement à venir le plus proche) |
| POST    | `/api/expenses/`        | Trésorier / Admin | Créer une dépense                                                |
| PUT     | `/api/expenses/{id}`    | Trésorier / Admin | Modifier une dépense                                             |
| DELETE  | `/api/expenses/{id}`    | Trésorier / Admin | Supprimer une dépense                                           |

### Lots

*Optionnel — 404 pour les non-admins tant que l'option `prizes` est désactivée ; l'activer masque la Trésorerie.*

| Méthode | Chemin                      | Accès      | Description                          |
|---------|------------------------------|------------|----------------------------------------|
| GET     | `/api/prizes/`                | Tous       | Lister les lots (filtre `?event_id=`)  |
| POST    | `/api/prizes/`                | Admin uniquement | Créer un lot                    |
| POST    | `/api/prizes/{id}/photo`      | Admin uniquement | Envoyer/remplacer la photo du lot |
| PUT     | `/api/prizes/{id}`            | Admin uniquement | Modifier titre/description       |
| DELETE  | `/api/prizes/{id}`            | Admin uniquement | Supprimer un lot                 |

### Sponsors

*Optionnel — 404 pour les non-admins tant que l'option `sponsors` est désactivée.*

| Méthode | Chemin                          | Accès      | Description                                       |
|---------|----------------------------------|------------|-----------------------------------------------------|
| GET     | `/api/sponsors/`                  | Tous       | Lister les sponsors (filtre `?event_id=`)            |
| GET     | `/api/sponsors/active`            | Tous       | Sponsors de l'événement en cours/à venir             |
| POST    | `/api/sponsors/`                  | Admin uniquement | Créer un sponsor                              |
| POST    | `/api/sponsors/{id}/banner`       | Admin uniquement | Envoyer une bannière (image ou vidéo `.webm`) |
| PUT     | `/api/sponsors/{id}`              | Admin uniquement | Modifier nom/lien/ordre d'affichage           |
| DELETE  | `/api/sponsors/{id}`              | Admin uniquement | Supprimer un sponsor                          |

### Tournois

| Méthode | Chemin                                       | Accès               | Description                                  |
|---------|----------------------------------------------|---------------------|----------------------------------------------|
| GET     | `/api/tournaments/`                          | Tous                | Lister les tournois                          |
| GET     | `/api/tournaments/hall-of-fame`              | Tous                | Classement des joueurs par taux de victoire  |
| GET     | `/api/tournaments/{id}`                      | Tous                | Détail d'un tournoi                          |
| GET     | `/api/tournaments/{id}/standings`            | Tous                | Classement toutes rondes (V/D/N/Pts)         |
| POST    | `/api/tournaments/`                          | Organisateur+       | Créer un tournoi                             |
| PUT     | `/api/tournaments/{id}`                      | Organisateur / Admin | Modifier le nom ou le statut ; format et taille d'équipe tant qu'il est en attente |
| DELETE  | `/api/tournaments/{id}`                      | Organisateur / Admin | Supprimer un tournoi                        |
| POST    | `/api/tournaments/{id}/teams`                | Organisateur / Admin | Ajouter une équipe                          |
| PUT     | `/api/tournaments/{id}/teams`                | Organisateur / Admin | Remplacer toutes les équipes (tirage aléatoire), tant qu'il est en attente |
| PUT     | `/api/tournaments/{id}/teams/{team_id}`      | Organisateur / Admin | Modifier une équipe                         |
| PATCH   | `/api/tournaments/{id}/teams/{team_id}/seed` | Organisateur / Admin | Définir la tête de série                    |
| DELETE  | `/api/tournaments/{id}/teams/{team_id}`      | Organisateur / Admin | Retirer une équipe                          |
| POST    | `/api/tournaments/{id}/generate-brackets`    | Organisateur / Admin | Générer l'arbre / le calendrier toutes rondes |
| PUT     | `/api/tournaments/{id}/matches/{match_id}`   | Organisateur / Admin | Mettre à jour le score / faire avancer      |

### Événements LAN

| Méthode | Chemin                               | Accès           | Description                                                          |
|---------|--------------------------------------|-----------------|---------------------------------------------------------------------|
| GET     | `/api/events/`                       | Tous            | Lister tous les événements (enrichis avec RSVP + mes dates)         |
| POST    | `/api/events/`                       | Admin uniquement | Créer un événement (capacité optionnelle)                          |
| PUT     | `/api/events/{id}`                   | Admin uniquement | Modifier un événement                                              |
| DELETE  | `/api/events/{id}`                   | Admin uniquement | Supprimer un événement                                            |
| POST    | `/api/events/{id}/rsvp`              | Tous            | RSVP « présent » avec `{arrival_date, departure_date}` bornées à la fenêtre de l'événement ; 409 dès le premier jour |
| DELETE  | `/api/events/{id}/rsvp`              | Tous            | Passer le statut RSVP à « absent » ; 409 dès le premier jour        |
| PUT     | `/api/events/{id}/rsvps/{user_id}`   | Trésorier       | Fixer la présence d'un membre `{status, arrival_date, departure_date}` — seul moyen une fois la LAN commencée ; journalisé, membre prévenu |
| GET     | `/api/events/{id}/invite`            | Admin uniquement | Récupérer le code d'invitation de l'événement (ou `null`)          |
| POST    | `/api/events/{id}/invite`            | Admin uniquement | Générer/régénérer le code d'invitation de l'événement              |
| DELETE  | `/api/events/{id}/invite`            | Admin uniquement | Révoquer le code d'invitation de l'événement                       |
| GET     | `/api/events/invite/validate/{code}` | Public          | Valider un code — `{valid, full, event_title, event_start, event_end}` |

### Craving Chat

*Optionnel — 404 pour les non-admins tant que l'option `craving_chat` est désactivée. Réservé aux
participants confirmés (statut RSVP « présent »), et uniquement dans une fenêtre allant de 30 jours
avant l'événement à 15 jours après — en dehors de cette fenêtre, chaque route (REST et WebSocket)
répond comme si le salon n'existait pas.*

| Méthode | Chemin                                          | Accès      | Description                                                          |
|---------|----------------------------------------------------|------------|------------------------------------------------------------------------|
| GET     | `/api/chat/{event_id}/messages`                       | Participant | Les 200 derniers messages de l'événement, du plus ancien au plus récent |
| POST    | `/api/chat/{event_id}/messages`                       | Participant | Poster un message (`reply_to_id` optionnel) ; mentions @ résolues côté serveur, aperçus de liens récupérés en arrière-plan |
| PATCH   | `/api/chat/{event_id}/messages/{message_id}`          | Propriétaire | Modifier son propre message (fenêtre de 10 minutes)                   |
| DELETE  | `/api/chat/{event_id}/messages/{message_id}`          | Propriétaire | Supprimer son propre message                                          |
| POST    | `/api/chat/{event_id}/messages/{message_id}/react`    | Participant | Définir sa réaction emoji (renvoyer le même emoji l'efface)            |
| GET     | `/api/chat/{event_id}/pinned`                         | Participant | Le message actuellement épinglé de l'événement, s'il existe            |
| POST    | `/api/chat/{event_id}/pin/{message_id}`               | Admin uniquement | Épingler un message (remplace toute épingle précédente)          |
| DELETE  | `/api/chat/{event_id}/pin`                            | Admin uniquement | Désépingler                                                        |
| WS      | `/api/chat/{event_id}/ws`                             | Participant | Diffusion en direct des messages/épingle modifiés, plus le relais « en train d'écrire… ». Première trame : `{"type": "auth", "token": "<JWT>"}` (jamais dans l'URL) |

### Planification (vue calendrier)

*Optionnel — 404 pour les non-admins tant que l'option `planning` est désactivée ; les bascules par événement `can_propose`/`can_vote` filtrent en plus certaines routes.*

| Méthode | Chemin                                     | Accès | Description                                                     |
|---------|----------------------------------------------|-------|--------------------------------------------------------------------|
| GET     | `/api/planning/events/{event_id}`              | Tous  | Le tableau de planification complet — propositions, créneaux, votes |
| POST    | `/api/planning/events/{event_id}/blocks`       | Tous  | Proposer un jeu pour un créneau jour × heure                       |
| DELETE  | `/api/planning/blocks/{block_id}`              | Tous  | Retirer un créneau proposé                                         |
| PUT     | `/api/planning/blocks/{block_id}/votes`        | Tous  | Voter/changer son vote, borné par sa fenêtre RSVP                  |
| POST    | `/api/planning/blocks/{block_id}/lock`         | Tous  | L'organisateur verrouille un créneau comme choix final              |
| POST    | `/api/planning/blocks/{block_id}/unlock`       | Tous  | Déverrouiller un créneau précédemment verrouillé                    |

### Matériel BYO

*Optionnel — 404 pour les non-admins tant que l'option `gear` est désactivée.*

| Méthode | Chemin                                         | Accès      | Description                                                       |
|---------|--------------------------------------------------|------------|-----------------------------------------------------------------------|
| GET     | `/api/gear/events/{event_id}`                     | Tous       | Toute la liste de matériel d'un événement (annonces + demandes ouvertes) |
| GET     | `/api/gear/suggestions`                           | Tous       | Votre casier de matériel personnel — tout ce que vous avez déjà annoncé |
| POST    | `/api/gear/events/{event_id}/items`               | Tous       | Annoncer le matériel que vous apportez                                |
| POST    | `/api/gear/events/{event_id}/requests`            | Admin uniquement | Publier une demande (« il nous faut X ») qu'un membre peut réclamer |
| POST    | `/api/gear/events/{event_id}/carryover`           | Tous       | Reprendre en bloc votre kit habituel depuis votre casier (idempotent) |
| POST    | `/api/gear/items/{item_id}/claim`                 | Tous       | Réclamer une demande ouverte                                          |
| POST    | `/api/gear/items/{item_id}/unclaim`               | Tous       | Libérer une demande réclamée                                          |
| PUT     | `/api/gear/items/{item_id}`                       | Tous       | Modifier une annonce/demande                                          |
| DELETE  | `/api/gear/items/{item_id}`                       | Tous       | Supprimer une annonce/demande                                         |

### Checklist de préparation

*Optionnel — 404 pour les non-admins tant que l'option `checklist` est désactivée. **Privée par conception :** chaque route ne résout que « la checklist du membre qui appelle » — aucune route ne peut lire ou modifier la liste d'un autre membre, pas même pour un admin.*

| Méthode | Chemin                                              | Accès | Description                                                       |
|---------|--------------------------------------------------------|-------|------------------------------------------------------------------|
| GET     | `/api/checklist/events/{event_id}`                       | Tous  | Votre checklist pour cet événement (forme vide si rien d'enregistré) |
| PUT     | `/api/checklist/events/{event_id}`                       | Tous  | Enregistrer les 9 objets fixes + jusqu'à 10 champs personnalisés (remplace tout) |
| GET     | `/api/checklist/suggestions`                             | Tous  | Votre dernière checklist non vide provenant d'un autre événement    |
| POST    | `/api/checklist/events/{event_id}/carryover`             | Tous  | Fusionner votre liste habituelle dans la checklist de cet événement (répétable sans risque) |

### Mini-Jeux

*Optionnel — 404 pour les non-admins tant que l'option `minigames` est désactivée.*

L'enregistrement d'un score se fait en deux temps, pour qu'il puisse être vérifié plutôt que
cru sur parole : `POST /runs` enregistre une heure de début et renvoie un jeton à usage unique,
contre lequel la soumission finale est validée. Trois barrières s'appliquent — un maximum
propre au jeu, le temps réellement écoulé depuis l'ouverture de la partie, et des règles de
cohérence propres au jeu (pour *Neon Survivor*, le numéro de vague est une fonction pure du
score : tout autre couple est une charge forgée). Cela arrête l'opportuniste qui ouvre la
console ; ce n'est pas une preuve contre un attaquant motivé, ce qui supposerait de rejouer la
simulation côté serveur. Le `DELETE` admin est le garde-fou honnête.

Tout ce qui est propre à un jeu — ce que compte `score`, son plafond, son sens de tri — vit
dans `backend/minigames_registry.py`. Ajouter un jeu, c'est une entrée là plus un dossier sous
`frontend/public/games/<slug>/` : aucune migration, aucun nouvel endpoint.

| Méthode | Chemin                                   | Accès | Description                                                    |
|---------|------------------------------------------|-------|----------------------------------------------------------------|
| GET     | `/api/minigames/games`                   | Tous  | Le registre — slug, métrique classée, plafond, sens de tri      |
| POST    | `/api/minigames/runs`                    | Tous  | Ouvrir une partie classée ; renvoie un jeton à usage unique     |
| POST    | `/api/minigames/runs/{token}/submit`     | Tous  | Soumettre une partie finie (validée, jeton consommé quoi qu'il arrive) |
| GET     | `/api/minigames/leaderboard?game=`       | Tous  | Meilleure partie par joueur, la meilleure d'abord — une ligne par joueur |
| GET     | `/api/minigames/me/best?game=`           | Tous  | Votre propre record sur un jeu                                  |
| DELETE  | `/api/minigames/scores/{score_id}`       | Admin | Supprimer une entrée aberrante à la main                        |

### Streams

| Méthode | Chemin                     | Accès               | Description                                |
|---------|----------------------------|---------------------|--------------------------------------------|
| GET     | `/api/streams/`            | Tous                | Lister les streams                         |
| GET     | `/api/streams/live-status` | Tous                | Récupérer le statut en direct via l'API Twitch Helix |
| POST    | `/api/streams/`            | Tous                | Ajouter un stream (nom de chaîne ou URL de clip) |
| PUT     | `/api/streams/{id}`        | Propriétaire / Admin | Modifier un stream                        |
| DELETE  | `/api/streams/{id}`        | Propriétaire / Admin | Supprimer un stream                       |

### Média

| Méthode | Chemin                   | Accès               | Description                                              |
|---------|--------------------------|---------------------|---------------------------------------------------------|
| GET     | `/api/media/`            | Tous                | Lister les médias (filtre `?event_id=` supporté)        |
| POST    | `/api/media/upload`      | Tous                | Envoyer une image ou une vidéo (max 100 Mo) ; miniatures ffmpeg |
| POST    | `/api/media/bulk-delete` | Admin uniquement    | Supprimer plusieurs éléments par liste d'ID             |
| DELETE  | `/api/media/{id}`        | Propriétaire / Admin | Supprimer un média                                     |

### Ma configuration

*Optionnel — 404 tant que l'option `setup` est désactivée. Chaque route d'écriture passe par `/me` — il n'existe aucune route d'écriture `/{user_id}` : la règle « seul le propriétaire » est imposée par la structure même des URL, pas par une vérification de rôle.*

| Méthode | Chemin                              | Accès           | Description                                                        |
|---------|---------------------------------------|-----------------|------------------------------------------------------------------------|
| GET     | `/api/setup/shared`                     | Public (jeton)  | Une configuration via son jeton de partage public — sans connexion, limité en fréquence |
| GET     | `/api/setup/me`                         | Tous            | Votre propre configuration (forme vide si rien d'enregistré)            |
| PUT     | `/api/setup/me`                         | Tous            | Enregistrer les 14 composants + champs personnalisés                    |
| POST    | `/api/setup/me/photos`                  | Tous            | Ajouter une photo (jusqu'à 5)                                            |
| PATCH   | `/api/setup/me/photos/{photo_id}`       | Tous            | Légender une photo (vide pour effacer)                                  |
| DELETE  | `/api/setup/me/photos/{photo_id}`       | Tous            | Supprimer une photo                                                      |
| GET     | `/api/setup/me/share`                   | Tous            | Votre lien de partage public actuel, s'il existe                        |
| POST    | `/api/setup/me/share`                   | Tous            | Créer/renouveler votre lien de partage public                           |
| DELETE  | `/api/setup/me/share`                   | Tous            | Révoquer votre lien de partage public                                   |
| GET     | `/api/setup/{user_id}`                  | Tous            | Voir la configuration d'un autre membre dans l'app                       |
| POST    | `/api/setup/{user_id}/react`            | Tous            | Réagir avec un emoji à la config d'un membre                            |

### Rétrospective d'après-événement

*Optionnel — 404 pour les non-admins tant que l'option `recap` est désactivée. Les chiffres financiers apparaissent pour les membres connectés (si la Trésorerie est active) mais jamais dans la version partagée publiquement.*

| Méthode | Chemin                              | Accès      | Description                                                      |
|---------|----------------------------------------|------------|----------------------------------------------------------------------|
| GET     | `/api/recap/shared`                     | Public (jeton) | Une rétrospective via son jeton de partage public — sans connexion, sans montants |
| GET     | `/api/recap/{event_id}`                 | Tous       | Rétrospective complète pour un membre — champion, MVP, nuits, photos, dépenses |
| GET     | `/api/recap/{event_id}/share`           | Admin uniquement | Lien de partage public actuel, s'il existe                    |
| POST    | `/api/recap/{event_id}/share`           | Admin uniquement | Créer/renouveler le lien de partage public de l'événement     |
| DELETE  | `/api/recap/{event_id}/share`           | Admin uniquement | Révoquer le lien de partage public de l'événement              |

### Kiosque / Grand écran

*Optionnel — la lecture `/summary` n'est autorisée que par un jeton kiosque révocable (comparaison en temps constant), jamais par un JWT personnel : sans risque de laisser tourner sur un projecteur partagé.*

| Méthode | Chemin                     | Accès            | Description                                                    |
|---------|------------------------------|------------------|--------------------------------------------------------------------|
| GET     | `/api/kiosk/admin`             | Admin uniquement | État actuel du kiosque (jeton créé ? activé ?)                     |
| POST    | `/api/kiosk/admin/token`       | Admin uniquement | Générer/renouveler le jeton kiosque (invalide toute ancienne URL)   |
| DELETE  | `/api/kiosk/admin/token`       | Admin uniquement | Effacer le jeton — aucune URL kiosque ne fonctionne tant qu'un nouveau n'est pas créé |
| GET     | `/api/kiosk/summary`           | Public (jeton)   | Tout ce que l'affichage projecteur fait défiler, en un seul appel   |

### Annonces et présence

| Méthode | Chemin                       | Accès      | Description                                                       |
|---------|--------------------------------|------------|------------------------------------------------------------------------|
| GET     | `/api/announcements/`            | Tous       | Annonces actuellement actives (les expirées sont filtrées)              |
| POST    | `/api/announcements/`            | Admin uniquement | Publier une annonce (relais Discord optionnel)                   |
| DELETE  | `/api/announcements/{id}`        | Admin uniquement | Supprimer/masquer une annonce                                    |
| POST    | `/api/presence/ping`             | Tous       | Heartbeat du navigateur — alimente la liste « qui est en ligne » du HUB |

### Courses

*Optionnel — 404 tant que le drapeau `groceries` est désactivé.*

| Méthode | Chemin                                        | Accès                          | Description                                                        |
|---------|-----------------------------------------------|--------------------------------|--------------------------------------------------------------------|
| GET     | `/api/groceries/events/{event_id}`            | Tous                           | Toute la liste de l'événement en un appel                          |
| POST    | `/api/groceries/events/{event_id}/items`      | Tous                           | Ajouter un article, en désignant éventuellement qui l'achète       |
| POST    | `/api/groceries/events/{event_id}/import`     | Tous                           | Ajouter des articles en masse (l'import CSV)                       |
| PUT     | `/api/groceries/items/{item_id}`              | Créateur, acheteur désigné ou admin | Modifier nom, catégorie, quantité, acheteur, ou cocher comme acheté |
| DELETE  | `/api/groceries/items/{item_id}`              | Créateur, acheteur désigné ou admin | Retirer un article                                            |

### Ludothèque

*Optionnel — 404 tant que le drapeau `games` est désactivé. L'import Steam demande un compte Steam lié depuis le profil (`/api/auth/steam/link`).*

| Méthode | Chemin                                     | Accès | Description                                                             |
|---------|--------------------------------------------|-------|-------------------------------------------------------------------------|
| GET     | `/api/games/catalog`                       | Tous  | Le catalogue partagé (titres de base + chaque ajout personnalisé)       |
| GET     | `/api/games/me`                            | Tous  | Ma ludothèque, ma liste de souhaits et mes filtres                      |
| PUT     | `/api/games/me/filters`                    | Tous  | Enregistrer mes filtres                                                 |
| POST    | `/api/games/me/library`                    | Tous  | Ajouter un jeu à ma ludothèque                                          |
| PUT     | `/api/games/me/library/{game_id}`          | Tous  | Modifier une entrée (nombre de joueurs, …)                              |
| PUT     | `/api/games/me/library/{game_id}/favorite` | Tous  | Mettre ou retirer le favori                                             |
| DELETE  | `/api/games/me/library/{game_id}`          | Tous  | Retirer un jeu de ma ludothèque                                         |
| POST    | `/api/games/me/wishlist`                   | Tous  | Ajouter un jeu à ma liste de souhaits                                   |
| DELETE  | `/api/games/me/wishlist/{game_id}`         | Tous  | L'en retirer                                                            |
| GET     | `/api/games/matches`                       | Tous  | Chaque autre membre, classé par jeux en commun avec moi                 |
| POST    | `/api/games/session`                       | Tous  | Les jeux possédés par tous les membres listés, avec le plafond de joueurs du groupe |
| POST    | `/api/games/me/import-steam`               | Tous  | Importer mes jeux Steam dans ma ludothèque                              |

### Trophées

*Optionnel — 404 tant que le drapeau `trophies` est désactivé. Les éditions en brouillon restent réservées aux admins jusqu'à la révélation.*

| Méthode | Chemin                                            | Accès            | Description                                                              |
|---------|---------------------------------------------------|------------------|--------------------------------------------------------------------------|
| GET     | `/api/trophies/`                                  | Admin uniquement | Toute la vitrine, trophées archivés en dernier                           |
| POST    | `/api/trophies/`                                  | Admin uniquement | Créer un trophée                                                         |
| PUT     | `/api/trophies/{trophy_id}`                       | Admin uniquement | Modifier un trophée                                                      |
| DELETE  | `/api/trophies/{trophy_id}`                       | Admin uniquement | Supprimer un trophée que personne n'a encore gagné (sinon il est archivé) |
| POST    | `/api/trophies/{trophy_id}/image`                 | Admin uniquement | Envoyer son image                                                        |
| DELETE  | `/api/trophies/{trophy_id}/image`                 | Admin uniquement | Retirer son image                                                        |
| GET     | `/api/trophies/events/{event_id}`                 | Tous             | Les trophées d'un événement, tels que le lecteur peut les voir           |
| POST    | `/api/trophies/events/{event_id}`                 | Admin uniquement | Ajouter une édition de trophée à un événement                            |
| PATCH   | `/api/trophies/editions/{edition_id}`             | Admin uniquement | Modifier une édition                                                     |
| DELETE  | `/api/trophies/editions/{edition_id}`             | Admin uniquement | Supprimer une édition                                                    |
| PUT     | `/api/trophies/editions/{edition_id}/winners`     | Admin uniquement | Fixer les vainqueurs à la main                                           |
| POST    | `/api/trophies/editions/{edition_id}/vote`        | Tous             | Voter — un bulletin par membre et par édition, une relance ne compte jamais deux fois |
| POST    | `/api/trophies/editions/{edition_id}/reveal`      | Admin uniquement | Révéler les vainqueurs                                                   |
| POST    | `/api/trophies/events/{event_id}/open-votes`      | Admin uniquement | Ouvrir les votes des éditions d'un événement                             |
| POST    | `/api/trophies/events/{event_id}/close-votes`     | Admin uniquement | Clore tous les votes ouverts et proposer les vainqueurs                  |
| POST    | `/api/trophies/events/{event_id}/nudge`           | Admin uniquement | Relancer les participants qui n'ont pas encore voté                      |
| GET     | `/api/trophies/ballot`                            | Tous             | Mes votes ouverts, ou `null` (interrogé par les onglets ouverts)         |
| GET     | `/api/trophies/users/{user_id}`                   | Tous             | Les trophées révélés d'un membre, événement le plus récent en premier    |

### League of Legends (capture par l'application de bureau)

*Optionnel — 404 tant que le drapeau `lol_stats` est désactivé. Les parties sont envoyées par la capture de l'application de bureau, jamais saisies à la main.*

| Méthode | Chemin                          | Accès               | Description                                                                 |
|---------|---------------------------------|---------------------|-----------------------------------------------------------------------------|
| POST    | `/api/lol/matches`              | Tous, 30 par heure  | Envoyer une partie capturée. Les valeurs sont bornées (K/D/A, dégâts, durée, 10 joueurs au plus) et la partie ne compte pour un membre que si sa propre application l'a envoyée |
| GET     | `/api/lol/capture-status`       | Tous                | Ce que l'application de bureau d'un membre interroge pour savoir si elle doit capturer (répond même drapeau éteint, pour que l'application s'arrête) |
| GET     | `/api/lol/stats`                | Tous                | Statistiques agrégées (`?event_id=`, ou globales)                           |
| GET     | `/api/lol/matches`              | Tous                | Parties capturées (`?event_id=`)                                            |
| DELETE  | `/api/lol/matches/{match_id}`   | Admin uniquement    | Retirer une partie qui ne devrait pas compter (un test, un remake) ; audité |

### XP et niveaux

*Optionnel — 404 tant que le drapeau `xp` est désactivé. Dérivé à la lecture des tournois, présences, chat et médias ; le registre est mis en cache 30 s par processus et invalidé par toute écriture qui compte.*

| Méthode | Chemin                      | Accès | Description                                                                 |
|---------|-----------------------------|-------|-----------------------------------------------------------------------------|
| GET     | `/api/xp/crew`              | Tous  | L'XP et le niveau de chaque membre actif, du meilleur au dernier (classement du Hub) |
| GET     | `/api/xp/users/{user_id}`   | Tous  | L'XP d'un membre avec son détail                                            |

### Cartes et boosters

*Optionnel — 404 tant que le drapeau `cards` est désactivé ; nécessite l'XP.*

| Méthode | Chemin                                     | Accès | Description                                                                          |
|---------|--------------------------------------------|-------|--------------------------------------------------------------------------------------|
| GET     | `/api/cards/me`                            | Tous  | Mes boosters non ouverts, après attribution de ce que j'ai gagné depuis ma dernière visite |
| POST    | `/api/cards/boosters/buy`                  | Tous  | Acheter un booster avec l'XP dépensable ; 409 quand le solde ne couvre plus         |
| POST    | `/api/cards/boosters/{booster_id}/open`    | Tous  | Révéler les cartes d'un booster dans l'ordre des emplacements (l'Épique en dernier) ; une seconde ouverture est refusée |
| GET     | `/api/cards/collection/{user_id}`          | Tous  | La collection d'un membre, visible par tout le crew                                  |

### Contrat mensuel

*Optionnel — 404 tant que le drapeau `quests` est désactivé, et seulement avec l'XP activée.*

| Méthode | Chemin                  | Accès | Description                                                                      |
|---------|-------------------------|-------|----------------------------------------------------------------------------------|
| GET     | `/api/quests/current`   | Tous  | Le contrat du mois et ma progression (le premier regard du mois le crée)         |

### Réglages, Activité, Audit et Sauvegarde

| Méthode | Chemin                | Accès           | Description                                                                  |
|---------|-----------------------|-----------------|------------------------------------------------------------------------------|
| GET     | `/api/settings/`      | Admin uniquement | Lister tous les réglages configurables                                      |
| PUT     | `/api/settings/{key}` | Admin uniquement | Enregistrer un réglage (twitch_client_id/secret, discord_oauth_enabled/client_id/client_secret, …) |
| GET     | `/api/activity/`      | Tous            | Fil d'activité paginé (`?limit=`)                                            |
| GET     | `/api/audit/`         | Admin uniquement | Journal d'audit admin paginé                                                |
| GET     | `/api/backup/export`  | Admin uniquement | Télécharger un `tar.gz` de la BDD + du dossier uploads (instantané SQLite cohérent ; `X-Backup-Estimate` porte la taille) |
| GET     | `/api/backup/storage` | Admin uniquement | Espace disque du volume des envois                                           |
| POST    | `/api/backup/import`  | Admin uniquement | Restaurer une archive d'`/export` (corps brut `application/gzip`) : remplace BDD + envois, puis redémarre le backend |

---

## Rôles et permissions

| Rôle        | Capacités                                                                                        |
|-------------|--------------------------------------------------------------------------------------------------|
| `admin`     | Tout — gestion des utilisateurs, rôles, invitations, dépenses, tournois, réglages, journal d'audit |
| `treasurer` | Créer / modifier / supprimer des dépenses ; consulter toutes les données                         |
| `user`      | Consulter toutes les données ; gérer son propre profil ; RSVP aux événements ; participer aux tournois |

Le premier compte inscrit est automatiquement promu `admin`.

---

## Répartition des coûts au prorata

Les dépenses sont réparties proportionnellement au nombre de nuits de présence de chaque participant :

```
nuits(utilisateur) = date_depart - date_arrivee
part(utilisateur)  = nuits(utilisateur) / total_nuits * total_depenses
```

Les dates sont définies **par événement**, pas globalement : indiquez RSVP « présent » sur la page
**LAN Party** et confirmez vos dates d'arrivée/départ dans la fenêtre de l'événement pour apparaître
dans sa répartition. L'onglet Prorata de la Trésorerie permet de choisir l'événement à répartir (par
défaut le plus proche à venir) et d'exporter le résultat en CSV.

---

## Dépannage

**Port déjà utilisé** — changez le port hôte dans `docker-compose.yml` :
```yaml
ports:
  - "127.0.0.1:8001:8000"   # backend (boucle locale uniquement)
  - "3002:80"     # frontend
```

**Réinitialiser la base de données**
```bash
docker compose down
rm -rf data/
docker compose up
```

**Reconstruire après modification du code**
```bash
docker compose up --build          # normal
docker compose build --no-cache    # à partir de zéro
```

**Consulter les logs**
```bash
docker compose logs -f backend
docker compose logs -f frontend
```

**Discord « Invalid OAuth2 redirect_uri »** — l'URI enregistrée dans le portail Discord doit
correspondre **exactement** à `{app_base_url}/api/auth/discord/callback` (même schéma, hôte, port,
sans slash final), et vous devez cliquer sur **Save Changes** dans Discord.

**ARM / Raspberry Pi** — le Dockerfile backend installe les bibliothèques natives de Pillow
(`libjpeg-dev`, `zlib1g-dev`, `libpng-dev`) et `ffmpeg`, toutes disponibles pour ARM64 (Pi 4/5) via
les dépôts Debian standard. La compilation fonctionne sans modification sur ARM64.

---

## Application de bureau (Windows)

Un client Windows natif dans la zone de notification, pour les équipes qui préfèrent ne pas garder
un onglet de navigateur ouvert — même connexion, tout identique, plus les notifications natives et
les mises à jour automatiques.

- **La même appli, dans une vraie fenêtre.** Une coquille [Tauri](https://tauri.app/) demande une
  fois l'URL de votre instance (comme choisir un espace de travail Slack), puis embarque l'appli web
  telle quelle — aucune interface séparée à maintenir.
- **Reste connectée.** Jetons à session glissante de 30 jours ; pas de reconnexion quotidienne.
- **Vit dans la zone de notification.** Se réduit au lieu de quitter ; notifications Windows natives
  pour les nouveaux tournois, médias, mises à jour de planification et demandes de matériel, avec des
  bascules par catégorie, et un clic sur une notification ouvre directement la page concernée.
- **Le SSO Discord** s'ouvre dans votre navigateur système plutôt que dans une fenêtre intégrée, et
  reprend automatiquement la main une fois connecté.
- **Se met à jour automatiquement** une fois installée — vérifie une fois par lancement, aucun
  téléchargement manuel par la suite.

Un installeur Windows signé (`LPM_Desktop_v<version>_x64.msi`) est publié sur
[lanpartymanager.com](https://lanpartymanager.com/fr/) — la section Desktop du site renvoie vers la
version courante. Une fois installée, l'application consulte
`https://lanpartymanager.com/assets/desktop/latest.json` à chaque lancement et n'accepte qu'une mise à
jour dont la signature correspond à la clé publique compilée dedans. Le code source se trouve dans
[`desktopapp/`](../desktopapp/) — voir [`desktopapp/README.md`](../desktopapp/README.md) (en anglais)
pour compiler et lancer depuis les sources :

```powershell
cd desktopapp
npm install
npm run dev
```

---

## Structure du projet

```
Lan-Party-Manager/
├── docker-compose.yml
├── data/                      # BDD SQLite (auto-créée, gitignored)
├── uploads/                   # Avatars, médias, miniatures (auto-créés, gitignored)
│
├── backend/
│   ├── Dockerfile             # python:3.11-slim + libs Pillow + ffmpeg
│   ├── requirements.txt
│   ├── main.py                # App FastAPI, middleware, migrations au démarrage
│   ├── database.py            # Moteur SQLAlchemy, session, mode WAL SQLite
│   ├── models.py              # Modèles ORM
│   ├── schemas.py             # Schémas Pydantic (requêtes/réponses)
│   ├── auth.py                # Helpers JWT, hachage des mots de passe, sentinelle sans mot de passe
│   ├── oauth_discord.py       # Client OAuth2 Discord + helpers d'état signé (SSO)
│   ├── activity.py            # Helpers journal d'activité + audit
│   ├── prorata.py             # Logique de calcul au prorata (par événement)
│   ├── link_preview.py        # Récupère titre/description/image pour un lien partagé dans le chat
│   ├── alembic/               # Migrations de schéma (versionnées)
│   ├── router_auth.py         # /api/auth (connexion pseudo/e-mail, garde d'invitation, SSO Discord, reset mdp)
│   ├── router_users.py        # /api/users
│   ├── router_expenses.py     # /api/expenses (prorata prend ?event_id=)
│   ├── router_prizes.py       # /api/prizes (optionnel, remplace la Trésorerie une fois activé)
│   ├── router_sponsors.py     # /api/sponsors (bannières optionnelles : image/webm + lien)
│   ├── router_tournaments.py  # /api/tournaments (toutes rondes, classements, Panthéon, têtes de série)
│   ├── router_events.py       # /api/events (RSVP avec dates, capacité, codes d'invitation par événement)
│   ├── router_chat.py         # /api/chat (Craving Chat optionnel : messages, réactions, épingle, WebSocket)
│   ├── router_planning.py     # /api/planning (proposition/vote/verrouillage optionnels)
│   ├── router_gear.py         # /api/gear (matériel BYO optionnel : annonces, demandes, casier)
│   ├── router_checklist.py    # /api/checklist (checklist de préparation privée, optionnelle)
│   ├── router_minigames.py    # /api/minigames (optionnel, jetons de partie + classement)
│   ├── minigames_registry.py  # Métrique, plafond et validation par jeu — ajouter un jeu ici
│   ├── router_streams.py      # /api/streams (détection de clips, statut Twitch en direct)
│   ├── router_media.py        # /api/media (filtre par événement, réactions, suppression groupée)
│   ├── router_setup.py        # /api/setup (vitrine « Ma configuration » optionnelle + lien public)
│   ├── router_recap.py        # /api/recap (rétrospective d'après-événement optionnelle + lien public)
│   ├── router_kiosk.py        # /api/kiosk (affichage projecteur optionnel, autorisé par jeton)
│   ├── router_announcements.py# /api/announcements (bannière PA admin + relais Discord)
│   ├── router_presence.py     # /api/presence (heartbeat navigateur, qui est en ligne)
│   ├── router_groceries.py    # /api/groceries (optionnel, liste de courses par événement)
│   ├── router_games.py        # /api/games (optionnel : ludothèque, souhaits, import Steam, recherche)
│   ├── router_trophies.py     # /api/trophies (optionnel : trophées, éditions, votes, révélation)
│   ├── router_lol.py          # /api/lol (optionnel, parties LoL capturées par l'application de bureau)
│   ├── router_xp.py           # /api/xp (optionnel, XP et niveaux dérivés à la lecture — xp.py)
│   ├── router_cards.py        # /api/cards (optionnel, cartes et boosters — cards.py)
│   ├── router_quests.py       # /api/quests (optionnel, contrat mensuel — quests.py)
│   ├── router_settings.py     # /api/settings
│   ├── router_activity.py     # /api/activity
│   ├── router_audit.py        # /api/audit
│   ├── router_backup.py       # /api/backup
│   ├── mailer.py               # Client SMTP — e-mails de réinitialisation de mot de passe
│   └── discord_notify.py       # Webhook Discord — annonces + rappels RSVP
│
├── frontend/
    ├── Dockerfile             # build node:20-alpine → service nginx:alpine
    ├── nginx.conf             # fallback SPA, proxy /api, service direct /uploads
    ├── package.json
    └── src/
        ├── App.tsx            # Routeur, contexte d'auth, Layout partagé
        ├── contexts/          # AuthContext, AppConfigContext
        ├── lib/api.ts         # Client Axios + toutes les fonctions API
        ├── types/index.ts     # Interfaces TypeScript
        ├── i18n/              # Setup i18next + fichiers de langue EN/FR
        ├── hooks/             # useActivityFeed, useCravingChat (WebSocket), usePresenceHeartbeat, useNoindex
        ├── components/
        │   ├── Navbar.tsx     # Nav responsive ; liens filtrés par fonctionnalité ; Réglages + Audit réservés aux admins
        │   ├── Footer.tsx
        │   ├── TournamentBracket.tsx
        │   ├── ProRataTable.tsx
        │   ├── ChecklistSection.tsx  # Widget de checklist de préparation (page détail événement)
        │   ├── CravingChatSection.tsx # Liste de bulles de chat — mentions, réponses, réactions, épingle, recherche (Hub + page dédiée)
        │   ├── MiniGames.tsx        # Sélecteur de jeu + jeu intégré + classement (onglet Arène)
        │   ├── AnnouncementsManager.tsx # Admin : composer/expirer la bannière PA
        │   ├── KioskManager.tsx      # Admin : créer/révoquer le jeton kiosque
        │   ├── MediaReactions.tsx    # Réactions emoji (partagé entre Média et Ma configuration)
        │   └── ui/            # QRModal, Lightbox, DiscordButton, LanguageToggle, …
        └── pages/
            ├── Login.tsx          # Pseudo/e-mail + mot de passe, saisie rapide d'invitation, SSO Discord
            ├── Register.tsx       # Validation du code d'invitation, contexte d'événement, dates RSVP, SSO Discord
            ├── ForgotPassword.tsx # Demander un lien de réinitialisation par e-mail
            ├── ResetPassword.tsx  # Définir un nouveau mot de passe depuis un jeton de réinitialisation
            ├── DiscordComplete.tsx # Atterrissage OAuth2 — lit le JWT depuis le fragment d'URL, puis redirige
            ├── Dashboard.tsx      # Roster de l'équipe, fil d'activité, panthéon, Craving Chat intégré
            ├── CravingChatPage.tsx # Page de chat plein écran dédiée, accessible depuis l'icône de la Navbar
            ├── Profile.tsx        # Avatar, t-shirt, rôles, liaison Discord, Ma configuration, événements à venir
            ├── PlayerProfile.tsx  # Profil d'un coéquipier dans l'app (configuration, sponsors, stats)
            ├── Events.tsx         # RSVP avec dates, affichage de la capacité, codes d'invitation admin
            ├── EventDetailPage.tsx # Matériel, Checklist, Planification, Sponsors pour un événement
            ├── Planning.tsx       # Heatmap jour × heure pour proposer/voter, verrouillage organisateur
            ├── Finances.tsx       # Dépenses + export CSV au prorata
            ├── Prizes.tsx         # Tableau des lots par événement (photo + description)
            ├── Tournaments.tsx    # Classements toutes rondes + interface de têtes de série
            ├── Streams.tsx        # Intégrations clips + chaînes, badge en direct, bascule chat
            ├── Media.tsx          # Filtre par événement, réactions, suppression groupée, miniatures vidéo
            ├── RecapPage.tsx      # Page de temps forts d'après-événement (+ SharedRecapPage, par jeton)
            ├── SharedSetupPage.tsx # Vue publique de « Ma configuration » via lien de partage
            ├── Kiosk.tsx          # Affichage projecteur en lecture seule, autorisé par jeton
            ├── Settings.tsx       # Admin : Twitch + SSO Discord, SMTP, devise, bascules de fonctionnalités, sauvegarde
            └── AuditLog.tsx       # Admin : journal d'audit
│
└── desktopapp/                # Client Windows dans la zone de notification (Tauri) — voir « Application de bureau » ci-dessus
    ├── ui/                     # la coquille embarquée — écran URL serveur, panneau de réglages
    └── src-tauri/              # Rust : fenêtre/zone de notification, sondage d'activité, SSO Discord, mise à jour auto
```

---

## Localisation

Toute l'interface est disponible en **français et en anglais**, commutable depuis la barre de
navigation (et depuis les pages Connexion/Inscription pour les invités). Le choix de langue est
conservé dans `localStorage`. Les traductions se trouvent dans `frontend/src/i18n/locales/{en,fr}.json`,
et l'intégration continue impose une parité totale des clés entre les deux via `scripts/check_i18n_parity.py`.

---

## Licence

Distribué sous **licence publique générale GNU Affero v3.0 (AGPL-3.0)** — voir [LICENSE](../LICENSE).
(Les versions jusqu'à la 1.3.2 étaient en GPL-2.0 ; le passage en AGPL-3.0 commence avec la 1.3.3.)
