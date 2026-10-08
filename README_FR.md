<div align="center">

<img src="assets/images/favicon_LPM.png" alt="Logo LAN Party Manager" width="200" height="200" />

# LAN Party Manager

**Le QG auto-hébergé de vos week-ends LAN.**
Invitations, brackets, frais partagés, photos, hype sur grand écran — sur une machine à vous.

[![Version](https://img.shields.io/badge/version-1.3.5-FF3D00?style=flat-square)](#)
[![Licence](https://img.shields.io/badge/licence-AGPL--3.0-4C566A?style=flat-square)](LICENSE)
[![Plateforme](https://img.shields.io/badge/plateforme-amd64%20%7C%20arm64%20(Pi%204%2F5)-555?style=flat-square)](#)
[![Docker](https://img.shields.io/badge/Docker-multi--arch-2496ED?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/r/crosswax/lanpartymanager-backend)
[![i18n](https://img.shields.io/badge/i18n-FR%20%7C%20EN-3B82F6?style=flat-square)](#)

[Site web](https://lanpartymanager.com/fr/) · [Docker Hub](https://hub.docker.com/r/crosswax/lanpartymanager-backend) · [App desktop](https://lanpartymanager.com/fr/#desktop) · [Doc technique complète](docs/README_FR.md) · [English version](README.md)

</div>

---

## L'histoire d'origine

On organise des LAN parties **depuis 2015**. À force, l'organisation était devenue un
deuxième boulot : un tableur pour l'argent, un fil Discord pour les RSVP, un tableau blanc
pour le bracket, et les photos prises en otage sur le téléphone de quelqu'un.

On jouait plus au **Simulateur de Tableur** qu'aux vrais jeux.

LPM règle ça. Une seule app, sur votre propre machine, qui suit tout le week-end : qui
vient et quand, qui doit quoi, qui a gagné, qui apporte le projecteur, et quelle photo de
la pizza a récolté le plus de 🔥. **Pas de cloud, aucun compte à créer, pas de télémétrie,
pas d'abonnement.** Le chaos de votre équipe reste chez vous.

## Ce qu'il y a dans la boîte

| | |
|---|---|
| 🎟️ **Invitations & RSVP** | Codes d'invitation par événement (partageables en QR, révocables). Les dates d'arrivée/départ alimentent tout le reste. |
| 🏆 **Tournois** | Brackets à élimination directe & round-robins, en équipe ou en solo, pour n'importe quel jeu. Les scores entrent, le classement sort, le champion passe sur grand écran. |
| 💸 **Trésorerie** | Partage des frais au prorata des *nuits réellement passées*. Le débat « qui doit quoi », enterré pour de bon. |
| 📸 **Médiathèque** | Galerie photo/vidéo partagée, réactions emoji et miniatures vidéo. |
| 📺 **Kiosque grand écran** | Une page projecteur autorisée par jeton : matchs en cours, arrivées, mur de photos, cérémonies de trophées avec confettis. |
| 🗓️ **Planning** | Proposez des créneaux, votez, verrouillez le programme. Le projecteur affiche le compte à rebours du prochain. |
| 🎮 **Et le reste** | Streams Twitch, connexion et annonces Discord, checklist matériel (« qui apporte le switch ? »), courses, trophées, récap d'après-LAN… **29 fonctionnalités**, chacune désactivable. |

Bilingue **FR/EN**, au choix de chaque joueur. Visite complète sur le [site](https://lanpartymanager.com/fr/).

## Installation (~10 minutes)

Il vous faut [Docker](https://docs.docker.com/get-docker/). Un portable, un PC qui traîne
ou un **Raspberry Pi 4/5** suffisent largement — les images existent en amd64 et arm64.

### Option A — Docker Compose

```bash
mkdir lanpartymanager && cd lanpartymanager
```

Créez `docker-compose.yml` :

```yaml
services:
  backend:
    image: crosswax/lanpartymanager-backend:latest
    # Pas de ports: — le Nginx du frontend le joint via le réseau Docker.
    volumes:
      - ./data:/app/data        # Base SQLite (persistée)
      - ./uploads:/app/uploads  # Avatars, médias, miniatures vidéo (persistés)
    environment:
      # Facultatif : vide, LPM génère sa propre clé au premier démarrage
      # et la garde dans ./data/secret_key.
      SECRET_KEY: ${SECRET_KEY:-}
      DATABASE_URL: sqlite:///./data/lanparty.db
      UPLOAD_DIR: /app/uploads
    restart: unless-stopped

  frontend:
    image: crosswax/lanpartymanager-frontend:latest
    ports:
      - "3001:80"
    environment:
      # D'où votre reverse proxy (Nginx Proxy Manager, Caddy…) se connecte.
      # La valeur par défaut couvre un proxy Docker sur la même machine.
      LPM_TRUSTED_PROXIES: "172.16.0.0/12"
    volumes:
      - ./uploads:/app/uploads  # Nginx sert les uploads directement
    depends_on:
      - backend
    restart: unless-stopped
```

```bash
docker compose up -d
```

Ouvrez **http://localhost:3001** — GG, c'est en ligne.

### Option B — Stack Portainer

Collez le même YAML comme stack Portainer. Portainer transforme silencieusement
`${VAR:-défaut}` en valeur *vide* — depuis la 1.3.4, c'est sans danger pour `SECRET_KEY` :
LPM génère sa propre clé et la garde dans `./data/secret_key`. Ce qui reste dangereux,
c'est de coller une valeur d'exemple : le backend refuse les clés d'exemple connues et
tout ce qui fait moins de 16 caractères, et le 502 nginx qui en résulte ressemble à s'y
méprendre à « la connexion est cassée ». Demandez-nous comment on le sait.

### Première connexion

Le **premier compte créé devient admin**. Tous les suivants entrent avec un code
d'invitation que vous générez par événement — partageable en QR, révocable à tout moment.
Les sauvegardes (base + uploads) se font en un clic dans les Réglages, la restauration aussi.

## App desktop (Windows) 🖥️

Pour les équipes qui n'ont pas envie de garder un onglet ouvert : un client natif dans la
barre des tâches qui embarque **votre** instance — même connexion, même tout.

- Pointez-le une fois vers l'URL de votre serveur, comme on choisit un espace Slack.
- Toasts natifs pour les matchs, annonces et trophées. Un clic, et vous êtes sur la page.
- Stats **League of Legends** capturées automatiquement pendant la LAN.
- Se met à jour tout seul entre deux éditions.

**[Télécharger l'installeur →](https://lanpartymanager.com/fr/#desktop)** (Windows 10/11, x64, .msi)

## Pour aller plus loin 🤿

La documentation technique complète — configuration, référence API, rôles & permissions,
le calcul du prorata, dépannage, structure du projet — vit dans
**[docs/README_FR.md](docs/README_FR.md)**.

Les questions qui piquent (« Pourquoi SQLite ? », « Ça sent le vibecodé ? », « Une image
backend de 250 Mo ? ») ont leurs réponses franches dans la
**[FAQ du site](https://lanpartymanager.com/fr/#faq)**.

## Licence

**AGPL-3.0** — voir [LICENSE](LICENSE). Les versions jusqu'à la 1.3.2 étaient en private-testing ;
le passage en AGPL-3.0 commence avec la 1.3.3. Faites-la tourner, forkez-la,
améliorez-la — si vous servez une version modifiée à votre équipe, partagez vos
changements. C'est le deal.

## Contribuer

Les issues sont les bienvenues — bugs, idées, récits de « ça a planté pendant notre LAN ».
Les pull requests ne sont pas acceptées pour l'instant : ce dépôt public reçoit un
instantané de chaque version, et le développement se fait ailleurs, donc une PR ne
pourrait de toute façon pas être fusionnée telle quelle.

---

<div align="center">

Fait par **[CrossWax](https://www.crosswax.net)** avec une bande d'habitués des LANs —
construit d'abord pour nos propres week-ends, énormément accéléré par
[Claude Code](https://claude.com/claude-code) depuis juillet 2026.
**Maintenant allez fragger, le tableur est géré.**

</div>
