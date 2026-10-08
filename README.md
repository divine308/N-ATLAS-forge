# N-ATLAS Forge

N-ATLAS Forge is a developer platform built around N-ATLAS for building, testing, evaluating, adapting, and integrating AI-powered applications.

Forge gives developers a structured workspace for managing projects, working with datasets, testing model behaviour, running evaluations, experimenting with N-ATLAS, working with speech recognition, and integrating AI capabilities into applications.

## Repositories

### Backend

https://github.com/divine308/N-ATLAS-forge

### Frontend

https://github.com/divine308/N-ATLAS-forge-frontend

## Live Application

**Frontend:**
https://n-atlas-forge-frontend.vercel.app

**Backend API:**
https://n-atlas-forge.onrender.com

**API Documentation:**
https://n-atlas-forge.onrender.com/docs

## What Forge Provides

N-ATLAS Forge is designed as a developer-facing environment rather than a single-purpose AI application.

Developers can create projects, organize project resources, work with datasets, run evaluation suites, test model behaviour, inspect evaluation results, perform crash testing, use N-ATLAS through the playground, and integrate Forge capabilities into their own applications.

The platform separates the frontend experience from the backend API, allowing the development environment to communicate with the Forge services through authenticated REST APIs.

## Technology Stack

### Backend

* Python
* FastAPI
* SQLAlchemy
* Pydantic
* PostgreSQL
* JWT authentication
* llama.cpp
* N-ATLAS
* N-ATLAS ASR
* Hugging Face Transformers
* PyTorch
* librosa

### Frontend

* React 19
* Vite
* React Router
* Tailwind CSS
* Lucide React
* Highlight.js
* PrismJS
* react-simple-code-editor

### Infrastructure

* Vercel for the frontend
* Render for the backend
* PostgreSQL for persistent application data
* Local GGUF inference for N-ATLAS where the model is available

## Core Features

### Project Management

Create and manage development projects with project-level authorization and workspace isolation.

Projects provide the foundation for organizing development resources and working with project-specific data.

### N-ATLAS Playground

Interact with N-ATLAS through the Forge development environment and experiment with model-powered workflows.

The playground is designed to provide a direct development surface for working with N-ATLAS rather than requiring developers to build a separate interface for every experiment.

### Datasets

Upload, inspect, manage, version, and download datasets used during development and evaluation.

Dataset management includes support for working with records and dataset versions through the Forge API.

### Evaluations

Create evaluation suites and cases, execute evaluation runs, inspect results, and identify regressions in model behaviour.

The evaluation system is intended to make model testing repeatable rather than relying entirely on manual inspection.

### Crash Testing

Run controlled tests against projects and inspect failures during development.

This provides a dedicated workflow for identifying problems before integrating AI functionality into a production application.

### ASR

Forge includes speech recognition capabilities through the N-ATLAS ASR integration.

Audio can be processed through the ASR service and exposed through the Forge API.

### SDK

Forge provides SDK-related resources for integrating applications with the platform and its APIs.

### Authentication and Authorization

The backend uses bearer-token authentication with JWT-based authorization.

Protected project resources use project-level authorization to prevent users from accessing resources belonging to other projects.

## Architecture

N-ATLAS Forge uses a separated frontend/backend architecture.

```text
┌──────────────────────────────┐
│        React Frontend        │
│       Vite + Tailwind        │
└──────────────┬───────────────┘
               │
               │ REST API
               │ Bearer Token
               ▼
┌──────────────────────────────┐
│        FastAPI Backend       │
│                              │
│ Authentication               │
│ Projects                     │
│ Playground                   │
│ Datasets                     │
│ Evaluations                  │
│ Crash Testing                │
│ ASR                          │
│ SDK                          │
└───────┬───────────┬──────────┘
        │           │
        ▼           ▼
   PostgreSQL    N-ATLAS
                 / ASR
```

The backend is organized into API routers, core configuration and database modules, and service modules responsible for N-ATLAS execution and other application functionality.

The frontend communicates with the backend through REST APIs.

## Model Deployment

The N-ATLAS GGUF model is intentionally **not included in this Git repository**.

The model file, `N-ATLaS-GGUF-Q4_K_M.gguf`, is approximately **597 MB**. Keeping a model of this size inside the normal Git repository would make cloning, versioning, and repository distribution unnecessarily heavy.

The application therefore expects the model to be supplied separately through the configured model path:

```env
NATLAS_MODEL_PATH=./N-ATLaS-GGUF-Q4_K_M.gguf
```

When the model is available, the local N-ATLAS provider can load it through the configured `llama.cpp` integration.

This repository contains the complete application code, API implementation, model integration, configuration, and execution logic required to use the model when it is supplied to the runtime environment.

The deployed Render environment is primarily used to demonstrate the Forge backend, authentication, project management, datasets, evaluations, API infrastructure, and other platform functionality. Full local N-ATLAS inference requires an execution environment with sufficient memory for the model.

