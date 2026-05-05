# ⚛ QuantumGlobe

QuantumGlobe is a sophisticated 3D web application that merges a Quantum Climate Circuit (QCC) and Quantum Machine Learning (QML) models with real-time weather APIs to provide a "quantum-enhanced" meteorological intelligence platform.

## Features

- **3D Interactive Globe:** Built with CesiumJS for high-performance 3D rendering.
- **Quantum Machine Learning AI:** A conversational agent that provides insights based on simulated quantum atmospheric states.
- **Real-time Weather:** Integration with OpenWeatherMap and Open-Meteo for accurate, up-to-date data.
- **Quantum Circuit Visualizer:** Real-time rendering of the 5-qubit variational quantum circuit (VQC) used to analyze weather conditions.
- **Glassmorphic UI:** A premium, fully responsive interface featuring dynamic animated backgrounds and intuitive controls.

## Requirements

- Python 3.10+
- Modern Web Browser (WebGL supported)
- API Keys (Optional but recommended for full functionality)

## Quick Start

1. **Clone the repository.**
2. **Configure keys (optional):**
   Copy `.env.example` to `.env` and add your API keys:
   ```bash
   cp .env.example .env
   ```
3. **Start the application:**
   ```bash
   bash start.sh
   ```
   *The script will automatically create a virtual environment, install dependencies, and start the backend/frontend on `localhost:8080`.*

## Configuration

The application is highly configurable via `config.json` and `.env`. 

- `config.json` manages application settings (ports, cache TTL, quantum simulation parameters).
- `.env` manages sensitive API keys:
  - `GOOGLE_MAPS_API_KEY`: For premium 3D tiles.
  - `WEATHER_API_KEY`: OpenWeatherMap key for accurate current conditions.
  - `AERIAL_VIEW_API_KEY`: For aerial flyover videos of selected cities.

## API Endpoints

- `GET /`: Serves the main UI.
- `GET /api/health`: Health check endpoint.
- `GET /api/weather/batch`: Retrieves weather and quantum predictions for all cities.
- `GET /api/weather/<city_id>`: Gets detailed data for a specific city.
- `POST /api/qml/chat`: Interacts with the QML AI.

## Architecture

- **Backend:** Flask, Qiskit (or mock engine), Open-Meteo / OpenWeatherMap.
- **Frontend:** HTML5, CSS3 (Glassmorphism), Vanilla JS, CesiumJS.
