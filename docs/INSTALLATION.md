# Installation Options

> **Note:** This project consists of two parts — a backend API (FastAPI) and a frontend UI (Vite). You can choose to run them together using Docker Compose, or separately from source code.

---

## Option 1: Run with Docker Compose (Recommended for Beginners)

This is the easiest way to get started — no need to install Node.js or Python manually!

### Prerequisites
- [Docker](https://www.docker.com/get-started/) installed on your machine
- A text editor (optional, just for editing environment variables)

### Steps

1. **Clone the repository**
     #### Git:
      ```bash
      git clone <your-repo-url>
      cd <repo-folder>
      ```
     #### Zip:
     Download the zip from the release page and extract in some folder
  
3. **Configure the variables**
   Open `compose.yml` and update the `VITE_API_URL` environment variable to match the ip/domain of the machine in which the app is running:
   ```yaml
   VITE_API_URL: http://localhost:6767
   ```
   **Change Download Variables** (optional) 
   By default the app saves data into the root folder where the docker compose lives.
   You can change the folder mapped to thi changing the values in the compose file.
   ```
   volumes:
      - YOURFOLDERPATH:/root/Music/OnTheSpot
      - YOURFOLDERPATH:/root/Videos/OnTheSpot
      - YOURFOLDERPATH:/root/.config/onthespot
   ```   

5. **Start the containers**
   From the project root, run:
   ```bash
   docker compose up --build
   ```

6. **Access the application**
   - Frontend: `http://yourip:6768`
   - Backend AP DocsI: `http://yourip:6767/docs`

7. **Stop when done** (optional)
   you won't loose data, only the download queue list.
   ```bash
   docker compose down
   ```

---

## Option 2: Run from Source Code

If you prefer to run the app directly on your machine, follow these steps.

### Prerequisites
- [Node.js](https://nodejs.org/) (v18 or higher)
- [uv](https://docs.astral.sh/uv/) — a fast Python package installer and resolver

### Backend API (`/api`)

1. Open a terminal in the `/api` folder:
   ```bash
   cd /path/to/project/api
   uv run fastapi run
   ```

2. The backend will start on `http://localhost:6767`.

### Frontend UI (`/ui`)

You have two options to run the frontend:

#### A. Development Mode (with hot-reload)
```bash
cd /path/to/project/ui
npm run dev
```
This runs Vite in development mode with live reload — great for testing changes.

#### B. Production Build
```bash
npm run build
npm run preview
```
This builds the app and serves it locally on `http://localhost:4173`.

### Running Detached (Background)

If you want to run the app in the background without keeping a terminal open, use platform-specific commands. **Note:** This is not recommended for development — only do this if you need to free up your terminal for other tasks.

- **Linux/macOS**
  ```bash
  # Backend (in /api)
  uv run fastapi run &

  # Frontend (in /ui)
  npm run dev > output.log 2>&1 &
  ```

- **Windows PowerShell**
  ```powershell
  # Backend (in api folder)
  uv run fastapi run | Out-File -FilePath "backend.log"

  # Frontend (in ui folder)
  npm run dev >> output.log 2>&1 &
  ```

> ⚠️ **Warning:** Detached processes may not restart automatically if your computer goes to sleep or crashes. Always use Docker Compose for production deployments!

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `VITE_APP_URL` is undefined in the frontend | Check that `compose.yml` has the correct environment variable set |
| Backend won't start | Ensure Python 3.10+ and uv are installed; run `uv sync` first |
| Frontend shows blank page | Verify the VITE_API_URL is correct |
| Docker containers fail to build | Run `docker compose pull` to refresh images, then rebuild |

---

## Need Help?

- Check the [README](../README.md) for more details about the project architecture.
- Open an issue on GitHub if you encounter a bug or have questions!
