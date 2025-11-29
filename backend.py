from fastapi import FastAPI, Request
import requests
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 모든 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


API_NINJAS_KEY = os.getenv("API_NINJAS_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CITIES = {
    "tashkent": (41.3111, 69.2406),
    "samarkand": (39.6542, 66.9597),
    "bukhara": (39.7737, 64.4286),
    "andijan": (40.8151, 72.2835),
    "namangan": (41.0011, 71.6726),
    "fergana": (40.3864, 71.7843),
    "gulistan": (40.4957, 68.7840),
    "karshi": (38.8610, 65.7847),
    "nukus": (42.4606, 59.6155),
    "navoi": (40.0844, 65.3792),
    "jizzakh": (40.1158, 67.8422),
    "urgench": (41.5614, 60.6313)
}


def aqi_from_pm25(pm):
    bp = [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300)
    ]
    for low_c, high_c, low_aqi, high_aqi in bp:
        if low_c <= pm <= high_c:
            return int((high_aqi - low_aqi) / (high_c - low_c) * (pm - low_c) + low_aqi)
    return 300

def aqi_from_pm10(pm):
    bp = [
        (0, 54, 0, 50),
        (55, 154, 51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200)
    ]
    for low_c, high_c, low_aqi, high_aqi in bp:
        if low_c <= pm <= high_c:
            return int((high_aqi - low_aqi) / (high_c - low_c) * (pm - low_c) + low_aqi)
    return 200

def detect_city_from_ip(ip):
    try:
        data = requests.get(f"https://ipapi.co/{ip}/json/").json()
        city = data.get("city", "").lower()
        if city in CITIES:
            return city
    except:
        pass
    return "tashkent"

def generate_groq_text(aqi):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
    Current AQI: {aqi}
    Generate exactly 4 extremely short air-quality messages.
    1. Should I go outside now?
    2. Advice for sensitive people.
    3. General caution message.
    4. Mask advice.
    Each message must be under 7 words.
    """

    body = {
        "model": "moonshotai/kimi-k2-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }

    res = requests.post(url, json=body, headers=headers).json()

    
    print("🔍 RAW GROQ RESPONSE:", res)

    output = res["choices"][0]["message"]["content"].strip().split("\n")

    clean = [x.strip("- ").strip() for x in output if x.strip()]
    return clean[:4]


def best_times_from_forecast(forecast):
    best = []
    now = datetime.now()

    for i, aqi in enumerate(forecast):
        if aqi < 60:
            best.append({
                "time": (now + timedelta(hours=i)).strftime("%I:%M %p"),
                "aqi": aqi
            })

    return best[:6]


@app.get("/full-aqi")
async def full_aqi(request: Request):

    client_ip = request.headers.get("X-Forwarded-For") or request.client.host
    city = detect_city_from_ip(client_ip)
    lat, lon = CITIES[city]

    live = requests.get(
        f"https://api.api-ninjas.com/v1/airquality?city={city}",
        headers={"X-Api-Key": API_NINJAS_KEY}
    ).json()

    print("🔍 LIVE AIR QUALITY DATA:", live)

    current_aqi = live.get("overall_aqi", 80)


    aq_url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality?"
        f"latitude={lat}&longitude={lon}"
        f"&hourly=pm10,pm2_5"
        f"&past_days=1&forecast_days=2"
    )

    aq = requests.get(aq_url).json()
    print(f"AQ is sadsdadsad: {aq}")

    pm25 = aq["hourly"]["pm2_5"]
    pm10 = aq["hourly"]["pm10"]

    hourly_aqi = []
    for i in range(len(pm25)):
        aqi25 = aqi_from_pm25(pm25[i])
        aqi10 = aqi_from_pm10(pm10[i])
        hourly_aqi.append(max(aqi25, aqi10))

    last_24 = hourly_aqi[-48:-24]
    next_24 = hourly_aqi[-24:]

    best_times = best_times_from_forecast(next_24)

    groq = generate_groq_text(current_aqi)

    return {
        "city": city,
        "current_aqi": current_aqi,
        "pollutants": live,
        "trend_24h": last_24,
        "forecast_24h": next_24,
        "best_times": best_times,

        "gpt_messages": {
            "now": groq[0],
            "sensitive": groq[1],
            "general": groq[2],
            "mask": groq[3],
        }
    }

