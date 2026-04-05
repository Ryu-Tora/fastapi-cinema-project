from fastapi import FastAPI

app = FastAPI(
    title="Online-Cinema",
    description="Digital platform for movies",
    version="0.0.1",
)


@app.get("/")
def root():
    return {"status": "success", "message": "Online-Cinema"}
