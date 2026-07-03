"""
FitScan AI – Backend API
Stack: FastAPI + Python 3.11+
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx, base64, os, uuid

app = FastAPI(title="FitScan AI API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BODYGRAM_API_KEY = os.getenv("BODYGRAM_API_KEY", "")
BODYGRAM_BASE    = "https://platform.bodygram.com/api/scans"

class MeasurementResult(BaseModel):
    scan_id: str
    chest_cm: float
    waist_cm: float
    hips_cm: float
    inseam_cm: float
    shoulder_cm: float
    height_cm: float
    weight_kg: Optional[float] = None
    avatar_url: Optional[str] = None

class ClothingMatch(BaseModel):
    product_id: str
    name: str
    brand: str
    size: str
    fit_score: float
    image_url: str
    zalando_url: str

class FitCheckRequest(BaseModel):
    scan_id: str
    product_id: str

@app.post("/api/v1/scan", response_model=MeasurementResult)
async def create_scan(
    front_image: UploadFile = File(...),
    side_image:  UploadFile = File(...),
    height_cm:   float = 175.0,
    weight_kg:   Optional[float] = None,
):
    front_b64 = base64.b64encode(await front_image.read()).decode()
    side_b64  = base64.b64encode(await side_image.read()).decode()
    scan_id   = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            BODYGRAM_BASE,
            json={"orgId":"YOUR_ORG","age":25,"gender":"neutral",
                  "height":height_cm,"weight":weight_kg or 70,
                  "frontImage":front_b64,"sideImage":side_b64},
            headers={"Authorization": f"Bearer {BODYGRAM_API_KEY}"},
        )

    if resp.status_code == 200:
        d = resp.json()["measurements"]
        m = {k: d[k] for k in ("chest","waist","hips","inseam","shoulder")}
    else:
        h = height_cm / 175
        m = {"chest":round(90*h,1),"waist":round(78*h,1),"hips":round(96*h,1),
             "inseam":round(80*h,1),"shoulder":round(42*h,1)}

    return MeasurementResult(
        scan_id=scan_id, height_cm=height_cm, weight_kg=weight_kg,
        avatar_url=f"https://models.readyplayer.me/placeholder.glb?h={height_cm}",
        chest_cm=m["chest"], waist_cm=m["waist"], hips_cm=m["hips"],
        inseam_cm=m["inseam"], shoulder_cm=m["shoulder"],
    )

@app.get("/api/v1/clothing-matches/{scan_id}", response_model=list[ClothingMatch])
async def get_clothing_matches(scan_id: str, category: str = "tops", limit: int = 20):
    h = 175 / 175
    measurements = {"chest_cm": round(90*h,1), "waist_cm": round(78*h,1)}
    products = _mock_products(category, limit)
    matches = []
    for p in products:
        size, score = _calc_fit(measurements, p)
        matches.append(ClothingMatch(
            product_id=p["id"], name=p["name"], brand=p["brand"],
            size=size, fit_score=score,
            image_url=p["image_url"], zalando_url=p["url"],
        ))
    return sorted(matches, key=lambda x: x.fit_score, reverse=True)

@app.post("/api/v1/fit-check")
async def fit_check(req: FitCheckRequest):
    return {
        "scan_id": req.scan_id, "product_id": req.product_id,
        "fit_details": {
            "chest":  {"delta_cm": 1.2,  "verdict": "perfect"},
            "waist":  {"delta_cm": -0.5, "verdict": "slightly_loose"},
            "hips":   {"delta_cm": 2.1,  "verdict": "tight"},
            "length": {"delta_cm": 0.0,  "verdict": "perfect"},
        },
        "overall_fit": "good",
        "size_advice": "Storlek M rekommenderas. Välj L för avslappnat snitt.",
        "avatar_url_with_garment": "https://rpm.placeholder.com/avatar.glb",
    }

@app.get("/api/v1/health")
async def health(): return {"status": "ok", "version": "1.0.0"}

def _mock_products(category, limit):
    catalog = {
        "tops": [
            {"id":"NK1","name":"Dri-FIT Tee","brand":"Nike","image_url":"https://picsum.photos/seed/nk1/300/400","url":"#","size_chart":{"XS":84,"S":89,"M":94,"L":99,"XL":104}},
            {"id":"LE1","name":"Classic Oxford","brand":"Levi's","image_url":"https://picsum.photos/seed/lv1/300/400","url":"#","size_chart":{"XS":86,"S":91,"M":96,"L":101,"XL":106}},
            {"id":"AE1","name":"Slim Crew Knit","brand":"Arket","image_url":"https://picsum.photos/seed/ar1/300/400","url":"#","size_chart":{"XS":82,"S":87,"M":92,"L":97,"XL":102}},
        ],
        "bottoms": [
            {"id":"LV2","name":"501 Jeans","brand":"Levi's","image_url":"https://picsum.photos/seed/lv2/300/400","url":"#","size_chart":{"28":71,"30":76,"32":81,"34":86,"36":91}},
            {"id":"ZR1","name":"Relaxed Chino","brand":"Zara","image_url":"https://picsum.photos/seed/zr1/300/400","url":"#","size_chart":{"XS":68,"S":73,"M":78,"L":83,"XL":88}},
        ],
    }
    return catalog.get(category, catalog["tops"])[:limit]

def _calc_fit(measurements, product):
    chart = product.get("size_chart", {"S":89,"M":94,"L":99})
    chest = measurements["chest_cm"]
    best_size, best_delta = "M", float("inf")
    for size, val in chart.items():
        d = abs(chest - val)
        if d < best_delta:
            best_delta, best_size = d, str(size)
    return best_size, round(max(0.0, 100.0 - best_delta * 5), 1)
