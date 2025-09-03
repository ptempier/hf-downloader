# Hugging Face Model Downloader & Manager

Interface web Flask pour télécharger et gérer des modèles Hugging Face avec suivi temps réel.

## Vue d'ensemble

**Objectif** : Interface web simple pour télécharger des modèles HF et les gérer localement
**Architecture** : Application Flask unique avec Socket.IO pour temps réel
**Déploiement** : Support des sous-dossiers (configurable via `base_url`)

## Fonctionnalités

- **Téléchargement** : Modèles HF avec filtres de quantification, progress bar temps réel
- **Gestion** : Navigation, groupement, mise à jour, suppression des modèles
- **Interface** : Deux pages (Download/Manage) avec navigation par onglets

## Structure du projet

```
/
├── app.py                 # Serveur principal Flask + Socket.IO
├── model_manager.py       # Logique scan/update/delete modèles
├── templates/
│   ├── index.html         # Page téléchargement
│   ├── model_manager.html # Page gestion
│   └── _shared_header.html# Header commun avec navigation
└── static/
    ├── script.js          # Frontend téléchargement
    └── model_manager.js   # Frontend gestion
```

## Configuration importante

**Base URL** : Variable `base_url` dans `app.py` pour déploiement sous-dossier
```python
base_url = "/hf-downloader"  # Pour https://example.com/hf-downloader/
base_url = ""                # Pour https://example.com/ (racine)
```

**Répertoire modèles** : `/models/` (hardcodé dans le code)

## Fichiers clés

### Backend
- `app.py` : Routes Flask (/download, /manage, /api/*), gestion Socket.IO, logique téléchargement
- `model_manager.py` : Fonctions `scan_models()`, `update_model_func()`, `delete_model_func()`

### Frontend
- `script.js` / `model_manager.js` : Gestion Socket.IO avec support sous-dossiers, logique UI
- Templates HTML : Configuration dynamique des chemins selon `base_url`

### Points techniques critiques
- **Socket.IO** : Path personnalisé pour sous-dossiers (`/base_url/socket.io`)
- **Téléchargement** : Subprocess isolé pour éviter RecursionError
- **Groupement** : Regroupement automatique des fichiers modèles (safetensors, GGUF, etc.)

## Installation

```bash
pip install -r requirements.txt
mkdir -p /models
python app.py
```

Accès : http://localhost:5000/[base_url]/

## Requirements principaux

- Flask, Flask-SocketIO
- huggingface_hub
- eventlet (async mode Socket.IO)

## Usage API

- `POST /download` : Démarre téléchargement
- `GET /api/models` : Liste modèles
- `POST /api/models/update` : Met à jour modèle
- `POST /api/models/delete` : Supprime modèle

