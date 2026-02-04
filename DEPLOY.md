# Desplegament MENAG Generator

## Opcio 1: Render.com (Recomanat - Gratuit)

1. Crea un compte a [render.com](https://render.com)
2. Connecta el teu repositori GitHub
3. Crea un nou "Web Service"
4. Selecciona el repositori
5. Render detectara automaticament el `render.yaml`
6. Fes clic a "Create Web Service"

L'aplicacio estara disponible a: `https://menag-generator.onrender.com`

## Opcio 2: Railway.app

1. Crea un compte a [railway.app](https://railway.app)
2. Connecta el teu repositori GitHub
3. Railway detectara automaticament que es una app Python
4. Desplega automaticament

## Opcio 3: Heroku

1. Instal·la Heroku CLI
2. Executa:
   ```bash
   heroku login
   heroku create menag-generator
   git push heroku main
   ```

## Configuracio Post-Desplegament

1. Ves a `/settings` a l'aplicacio desplegada
2. Introdueix les teves API keys:
   - Anthropic API Key (per Claude)
   - Google API Key (per Gemini)
3. Ja pots generar presentacions!

## Notes Importants

- Les API keys es guarden a la base de dades SQLite local
- El disc persistent (Render) guarda les dades entre desplegaments
- El cost de cada presentacio es mostra automaticament
- Totes les estadistiques es guarden a `/stats`
