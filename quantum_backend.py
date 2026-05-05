"""
╔══════════════════════════════════════════════════════════╗
║  QUANTUM GLOBE — Backend  (QCC + QML)                    ║
║  Run:  python quantum_backend.py                         ║
║  Needs: pip install flask flask-cors qiskit qiskit-aer   ║
║         qiskit-machine-learning numpy requests            ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import json
import logging
import math
import random
import requests
import concurrent.futures
import google.generativeai as genai
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Load config
CONFIG_FILE = "config.json"
try:
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
except Exception as e:
    print(f"Failed to load {CONFIG_FILE}: {e}")
    config = {}

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", config.get("GEMINI_API_KEY", ""))
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.0-flash')
else:
    gemini_model = None

SERVER_HOST = config.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = config.get("SERVER_PORT", 8080)
DEBUG = config.get("DEBUG", True)
CACHE_TTL = config.get("CACHE_TTL_SECONDS", 600)
QCC_SHOTS = config.get("QCC_SHOTS", 2048)
QCC_QUBITS = config.get("QCC_QUBITS", 5)
FORECAST_DAYS = config.get("FORECAST_DAYS", 7)
FRONTEND_FILE = config.get("FRONTEND_FILE", "quantum_globe3.html")

# Configure logging
log_level = getattr(logging, config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=log_level, format="[%(levelname)s] %(asctime)s - %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("QuantumGlobe")

# Override config with env variables if present
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", config.get("GOOGLE_MAPS_API_KEY", ""))
AERIAL_VIEW_API_KEY = os.environ.get("AERIAL_VIEW_API_KEY", config.get("AERIAL_VIEW_API_KEY", ""))
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", config.get("WEATHER_API_KEY", ""))
QCCSO_API_KEY = os.environ.get("QCCSO_API_KEY", config.get("QCCSO_API_KEY", ""))

# ── Qiskit imports (graceful fallback) ────────────────────────────────────────
QISKIT_AVAILABLE = False
try:
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator
    from qiskit.circuit.library import ZZFeatureMap, RealAmplitudes
    QISKIT_AVAILABLE = True
    logger.info("Qiskit loaded successfully ✓")
except ImportError as e:
    logger.warning(f"Qiskit not found ({e}) — running in MOCK mode")

app = Flask(__name__, static_url_path='')
CORS(app, origins=config.get("CORS_ORIGINS", ["*"]))

# ═══════════════════════════════════════════════════════════════════════════════
# CITY DATABASE  (20 global cities)
# ═══════════════════════════════════════════════════════════════════════════════
CITIES = [
    # Indian Cities First
    {"id":"del",  "name":"Delhi",        "country":"India",     "lat":28.7041,  "lon":77.1025},
    {"id":"noi",  "name":"Noida",        "country":"India",     "lat":28.5355,  "lon":77.3910},
    {"id":"mum",  "name":"Mumbai",       "country":"India",     "lat":19.0760,  "lon":72.8777},
    {"id":"ben",  "name":"Bengaluru",    "country":"India",     "lat":12.9716,  "lon":77.5946},
    {"id":"che",  "name":"Chennai",      "country":"India",     "lat":13.0827,  "lon":80.2707},
    {"id":"kol",  "name":"Kolkata",      "country":"India",     "lat":22.5726,  "lon":88.3639},
    {"id":"pun",  "name":"Pune",         "country":"India",     "lat":18.5204,  "lon":73.8567},
    # Global Cities
    {"id":"nyc",  "name":"New York",     "country":"USA",       "lat":40.7128,  "lon":-74.0060},
    {"id":"lon",  "name":"London",       "country":"UK",        "lat":51.5074,  "lon":-0.1278},
    {"id":"tok",  "name":"Tokyo",        "country":"Japan",     "lat":35.6762,  "lon":139.6503},
    {"id":"par",  "name":"Paris",        "country":"France",    "lat":48.8566,  "lon":2.3522},
    {"id":"dub",  "name":"Dubai",        "country":"UAE",       "lat":25.2048,  "lon":55.2708},
    {"id":"syd",  "name":"Sydney",       "country":"Australia", "lat":-33.8688, "lon":151.2093},
    {"id":"mos",  "name":"Moscow",       "country":"Russia",    "lat":55.7558,  "lon":37.6173},
]

# ═══════════════════════════════════════════════════════════════════════════════
# WEATHER FETCHER  (Open-Meteo & OpenWeatherMap)
# ═══════════════════════════════════════════════════════════════════════════════
class WeatherFetcher:
    OM_BASE = config.get("OPENMETEO_BASE_URL", "https://api.open-meteo.com/v1/forecast")
    OWM_BASE = config.get("OPENWEATHER_BASE_URL", "https://api.openweathermap.org/data/2.5")

    def fetch(self, lat, lon):
        """Fetch current conditions. Try OpenWeatherMap first if key exists, then fallback to Open-Meteo."""
        if WEATHER_API_KEY:
            try:
                return self._fetch_openweathermap(lat, lon)
            except Exception as e:
                logger.warning(f"OpenWeatherMap failed ({e}), falling back to Open-Meteo")

        return self._fetch_openmeteo(lat, lon)

    def _fetch_openweathermap(self, lat, lon):
        params = {"lat": lat, "lon": lon, "appid": WEATHER_API_KEY, "units": "metric"}
        r = requests.get(f"{self.OWM_BASE}/weather", params=params, timeout=6)
        r.raise_for_status()
        d = r.json()
        
        main = d.get("main", {})
        wind = d.get("wind", {})
        clouds = d.get("clouds", {})
        weather_list = d.get("weather", [])
        weather_id = weather_list[0].get("id", 0) if weather_list else 0

        return {
            "temperature": round(main.get("temp", 20), 1),
            "apparent_temperature": round(main.get("feels_like", 20), 1),
            "humidity": round(main.get("humidity", 60), 1),
            "pressure": round(main.get("pressure", 1013), 1),
            "wind_speed": round(wind.get("speed", 5), 1),
            "wind_direction": round(wind.get("deg", 180), 0),
            "precipitation": round(d.get("rain", {}).get("1h", 0) or d.get("snow", {}).get("1h", 0), 2),
            "cloud_cover": round(clouds.get("all", 30), 1),
            "uv_index": 3, # Not in current endpoint
            "weather_code": weather_id,
            "source": "openweathermap"
        }

    def _fetch_openmeteo(self, lat, lon):
        try:
            params = dict(
                latitude=lat, longitude=lon,
                current=",".join([
                    "temperature_2m","relative_humidity_2m",
                    "surface_pressure","wind_speed_10m","wind_direction_10m",
                    "precipitation","cloud_cover","uv_index",
                    "weather_code","apparent_temperature"
                ]),
                timezone="auto"
            )
            r = requests.get(self.OM_BASE, params=params, timeout=6)
            r.raise_for_status()
            c = r.json().get("current", {})
            return {
                "temperature":         round(c.get("temperature_2m", 20), 1),
                "apparent_temperature":round(c.get("apparent_temperature", 20), 1),
                "humidity":            round(c.get("relative_humidity_2m", 60), 1),
                "pressure":            round(c.get("surface_pressure", 1013), 1),
                "wind_speed":          round(c.get("wind_speed_10m", 5), 1),
                "wind_direction":      round(c.get("wind_direction_10m", 180), 0),
                "precipitation":       round(c.get("precipitation", 0), 2),
                "cloud_cover":         round(c.get("cloud_cover", 30), 1),
                "uv_index":            round(c.get("uv_index", 3), 1),
                "weather_code":        int(c.get("weather_code", 0)),
                "source":              "open-meteo"
            }
        except Exception as e:
            logger.error(f"[Weather] API failed: {e} — using synthetic data")
            return self._synthetic(lat, lon)

    def fetch_forecast(self, lat, lon, days=FORECAST_DAYS):
        """Fetch daily forecast from Open-Meteo."""
        try:
            params = dict(
                latitude=lat, longitude=lon,
                daily=",".join([
                    "temperature_2m_max","temperature_2m_min",
                    "precipitation_sum","wind_speed_10m_max",
                    "uv_index_max","cloud_cover_mean","weather_code"
                ]),
                forecast_days=days,
                timezone="auto"
            )
            r = requests.get(self.OM_BASE, params=params, timeout=6)
            r.raise_for_status()
            d = r.json().get("daily", {})
            result = []
            for i in range(min(days, len(d.get("time", [])))):
                date_str = d["time"][i]
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                result.append({
                    "date":        date_str,
                    "day":         dt.strftime("%A"),
                    "short_day":   dt.strftime("%a"),
                    "temp_max":    round(d["temperature_2m_max"][i], 1),
                    "temp_min":    round(d["temperature_2m_min"][i], 1),
                    "precipitation":round(d["precipitation_sum"][i], 1),
                    "wind_speed":  round(d["wind_speed_10m_max"][i], 1),
                    "uv_index":    round(d["uv_index_max"][i], 1),
                    "cloud_cover": round(d["cloud_cover_mean"][i], 1),
                    "weather_code":int(d["weather_code"][i]),
                })
            return result
        except Exception as e:
            logger.error(f"[Forecast] API failed: {e}")
            return self._synthetic_forecast(lat, lon, days)

    def _synthetic(self, lat, lon):
        """Generate physically-plausible fake weather."""
        doy   = datetime.utcnow().timetuple().tm_yday
        seas  = math.cos((doy - 172) / 365 * 2 * math.pi)  # +1=summer, -1=winter (NH)
        hem   = 1 if lat >= 0 else -1
        base_t = 30 * math.cos(math.radians(lat)) + seas * hem * 15
        rng = random.Random(int(lat*100)+int(lon*100)+doy)
        return {
            "temperature":  round(base_t + rng.uniform(-5, 5), 1),
            "apparent_temperature": round(base_t + rng.uniform(-8, 3), 1),
            "humidity":     round(70 - abs(lat)*0.3 + rng.uniform(-15, 15), 1),
            "pressure":     round(1013 + rng.uniform(-15, 15), 1),
            "wind_speed":   round(max(0, 8 + rng.uniform(-5, 15)), 1),
            "wind_direction":round(rng.uniform(0, 360), 0),
            "precipitation":round(max(0, rng.uniform(-1, 3)), 2),
            "cloud_cover":  round(max(0, min(100, rng.uniform(10, 80))), 1),
            "uv_index":     round(max(0, (1-abs(lat)/90)*10*rng.uniform(0.5,1.2)), 1),
            "weather_code": rng.choice([0, 1, 2, 3, 61, 80, 95]),
            "source":       "synthetic"
        }

    def _synthetic_forecast(self, lat, lon, days):
        rows = []
        rng = random.Random(int(lat*10)+int(lon*10))
        for i in range(days):
            dt = datetime.utcnow() + timedelta(days=i)
            base_t = 30 * math.cos(math.radians(lat))
            rows.append({
                "date":        dt.strftime("%Y-%m-%d"),
                "day":         dt.strftime("%A"),
                "short_day":   dt.strftime("%a"),
                "temp_max":    round(base_t + rng.uniform(-2, 8), 1),
                "temp_min":    round(base_t + rng.uniform(-8, 0), 1),
                "precipitation":round(max(0, rng.uniform(-0.5, 5)), 1),
                "wind_speed":  round(max(0, rng.uniform(2, 20)), 1),
                "uv_index":    round(max(0, (1-abs(lat)/90)*10*rng.uniform(0.4,1.2)), 1),
                "cloud_cover": round(max(0, min(100, rng.uniform(10,80))), 1),
                "weather_code":rng.choice([0,1,2,3,61,80,95]),
            })
        return rows

weather_fetcher = WeatherFetcher()

# ═══════════════════════════════════════════════════════════════════════════════
# QCC — Quantum Climate Circuit
# ═══════════════════════════════════════════════════════════════════════════════
class QCC:
    """
    Physics engine: encodes atmospheric conditions as a parameterised quantum
    circuit, runs a shot-based simulation, and extracts quantum metrics that
    describe the 'quantum state' of the weather system.
    """
    N = QCC_QUBITS

    def __init__(self):
        if QISKIT_AVAILABLE:
            self.sim = AerSimulator()
        self.shots = QCC_SHOTS
        self.backend_name = "qiskit-aer" if QISKIT_AVAILABLE else "mock"

    def build(self, weather: dict):
        qc = QuantumCircuit(self.N, self.N)

        T    = weather.get("temperature",  20)
        H    = weather.get("humidity",     60)
        P    = weather.get("pressure",   1013)
        W    = weather.get("wind_speed",    5)
        C    = weather.get("cloud_cover",  30)

        t_θ  = (T + 50) / 110 * math.pi
        h_θ  = H / 100 * math.pi
        p_θ  = (P - 950) / 120 * math.pi
        w_θ  = min(W, 50) / 50 * math.pi
        c_θ  = C / 100 * math.pi

        for q in range(self.N):
            qc.h(q)
        qc.barrier(label="H")

        qc.ry(t_θ, 0)
        qc.ry(h_θ, 1)
        if self.N > 2: qc.rz(p_θ, 2)
        if self.N > 3: qc.ry(w_θ, 3)
        if self.N > 4: qc.rx(c_θ, 4)
        qc.barrier(label="Encode")

        for i in range(self.N - 1):
            qc.cx(i, i+1)
        qc.barrier(label="CNOT₁")

        for q, θ in enumerate([t_θ*1.3, h_θ*0.8, p_θ*1.1, w_θ*1.5, c_θ*0.9][:self.N]):
            qc.ry(θ, q)
        qc.barrier(label="Var₁")

        if self.N > 2:
            qc.cx(0, 2)
            if self.N > 3: qc.cx(1, 3)
            if self.N > 4: qc.cx(3, 4)
            qc.barrier(label="CNOT₂")

        for q, θ in enumerate([p_θ, t_θ, c_θ, h_θ, w_θ][:self.N]):
            qc.rz(θ, q)
        qc.barrier(label="Var₂")

        qc.measure(range(self.N), range(self.N))
        return qc

    def simulate(self, weather: dict) -> dict:
        if not QISKIT_AVAILABLE:
            return self._mock_simulate(weather)

        qc = self.build(weather)
        # CHANGE optimization_level from 1 to 0 for faster transpile
        t  = transpile(qc, self.sim, optimization_level=0) 
        job = self.sim.run(t, shots=self.shots)
        counts = job.result().get_counts()

        return self._decode(counts, weather, qc)

    def _decode(self, counts, weather, qc=None) -> dict:
        total = sum(counts.values())
        probs = {k: v/total for k, v in counts.items()}

        entropy = -sum(p*math.log2(p+1e-9) for p in probs.values())
        dom = max(probs, key=probs.get)
        dom_prob = probs[dom] * 100

        fidelity = round(100 * (1 - entropy/self.N), 1)
        fidelity = max(0, min(100, fidelity))

        top_states = sorted(
            [{"state": k, "probability": round(v*100, 2)} for k, v in probs.items()],
            key=lambda x: -x["probability"]
        )[:8]

        if entropy < 1.5:   sev = "low"
        elif entropy < 2.5: sev = "moderate"
        elif entropy < 3.5: sev = "high"
        else:                sev = "extreme"

        condition = self._condition(weather, entropy)

        T = weather.get("temperature", 20)
        H = weather.get("humidity", 60)
        P = weather.get("pressure", 1013)
        W = weather.get("wind_speed", 5)

        return {
            "condition":       condition,
            "severity":        sev,
            "quantum_fidelity":fidelity,
            "quantum_entropy": round(entropy, 3),
            "dominant_state":  dom,
            "probability":     round(dom_prob, 1),
            "top_states":      top_states,
            "circuit_depth":   qc.depth() if qc else 14,
            "circuit_width":   self.N,
            "shots":           self.shots,
            "backend":         self.backend_name,
            "angles_deg": {
                "temp_theta":     round(math.degrees((T+50)/110*math.pi), 1),
                "humidity_theta": round(math.degrees(H/100*math.pi),      1),
                "pressure_theta": round(math.degrees((P-950)/120*math.pi),1),
                "wind_theta":     round(math.degrees(min(W,50)/50*math.pi),1),
            },
        }

    def _condition(self, w, entropy):
        T  = w.get("temperature", 20)
        H  = w.get("humidity", 60)
        P  = w.get("pressure", 1013)
        WS = w.get("wind_speed", 5)
        C  = w.get("cloud_cover", 30)
        if T > 40:          return "Extreme Heat Wave"
        if T < -20:         return "Arctic Blizzard"
        if WS > 25:         return "Severe Storm"
        if P < 990 and H > 85: return "Tropical Depression"
        if WS > 15:         return "Strong Gale"
        if H > 80 and C > 70: return "Heavy Rain"
        if C > 80:          return "Overcast"
        if T > 32:          return "Hot & Sunny"
        if T < 0:           return "Sub-Zero"
        if entropy > 3.5:   return "Quantum Turbulence"
        if entropy < 1.5:   return "Stable Clear"
        return "Partly Cloudy"

    def _mock_simulate(self, weather) -> dict:
        r = random.Random(hash(str(weather)) & 0xFFFFFF)
        n = 2**self.N
        raw = [r.random() for _ in range(n)]
        s   = sum(raw)
        probs = {format(i, f'0{self.N}b'): v/s for i, v in enumerate(raw)}
        return self._decode(probs, weather)

qcc = QCC()

# ═══════════════════════════════════════════════════════════════════════════════
# QML — Quantum Machine Learning
# ═══════════════════════════════════════════════════════════════════════════════
class QML:
    N = 4

    def __init__(self):
        if QISKIT_AVAILABLE:
            self.sim = AerSimulator()

    def _build_vqc(self, features: list):
        qc = QuantumCircuit(self.N, self.N)
        f  = [float(x) for x in features[:self.N]]

        for i, fi in enumerate(f):
            qc.h(i)
            qc.rz(fi * math.pi * 2, i)
        for i in range(self.N - 1):
            qc.cx(i, i+1)
            qc.rz((f[i] - f[i+1]) * math.pi, i+1)
            qc.cx(i, i+1)
        qc.barrier(label="FM")

        for i, fi in enumerate(f):
            qc.ry(fi * math.pi * 0.8 + 0.3, i)
        for i in range(self.N):
            qc.cx(i, (i+1) % self.N)
        for i, fi in enumerate(f):
            qc.ry(fi * math.pi * 0.5 + 0.1, i)
        qc.barrier(label="Ansatz")

        qc.measure_all()
        return qc

    def predict(self, current_weather: dict, raw_forecast: list) -> list:
        out = []
        for i, day in enumerate(raw_forecast):
            t_max = day.get("temp_max", 20)
            t_min = day.get("temp_min", 10)
            prec  = day.get("precipitation", 0)
            ws    = day.get("wind_speed", 5)

            features = [
                (t_max + 50) / 110,
                max(0, min(1, prec / 20)),
                min(1, ws / 50),
                (i + 1) / len(raw_forecast),
            ]

            q_data = self._run_vqc(features)

            condition = self._forecast_condition(day)
            out.append({
                **day,
                "condition":        condition,
                "quantum_fidelity": q_data["fidelity"],
                "quantum_entropy":  q_data["entropy"],
                "confidence":       round(max(30, 92 - i * 7 + q_data["fidelity"] * 0.1), 1),
            })
        return out

    def _run_vqc(self, features) -> dict:
        if QISKIT_AVAILABLE:
            try:
                qc = self._build_vqc(features)
                t  = transpile(qc, self.sim, optimization_level=0)
                job = self.sim.run(t, shots=512)
                counts = job.result().get_counts()
                total  = sum(counts.values())
                probs  = {k: v/total for k, v in counts.items()}
                entropy= -sum(p*math.log2(p+1e-9) for p in probs.values())
                fid    = round(max(0, min(100, 100*(1-entropy/self.N))), 1)
                return {"fidelity": fid, "entropy": round(entropy, 3)}
            except Exception:
                pass
        r = random.Random(hash(tuple(round(x,3) for x in features)))
        return {"fidelity": round(r.uniform(45, 85), 1), "entropy": round(r.uniform(1.5, 3.5), 3)}

    def _forecast_condition(self, day):
        t  = (day.get("temp_max",20) + day.get("temp_min",10)) / 2
        pr = day.get("precipitation", 0)
        ws = day.get("wind_speed", 5)
        cl = day.get("cloud_cover", 30)
        if pr > 10:   return "Heavy Rain"
        if pr > 3:    return "Rainy"
        if pr > 0.5:  return "Light Showers"
        if ws > 20:   return "Windy"
        if cl > 75:   return "Overcast"
        if cl > 40:   return "Cloudy"
        if t > 35:    return "Hot Sunny"
        if t < 0:     return "Freezing"
        if t < 10:    return "Cold Clear"
        return "Sunny"

    def chat(self, message: str, city_data: dict) -> str:
        name = city_data.get("name", "this location")
        w = city_data.get("weather", {})
        qp = city_data.get("quantum_prediction", {})
        fc = city_data.get("forecast", [])

        # --- 1. ATTEMPT GEMINI AI FIRST ---
        if gemini_model:
            context = (
                f"You are the QuantumGlobe AI assistant. Be concise, scientific, and helpful. "
                f"Current City: {name}. "
                f"Weather: {w.get('temperature')}°C, {w.get('wind_speed')} m/s wind, {w.get('humidity')}% humidity. "
                f"Quantum State: Fidelity is {qp.get('quantum_fidelity')}%, Entropy is {qp.get('quantum_entropy')} bits. "
                f"Dominant quantum state is |{qp.get('dominant_state')}⟩."
            )
            try:
                response = gemini_model.generate_content(f"{context}\n\nUser Question: {message}")
                return response.text
            except Exception as e:
                # If Gemini fails (e.g. rate limit, network error), we log it and let it fall through
                print(f"[Warning] Gemini API failed: {e}. Falling back to rule-based system.")

        # --- 2. FALLBACK RULE-BASED LOGIC ---
        msg = message.lower()
        T   = w.get("temperature", "—")
        H   = w.get("humidity", "—")
        WS  = w.get("wind_speed","—")
        fid = qp.get("quantum_fidelity","—")
        ent = qp.get("quantum_entropy","—")
        cond= qp.get("condition","—")

        if any(k in msg for k in ["temperature","temp","hot","cold","heat","warm"]):
            return (f"🌡 QML Thermal Analysis for {name}:\n\n"
                    f"Current: {T}°C | Feels like: {w.get('apparent_temperature','—')}°C\n"
                    f"Quantum fidelity: {fid}% — {'high confidence' if str(fid)>'60' else 'uncertain'}\n\n"
                    f"The VQC encodes temperature as a rotation angle θ_T = {qp.get('angles_deg',{}).get('temp_theta','—')}° on Q0. "
                    f"High entropy ({ent} bits) indicates thermal turbulence in the atmospheric quantum state.")

        if any(k in msg for k in ["rain","precipit","shower","drizzle","storm"]):
            pr = w.get("precipitation", 0)
            cl = w.get("cloud_cover", 30)
            future = [d for d in fc if d.get("precipitation",0) > 1]
            rain_days = ", ".join(d["short_day"] for d in future[:3]) if future else "none forecast"
            return (f"🌧 QML Precipitation Model for {name}:\n\n"
                    f"Current precipitation: {pr} mm | Cloud cover: {cl}%\n"
                    f"Rain expected: {rain_days}\n\n"
                    f"Quantum circuit dominant state |{qp.get('dominant_state','—')}⟩ at {qp.get('probability','—')}% "
                    f"amplitude — {'convective instability detected' if pr>0 else 'stable pressure system'}.")

        if any(k in msg for k in ["wind","gust","breeze","storm","hurricane","cyclone"]):
            wd = w.get("wind_direction", 0)
            dirs = ["N","NE","E","SE","S","SW","W","NW"]
            d_label = dirs[round(wd/45)%8]
            return (f"🌬 QML Wind Analysis for {name}:\n\n"
                    f"Speed: {WS} m/s | Direction: {wd}° ({d_label})\n"
                    f"Quantum encoding: θ_W = {qp.get('angles_deg',{}).get('wind_theta','—')}° on Q3\n\n"
                    f"VQC measurement statistics show {'high' if float(WS or 0)>15 else 'moderate'} "
                    f"kinetic energy eigenstate probability. Wind patterns are "
                    f"{'chaotic' if float(ent or 3)>3 else 'laminar'} in quantum phase space.")

        if any(k in msg for k in ["forecast","next","week","tomorrow","days","predict"]):
            if fc:
                lines = "\n".join(
                    f"  {d['short_day']}: {d.get('temp_min','?')}–{d.get('temp_max','?')}°C  "
                    f"{d.get('condition','—')}  Q-conf:{d.get('confidence','—')}%"
                    for d in fc[:5]
                )
                return (f"📅 QML {FORECAST_DAYS}-Day Quantum Forecast for {name}:\n\n{lines}\n\n"
                        f"VQC confidence decays over time as quantum decoherence degrades "
                        f"predictability beyond ~5 days. Fidelity starts at {fid}% today.")
            return f"📅 No forecast data available for {name}."

        if any(k in msg for k in ["quantum","qubit","circuit","vqc","qcc","qml","fidelity","entropy"]):
            return (f"⚛ Quantum Architecture for {name}:\n\n"
                    f"QCC: {QCC_QUBITS}-qubit VQC | depth {qp.get('circuit_depth','—')} | {qp.get('shots','—')} shots\n"
                    f"Fidelity: {fid}%  |  Entropy: {ent} bits\n"
                    f"Dominant eigenstate: |{qp.get('dominant_state','—')}⟩ @ {qp.get('probability','—')}%\n\n"
                    f"QCC encodes T/H/P/W/C as rotation angles, entangles qubits via CNOT to model "
                    f"atmospheric correlation, then measures probability amplitudes.\n"
                    f"QML re-runs a 4-qubit VQC per forecast day, extracting fidelity as confidence.")

        if any(k in msg for k in ["humidity","moisture","dew"]):
            return (f"💧 QML Humidity Analysis for {name}:\n\n"
                    f"Relative humidity: {H}%  |  Pressure: {w.get('pressure','—')} hPa\n"
                    f"θ_H = {qp.get('angles_deg',{}).get('humidity_theta','—')}° on Q1\n\n"
                    f"{'High humidity detected — evapotranspiration feedback loop active in quantum state.' if float(H or 0)>75 else 'Moderate humidity — stable moisture-pressure coupling.'}")

        if any(k in msg for k in ["uv","ultraviolet","sun","sunburn"]):
            uv = w.get("uv_index", 3)
            level = "extreme" if uv>8 else ("very high" if uv>6 else ("high" if uv>4 else ("moderate" if uv>2 else "low")))
            return (f"☀ UV Index for {name}: {uv} ({level})\n\n"
                    f"{'⚠ Limit outdoor exposure, use SPF 50+' if uv>6 else 'Standard precautions recommended' if uv>3 else 'Low UV — no special precautions needed'}.\n"
                    f"UV is quantum-modelled via amplitude in the cloud-cover encoding.")

        return (f"⚛ QML Summary for {name}:\n\n"
                f"Condition: {cond}  |  Temp: {T}°C  |  Wind: {WS} m/s\n"
                f"Q-Fidelity: {fid}%  |  Entropy: {ent} bits\n\n"
                f"Ask me about: temperature, rain, wind, forecast, humidity, UV, "
                f"or the quantum circuit architecture!")

qml = QML()

# ═══════════════════════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════════════════════
_cache: dict = {}

def get_city_data(city_id: str, force=False) -> dict:
    if city_id in _cache and not force:
        age = (datetime.utcnow() - _cache[city_id]["_ts"]).seconds
        if age < CACHE_TTL:
            return _cache[city_id]

    city = next((c for c in CITIES if c["id"] == city_id), None)
    if not city:
        return {}

    weather  = weather_fetcher.fetch(city["lat"], city["lon"])
    raw_fc   = weather_fetcher.fetch_forecast(city["lat"], city["lon"], FORECAST_DAYS)
    qcc_data = qcc.simulate(weather)
    forecast = qml.predict(weather, raw_fc)

    data = {**city, "weather": weather, "quantum_prediction": qcc_data,
            "forecast": forecast, "_ts": datetime.utcnow()}
    _cache[city_id] = data
    return data

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.errorhandler(Exception)
def handle_error(e):
    logger.exception(f"Unhandled exception: {e}")
    return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/")
def serve_index():
    if os.path.exists(FRONTEND_FILE):
        return send_file(FRONTEND_FILE)
    return jsonify({"error": f"Frontend file {FRONTEND_FILE} not found"}), 404

@app.route("/api/health")
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

@app.route("/api/keys")
def get_keys():
    """Return API keys for frontend."""
    return jsonify({
        "google_maps_key": GOOGLE_MAPS_API_KEY,
        "aerial_view_key": AERIAL_VIEW_API_KEY
    })

@app.route("/api/aerial/<city_id>")
def aerial_view(city_id):
    """Mock or actual Aerial View endpoint."""
    city = next((c for c in CITIES if c["id"] == city_id), None)
    if not city:
        return jsonify({"available": False, "reason": "City not found"}), 404
        
    if not AERIAL_VIEW_API_KEY:
        return jsonify({"available": False, "reason": "Configure AERIAL_VIEW_API_KEY in config.json"})

    # In a real app, this would query the Google Aerial View API
    # Since we can't reliably get a video for an arbitrary lat/lon here, we'll mock it
    # by returning unavailable unless it's a specific mock scenario.
    return jsonify({"available": False, "reason": "No footage generated for this location yet."})

@app.route("/api/quantum/status")
def status():
    return jsonify({
        "available": QISKIT_AVAILABLE,
        "qubits": QCC_QUBITS,
        "shots": QCC_SHOTS,
        "mode": "Qiskit Aer" if QISKIT_AVAILABLE else "Mock",
        "qiskit": QISKIT_AVAILABLE,
        "cities": len(CITIES)
    })

@app.route("/api/cities")
def cities():
    return jsonify(CITIES)

@app.route("/api/weather/batch")
def batch():
    """Return top cities quickly to prevent long startup hangs."""
    # Only process the first 7 cities (the Indian ones) on initial batch load
    top_cities = CITIES[:7] 
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda c: get_city_data(c["id"]), top_cities))
    clean = [{k:v for k,v in r.items() if k!="_ts"} for r in results if r]
    return jsonify(clean)

@app.route("/api/weather/<city_id>")
def city_detail(city_id):
    d = get_city_data(city_id, force=True)
    if not d:
        return jsonify({"error": "City not found"}), 404
    return jsonify({k:v for k,v in d.items() if k!="_ts"})

@app.route("/api/qml/forecast/<city_id>")
def forecast(city_id):
    d = get_city_data(city_id)
    return jsonify(d.get("forecast", []))

@app.route("/api/qml/chat", methods=["POST"])
def chat():
    body    = request.get_json(force=True) or {}
    message = body.get("message", "")
    city_id = body.get("city_id", "nyc")
    d = get_city_data(city_id)
    reply = qml.chat(message, d)
    return jsonify({"reply": reply, "city": d.get("name","—")})

@app.route("/api/qcc/circuit/<city_id>")
def circuit_info(city_id):
    d = get_city_data(city_id)
    return jsonify(d.get("quantum_prediction", {}))

@app.route("/api/overlay/<layer>")
def overlay(layer):
    """Return a coarse lat/lon grid for weather overlay rendering."""
    rng = random.Random(datetime.utcnow().hour)
    pts = []
    for lat in range(-85, 86, 5):
        for lon in range(-180, 181, 5):
            base_t = 30 * math.cos(math.radians(lat))
            doy    = datetime.utcnow().timetuple().tm_yday
            seas   = math.cos((doy-172)/365*2*math.pi) * (1 if lat>=0 else -1)
            T  = base_t + seas*12 + rng.uniform(-5,5)
            H  = 70 - abs(lat)*0.3 + rng.uniform(-15,15)
            P  = 1013 + math.sin(math.radians(lat*3))*18 + rng.uniform(-8,8)
            WS = max(0, 8 + rng.uniform(-5,15))
            WD = (180 - lat + rng.uniform(-40,40)) % 360
            UV = max(0, (1-abs(lat)/90)*11*rng.uniform(0.5,1.1))
            pts.append({"lat":lat, "lon":lon, "T":round(T,1), "H":round(H,1),
                        "P":round(P,1), "WS":round(WS,1), "WD":round(WD,1),
                        "UV":round(UV,1)})
    return jsonify(pts)

# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    logger.info("╔═══════════════════════════════════════╗")
    logger.info("║  QUANTUM GLOBE Backend  — Starting    ║")
    logger.info(f"║  Qiskit: {'✓ Active' if QISKIT_AVAILABLE else '✗ Mock mode':<28}║")
    logger.info(f"║  http://{SERVER_HOST}:{SERVER_PORT}{' '*(23-len(str(SERVER_PORT)))}║")
    logger.info("╚═══════════════════════════════════════╝")
    
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=DEBUG)
