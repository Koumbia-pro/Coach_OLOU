# Coach OLOU
Site personnel statique en français, sept pages de contenu responsive et une page 404, créé à partir du brief de conception et du portfolio fournis.

## Contenu
Accueil, parcours, quatre expertises, interventions, entreprises et projets filtrables, trois fiches pratiques, contact.

## Contacts et fonctionnement
Email euloge@oloustream.com et WhatsApp +226 64 09 31 96 issus du CV fourni. Le formulaire prépare un email via mailto et propose l’ouverture de la messagerie ou la copie du message ; aucun envoi serveur ni stockage de prospects. Les champs obligatoires et le format email sont vérifiés par le navigateur.

## Points à valider avant ouverture publique
- Coordonnées reprises du CV 2024.
- Chiffres d’impact repris du brief : 6 800 personnes et entreprises, 90 conférences et ateliers, 7 pays. Expérience actualisée à 17+ ans selon le contexte fourni.
- Portrait extrait du portfolio 2024 ; à remplacer si une photo plus récente est souhaitée.
- Ajouter la vidéo de présentation, des photos de conférences et d’éventuels témoignages lorsque fournis. Aucun témoignage inventé.
- Les trois fiches ressources sont de nouveaux brouillons éditoriaux, sans dates ni attribution à des publications antérieures.
- Aucun identifiant Analytics, Pixel Meta ou calendrier de réservation fourni : aucun de ces services n'est connecté.
- Aucune liaison au domaine eulogeolou.com effectuée.
- `dist/.htaccess` et `dist/_headers` fournissent des protections HTTP pour Apache et les hébergeurs compatibles avec `_headers`.
- `check_site.py` vérifie les fichiers, les liens locaux, les IDs et les éléments obligatoires avant publication.

## Édition
Les pages publiques sont dans dist. build_content.py génère le contenu commun et les pages ; dist/style.css et dist/site.js contiennent le style et les interactions. Aucun CMS tiers n'est installé ; modifications via Sites.