The N-ATLAS model setup and execution workflow are demonstrated as part of the project documentation and demo.

## Running Locally

### Clone the Repository

```bash
git clone https://github.com/divine308/N-ATLAS-forge.git
cd N-ATLAS-forge
```

### Create a Virtual Environment

```bash
python -m venv venv
```

### Activate the Environment

On Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

On Windows Command Prompt:

```cmd
venv\Scripts\activate
```

On macOS/Linux:

```bash
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment Variables

Create a `.env` file in the backend root directory and configure the required values.

### Start the Development Server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at:

```text
http://127.0.0.1:8000
```

Interactive Swagger API documentation:

```text
http://127.0.0.1:8000/docs
```

ReDoc documentation:

```text
http://127.0.0.1:8000/redoc
```

## Environment Variables

A typical production configuration looks like:

```env
APP_ENV=production
DEBUG=false

DATABASE_URL=your_database_url

JWT_SECRET_KEY=your_secret_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

FRONTEND_URL=https://n-atlas-forge-frontend.vercel.app

NATLAS_LOCAL_ENABLED=true
NATLAS_MODEL_PATH=./N-ATLaS-GGUF-Q4_K_M.gguf
NATLAS_CONTEXT_SIZE=4096
NATLAS_THREADS=4
NATLAS_BATCH_SIZE=128
NATLAS_GPU_LAYERS=0

HF_TOKEN=your_huggingface_token

ASR_CACHE_DIR=./models/asr
ASR_DEVICE=cpu
ASR_MAX_AUDIO_SIZE_MB=25
ASR_SAMPLE_RATE=16000
ASR_CHUNK_LENGTH_S=30
ASR_STRIDE_LENGTH_S=5
```

Environment variable names should match the configuration expected by the version of Forge being deployed.

### Security

Never commit sensitive environment variables to Git.

Do not commit:

* `.env` files
* JWT secrets
* Database credentials
* Hugging Face tokens
* API keys
* Private authentication credentials
* Model credentials

Use environment variables provided by the deployment platform for production secrets.

## API

The FastAPI backend exposes REST endpoints under `/api/v1`.

Major API areas include:

```text
/api/v1/auth
/api/v1/projects
/api/v1/playground
/api/v1/datasets
/api/v1/evaluations
/api/v1/crash-test
/api/v1/asr
/api/v1/sdk
```

The complete interactive API reference is available through Swagger:

https://n-atlas-forge.onrender.com/docs

## Health Check

The backend exposes:

```text
GET /health
```

Example response:

```json
{
  "status": "healthy",
  "service": "natlas-forge-api",
  "environment": "production",
  "natlas_configured": true
}
```

The health endpoint provides a quick way to verify that the API is running and reports whether an N-ATLAS execution configuration is currently available.

## Production Deployment

The current deployment uses:

**Frontend**

Vercel

```text
https://n-atlas-forge-frontend.vercel.app
```

**Backend**

Render

```text
https://n-atlas-forge.onrender.com
```

**Database**

PostgreSQL

The frontend uses the following environment variable:

```env
VITE_BACKEND_URL=https://n-atlas-forge.onrender.com
```

The Render backend starts with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The backend must bind to `0.0.0.0` in the Render environment so that the service is externally accessible.

## Frontend Setup

The frontend repository is available at:

https://github.com/divine308/N-ATLAS-forge-frontend

Clone it separately:

```bash
git clone https://github.com/divine308/N-ATLAS-forge-frontend.git
cd N-ATLAS-forge-frontend
```

Install dependencies:

```bash
npm install
```

Configure the backend URL:

```env
VITE_BACKEND_URL=http://127.0.0.1:8000
```

Start the development server:

```bash
npm run dev
```

For production deployment, set:

```env
VITE_BACKEND_URL=https://n-atlas-forge.onrender.com
```

## Development Workflow

A typical Forge development workflow is:

```text
Create Project
      ↓
Add Project Resources
      ↓
Work With Data
      ↓
Experiment With N-ATLAS
      ↓
Run Tests / Evaluations
      ↓
Inspect Results
      ↓
Identify Regressions
      ↓
Integrate Into Application
```

The platform is structured so that development, testing, evaluation, and integration can happen within the same environment.

## Project Status

N-ATLAS Forge is actively being developed.

The current platform includes the core developer workspace, authentication, project management, datasets, evaluations, API infrastructure, ASR integration, SDK resources, and N-ATLAS execution infrastructure.

Some deployment environments may not have sufficient resources for local model inference. This does not affect the availability of the underlying Forge application and development infrastructure.

## Contributing

Contributions, improvements, testing, and feedback are welcome.

Before submitting changes, ensure that:

* The application starts successfully.
* API routes continue to work.
* Authentication and authorization remain intact.
* Sensitive credentials are not committed.
* New functionality is documented where appropriate.

## License

This project is currently maintained by the N-ATLAS Forge development team.
