<div align="center">

<img src="assets/images/favicon_LPM.png" alt="Logo LAN Party Manager" width="200" height="200" />

# LAN Party Manager

**Gestion d'événements auto-hébergée pour LAN parties** — invitations, tournois, trésorerie,
médias et streams en direct, le tout sur votre propre matériel. D'un Raspberry Pi à un NUC.

Site officiel : https://www.lanpartymanager.com

[![Version](https://img.shields.io/badge/version-1.7.0--beta-FF3D00?style=flat-square)](#)
[![Licence](https://img.shields.io/badge/licence-GPL--2.0-4C566A?style=flat-square)](LICENSE)
[![Plateforme](https://img.shields.io/badge/plateforme-amd64%20%7C%20arm64%20(Pi%204%2F5)-555?style=flat-square)](#)
[![Docker](https://img.shields.io/badge/Docker-multi--arch-2496ED?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/r/crosswax/lanpartymanager-backend)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20FR-3B82F6?style=flat-square)](#localisation)

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/)

`BETA 1.7.0`

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
- [Structure du projet](#structure-du-projet)
- [Localisation](#localisation)
- [Licence](#licence)

---

## Fonctionnalités

| | |
|---|---|
| **Connexion flexible** | Connectez-vous avec **votre pseudo ou votre e-mail** ; **SSO Discord** optionnel pour une connexion et une inscription en un clic. Les joueurs lient/délient Discord depuis leur profil ; les admins le configurent dans les Réglages. |
| **Gestion de l'équipe** | Inscription protégée par un code d'invitation par événement (6 caractères, places liées à la capacité de l'événement) ; profils, tailles de t-shirt, avatars WebP. |
| **Calendrier des LAN** | Planifiez des événements avec dates, lieu, description et capacité optionnelle ; RSVP avec dates d'arrivée/départ bornées à la fenêtre de l'événement et décompte en direct des participants ; code d'invitation partageable par QR pour chaque événement. |
| **Planification (vue calendrier)** | Proposez des jeux pour un événement et **votez sur les heures** pour y jouer via une heatmap jour × heure — dans les limites de la présence de chacun — puis un organisateur **verrouille** le planning. Deux bascules indépendantes (proposer / voter). Optionnel. |
| **Trésorerie** | Suivi des dépenses par catégorie, **répartition automatique au prorata** selon les nuits de présence, règlement entre pairs (P2P) et export CSV en un clic. |
| **Arène / Tournois** | Événements par équipe ou solo/individuel ; **arbres à élimination directe et toutes rondes** (classement V/D/N/Pts) ; têtes de série par équipe ; suivi des scores en direct ; **signalement des scores depuis le téléphone** (les joueurs signalent, l'organisateur confirme) ; vue plein écran de l'arbre pour la projection. |
| **Streams en direct** | Intégration des chaînes **et clips** Twitch ; statut en direct + nombre de spectateurs via l'API Twitch Helix ; iframe de chat optionnelle. |
| **Galerie média** | Espace photo/vidéo partagé ; envois taggés par événement ; suppression groupée (admin) ; miniatures vidéo générées par ffmpeg ; lightbox intégrée. |
| **Activité et Panthéon** | Fil des 20 événements les plus récents sur le tableau de bord, plus un classement des joueurs par taux de victoire issu des tournois terminés. |
| **Annonces et présence** | **Bannière PA** admin (info/alerte, expiration auto, relais Discord optionnel) affichée dans toute l'app ; la liste du HUB montre **qui est en ligne** via un heartbeat léger du navigateur. |
| **Journal d'audit** | Trace réservée aux admins des actions sensibles (création/suppression d'événements et de tournois) avec auteur et horodatage. |
| **Réglages admin** | Identifiants Twitch + SSO Discord, devise, activation des fonctionnalités optionnelles, et sauvegarde en un clic de la BDD + envois au format `tar.gz`. |
| **Accès par rôle** | Rôles Admin, Trésorier et Utilisateur appliqués côté serveur pour chaque route — pas seulement masqués dans l'interface. |

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
- Ports `3001` et `8000` libres sur votre hôte

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
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    environment:
      SECRET_KEY: change-me-to-a-long-random-string
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

### Option B — Compilation depuis les sources

```bash
git clone <url-de-votre-depot>
cd LANPARTYMANAGER
echo "SECRET_KEY=change-me-to-a-long-random-string" > .env
docker compose up --build
```

La première compilation prend ~3 à 5 minutes (installation des dépendances Python + ffmpeg,
compilation de l'application React).

### Accès

| Service     | URL                          |
|-------------|------------------------------|
| Frontend    | http://localhost:3001        |
| API         | http://localhost:8000        |
| Docs de l'API | http://localhost:8000/docs |

> **Important :** définissez toujours une `SECRET_KEY` robuste — elle signe tous les jetons JWT.

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
      - "8000:8000"
    volumes:
      - ./data:/app/data        # Base de données SQLite (persistée)
      - ./uploads:/app/uploads  # Avatars, médias, miniatures (persistés)
    environment:
      SECRET_KEY: ${SECRET_KEY:-lanparty-secret-CHANGE-ME}
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
| `SECRET_KEY`   | `lanparty-secret-CHANGE-ME`    | Secret de signature JWT — **à changer**        |
| `DATABASE_URL` | `sqlite:///./data/lanparty.db` | Chaîne de connexion SQLAlchemy                 |
| `UPLOAD_DIR`   | `/app/uploads`                 | Répertoire des avatars, médias et miniatures   |

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
docker run -p 8000:8000 \
  -e SECRET_KEY=your-secret \
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
cd backend && pytest                       # suite de tests backend
python scripts/check_i18n_parity.py        # parité des traductions EN/FR
python scripts/check_version_sync.py       # cohérence de version entre les fichiers
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
| GET     | `/api/auth/discord/config`    | Public   | Renvoie `{ enabled: bool }` — le SSO Discord est-il configuré ?       |
| GET     | `/api/auth/discord/authorize` | Public   | Démarre la connexion/inscription Discord (`?code=` invitation optionnelle) |
| GET     | `/api/auth/discord/link`      | Requis   | Démarre la liaison de Discord au compte courant                       |
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

### Tournois

| Méthode | Chemin                                       | Accès               | Description                                  |
|---------|----------------------------------------------|---------------------|----------------------------------------------|
| GET     | `/api/tournaments/`                          | Tous                | Lister les tournois                          |
| GET     | `/api/tournaments/hall-of-fame`              | Tous                | Classement des joueurs par taux de victoire  |
| GET     | `/api/tournaments/{id}`                      | Tous                | Détail d'un tournoi                          |
| GET     | `/api/tournaments/{id}/standings`            | Tous                | Classement toutes rondes (V/D/N/Pts)         |
| POST    | `/api/tournaments/`                          | Organisateur+       | Créer un tournoi                             |
| PUT     | `/api/tournaments/{id}`                      | Organisateur / Admin | Modifier le nom ou le statut                |
| DELETE  | `/api/tournaments/{id}`                      | Organisateur / Admin | Supprimer un tournoi                        |
| POST    | `/api/tournaments/{id}/teams`                | Tous                | Ajouter une équipe                           |
| PUT     | `/api/tournaments/{id}/teams/{team_id}`      | Tous                | Modifier une équipe                          |
| PATCH   | `/api/tournaments/{id}/teams/{team_id}/seed` | Organisateur / Admin | Définir la tête de série                    |
| DELETE  | `/api/tournaments/{id}/teams/{team_id}`      | Tous                | Retirer une équipe                           |
| POST    | `/api/tournaments/{id}/generate-brackets`    | Organisateur / Admin | Générer l'arbre / le calendrier toutes rondes |
| PUT     | `/api/tournaments/{id}/matches/{match_id}`   | Organisateur / Admin | Mettre à jour le score / faire avancer      |

### Événements LAN

| Méthode | Chemin                               | Accès           | Description                                                          |
|---------|--------------------------------------|-----------------|---------------------------------------------------------------------|
| GET     | `/api/events/`                       | Tous            | Lister tous les événements (enrichis avec RSVP + mes dates)         |
| POST    | `/api/events/`                       | Admin uniquement | Créer un événement (capacité optionnelle)                          |
| PUT     | `/api/events/{id}`                   | Admin uniquement | Modifier un événement                                              |
| DELETE  | `/api/events/{id}`                   | Admin uniquement | Supprimer un événement                                            |
| POST    | `/api/events/{id}/rsvp`              | Tous            | RSVP « présent » avec `{arrival_date, departure_date}` bornées à la fenêtre de l'événement |
| DELETE  | `/api/events/{id}/rsvp`              | Tous            | Passer le statut RSVP à « absent »                                  |
| GET     | `/api/events/{id}/invite`            | Admin uniquement | Récupérer le code d'invitation de l'événement (ou `null`)          |
| POST    | `/api/events/{id}/invite`            | Admin uniquement | Générer/régénérer le code d'invitation de l'événement              |
| DELETE  | `/api/events/{id}/invite`            | Admin uniquement | Révoquer le code d'invitation de l'événement                       |
| GET     | `/api/events/invite/validate/{code}` | Public          | Valider un code — `{valid, full, event_title, event_start, event_end}` |

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

### Réglages, Activité, Audit et Sauvegarde

| Méthode | Chemin                | Accès           | Description                                                                  |
|---------|-----------------------|-----------------|------------------------------------------------------------------------------|
| GET     | `/api/settings/`      | Admin uniquement | Lister tous les réglages configurables                                      |
| PUT     | `/api/settings/{key}` | Admin uniquement | Enregistrer un réglage (twitch_client_id/secret, discord_oauth_enabled/client_id/client_secret, …) |
| GET     | `/api/activity/`      | Tous            | Fil d'activité paginé (`?limit=`)                                            |
| GET     | `/api/audit/`         | Admin uniquement | Journal d'audit admin paginé                                                |
| GET     | `/api/backup/export`  | Admin uniquement | Télécharger un `tar.gz` de la BDD + du dossier uploads                       |

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
  - "8001:8000"   # backend
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

## Structure du projet

```
LANPARTYMANAGER/
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
│   ├── alembic/               # Migrations de schéma (versionnées)
│   ├── router_auth.py         # /api/auth (connexion pseudo/e-mail, garde d'invitation, SSO Discord)
│   ├── router_users.py        # /api/users
│   ├── router_expenses.py     # /api/expenses (prorata prend ?event_id=)
│   ├── router_tournaments.py  # /api/tournaments (toutes rondes, classements, Panthéon, têtes de série)
│   ├── router_events.py       # /api/events (RSVP avec dates, capacité, codes d'invitation par événement)
│   ├── router_streams.py      # /api/streams (détection de clips, statut Twitch en direct)
│   ├── router_media.py        # /api/media (filtre par événement, suppression groupée)
│   ├── router_settings.py     # /api/settings
│   ├── router_activity.py     # /api/activity
│   ├── router_audit.py        # /api/audit
│   └── router_backup.py       # /api/backup
│
└── frontend/
    ├── Dockerfile             # build node:20-alpine → service nginx:alpine
    ├── nginx.conf             # fallback SPA, proxy /api, service direct /uploads
    ├── package.json
    └── src/
        ├── App.tsx            # Routeur, contexte d'auth, Layout partagé
        ├── contexts/          # AuthContext, AppConfigContext
        ├── lib/api.ts         # Client Axios + toutes les fonctions API
        ├── types/index.ts     # Interfaces TypeScript
        ├── i18n/              # Setup i18next + fichiers de langue EN/FR
        ├── components/
        │   ├── Navbar.tsx     # Nav responsive ; liens Réglages + Audit réservés aux admins
        │   ├── Footer.tsx
        │   ├── TournamentBracket.tsx
        │   ├── ProRataTable.tsx
        │   └── ui/            # QRModal, Lightbox, DiscordButton, LanguageToggle, …
        └── pages/
            ├── Login.tsx          # Pseudo/e-mail + mot de passe, saisie rapide d'invitation, SSO Discord
            ├── Register.tsx       # Validation du code d'invitation, contexte d'événement, dates RSVP, SSO Discord
            ├── DiscordComplete.tsx # Atterrissage OAuth2 — lit le JWT depuis le fragment d'URL, puis redirige
            ├── Dashboard.tsx      # Roster de l'équipe, fil d'activité, panthéon
            ├── Profile.tsx        # Avatar, t-shirt, rôles, liaison Discord, événements à venir
            ├── Events.tsx         # RSVP avec dates, affichage de la capacité, codes d'invitation admin
            ├── Finances.tsx       # Dépenses + export CSV au prorata
            ├── Tournaments.tsx    # Classements toutes rondes + interface de têtes de série
            ├── Streams.tsx        # Intégrations clips + chaînes, badge en direct, bascule chat
            ├── Media.tsx          # Filtre par événement, suppression groupée, miniatures vidéo
            ├── Settings.tsx       # Admin : Twitch + SSO Discord, devise, sauvegarde
            └── AuditLog.tsx       # Admin : journal d'audit
```

---

## Localisation

Toute l'interface est disponible en **français et en anglais**, commutable depuis la barre de
navigation (et depuis les pages Connexion/Inscription pour les invités). Le choix de langue est
conservé dans `localStorage`. Les traductions se trouvent dans `frontend/src/i18n/locales/{en,fr}.json`,
et l'intégration continue impose une parité totale des clés entre les deux via `scripts/check_i18n_parity.py`.

---

## Licence

Distribué sous **licence publique générale GNU v2.0** — voir [LICENSE](LICENSE).
