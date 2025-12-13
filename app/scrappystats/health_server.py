from fastapi import FastAPI
import uvicorn
from .version import __version__

app = FastAPI()

@app.get("/health/live")
def live():
    return {"status": "alive", "version": __version__}

@app.get("/health/ready")
def ready():
    return {"status": "ready", "version": __version__}

def main():
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)

if __name__ == "__main__":
    main()
