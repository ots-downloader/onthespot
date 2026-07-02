# Installation Options

## 1. Docker Compose (Universal)

   - Install Docker
   - Download the repo 
   - Eedit the VITE_APP_URL environment variable in `compose.yml`
   - From the same folder open a terminal and run `docker compose up` to start the containers
   - Enjoy


## 2. Run The App From Source

If you prefer to run OnTheSpot yourself, follow these steps.

1. **Download the Source Code**

   - Install NodeJS and uv
   - Open a terminal from the folder /api and run
   `uv run fastapi run`
   - Open another terminal from /ui and run
   `npm run dev`
   - or 
   - `npm run build` and after `npm run preview`

   there are various methods to run detached depending on your plaltform, but it's not suggested so no guide will be provided.
