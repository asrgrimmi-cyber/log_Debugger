import re
import json
from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

class RRCLogParser:
    def __init__(self, text_content: str):
        self.raw_text = text_content

    @staticmethod
    def clean_to_dict(block_text: str) -> Dict[str, Any]:
        if not block_text: return {}
        result = {}
        for line in block_text.splitlines():
            clean = line.strip().rstrip(',').replace('{', '').replace('}', '').strip()
            if clean:
                parts = re.split(r'\s+|:\s*', clean, maxsplit=1)
                if len(parts) == 2:
                    key, val = parts[0], parts[1].strip('"')
                    try:
                        result[key] = float(val) if '.' in val else int(val)
                    except ValueError:
                        result[key] = val
                else:
                    result[parts[0]] = "present"
        return result

    def fetch_changes(self, pattern: str, is_block: bool = False) -> List[Any]:
        flags = re.DOTALL if is_block else 0
        instances = []
        last_value = None
        for match in re.finditer(pattern, self.raw_text, flags=flags):
            current_raw = match.group(1).strip() if is_block and match.groups() else match.group(0).strip()
            current_value = self.clean_to_dict(current_raw) if is_block else current_raw
            if current_value != last_value:
                instances.append(current_value)
                last_value = current_value
        return instances

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "results": None})

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, file: UploadFile = File(...)):
    # Get the list of selected features from the form
    form_data = await request.form()
    selected_features = form_data.getlist("features") # This gets all checked boxes
    
    content = await file.read()
    text = content.decode('utf-8')
    parser = RRCLogParser(text)
    
    # Define our Categorized Database
    feature_database = {
        # General Category
        "cell_barred": {"patt": r'cellBarredNTN-r17\s+(\w+)', "is_block": False, "cat": "General"},
        "nr_band": {"patt": r'freqBandIndicatorNR\s+(\d+)', "is_block": False, "cat": "General"},
        "cell_identity": {"patt": r"cellIdentity\s+'([0-9A-Fa-f]+)'H", "is_block": False, "cat": "General"},

        
        # Feature Specific Category
        "ntn_config": {"patt": r"ntn-Config-r17\s*{(.*?)\}", "is_block": True, "cat": "Feature"},
        "ephemeris_pos": {"patt": r"ephemerisInfo-r17\s+positionVelocity-r17\s*[:]?\s*\{(.*?)\}", "is_block": True, "cat": "Feature"},
        "timers": {"patt": r"ue-TimersAndConstants\s*{(.*?)}", "is_block": True, "cat": "Feature"},
        "scheduling": {"patt": r"schedulingRequestToAddModList\s*{(.*?)\}", "is_block": True, "cat": "Feature"},
        "radioBearerConfig":{"patt": r"radioBearerConfig\s*{(.*?)\}", "is_block": True, "cat": "Feature"}
    }

    history = {}
    # Only process if the key was checked in the UI
    for key in selected_features:
        if key in feature_database:
            item = feature_database[key]
            res = parser.fetch_changes(item["patt"], item["is_block"])
            if res:
                history[key] = res

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "results": history, 
        "filename": file.filename,
        "json_str": json.dumps(history, indent=4),
        "selected_features": selected_features # Keep track of what was checked
    })
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)