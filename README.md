# FortiOS 7.6.7 KB POC

POC pour construire une KB **traçable** à partir de plusieurs sources, sans considérer Ansible ou Terraform comme vérité unique.

## Sources pincées pour le POC

- Fortinet Ansible Collection: **2.6.0** (tag GitHub), qui ajoute le support de FortiOS 7.6.7.
- Fortinet Terraform provider: **1.26.0**.
- Fortinet CLI Reference: **7.6.7**.
- Fortinet Administration Guide: **7.6.7**.
- FortiOS 7.6.7 Release Notes.
- New Features page pour 7.6.7.

Les tags/commits sont enregistrés dans `metadata.yaml` afin que le build soit reproductible.

## Ce que le POC fait

1. Clone les versions GitHub pincées.
2. Extrait `versioned_schema` des modules Ansible **avec filtrage v_range pour 7.6.7**.
3. Extrait le schéma des resources Terraform (types, contraintes simples, champs imbriqués).
4. Crawl les pages Fortinet d'une version et extrait:
   - pages CLI `config ...` et tableaux Parameter/Type/Size/Default;
   - topics Administration Guide et références CLI détectées dans les exemples;
   - Release Notes et New Features.
5. Réconcilie les sections par identifiant canonique.
6. Ne masque pas les conflits: ils sont enregistrés dans chaque section et dans l'audit.
7. Génère `audit/report.yaml` et `audit/report.md`.

## Installation Windows / PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_poc.py --docs-max-pages 100
```

Pour un crawl complet (attention: beaucoup de pages et plus lent):

```powershell
python run_poc.py --docs-max-pages 0
```

Pour tester d'abord uniquement GitHub/Ansible/Terraform:

```powershell
python run_poc.py --skip-docs
```

## Sortie

```text
knowledge_base/fortios/7.6.7/
├── metadata.yaml
├── raw/
│   ├── ansible/
│   ├── terraform/
│   └── docs/
│       ├── cli_reference/
│       ├── features/admin_topics.yaml
│       └── version/
├── canonical/
└── audit/
    ├── report.yaml
    └── report.md
```

## Important

Ce POC est volontairement prudent:

- Ansible donne un schéma versionné très riche (`v_range`, options, enfants).
- Terraform sert de seconde source structurée, notamment pour des contraintes.
- Le CLI Reference officiel est prioritaire pour la projection canonique quand il est disponible.
- Les divergences restent visibles dans `conflicts`.
- L'Administration Guide sert à construire progressivement la couche *features/dépendances*, pas à inventer de la syntaxe CLI.

Le POC ne prétend pas qu'une KB est “correcte” parce qu'elle contient beaucoup d'attributs. L'audit est obligatoire avant de passer au hardware.
