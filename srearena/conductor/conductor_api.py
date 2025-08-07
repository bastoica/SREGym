import pyfiglet
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from uvicorn import Config, Server

app = FastAPI()
_conductor = None


def set_conductor(c):
    """Inject the shared Conductor instance."""
    global _conductor
    _conductor = c


class SubmitRequest(BaseModel):
    solution: str


@app.post("/submit")
async def submit_solution(req: SubmitRequest):
    if _conductor is None or _conductor.submission_stage is None:
        raise HTTPException(400, "No problem has been started")

    wrapped = f"```\nsubmit({req.solution})\n```"
    try:
        await _conductor.ask_env(wrapped)
    except Exception as e:
        raise HTTPException(400, f"Grading error: {e}")
    return _conductor.results


@app.get("/status")
async def get_status():
    if _conductor is None:
        raise HTTPException(400, "No problem has been started")
    return {"stage": _conductor.submission_stage}


def run_api(conductor, host: str = "0.0.0.0", port: int = 8000):
    set_conductor(conductor)

    console = Console()
    art = pyfiglet.figlet_format("SREArena")
    console.print(Panel(art, title="SREArena API Server", subtitle=f"http://{host}:{port}", style="bold green"))
    console.print(
        Markdown(
            """
**Available Endpoints**
- **POST /submit**: `{ "solution": "<your-solution>" }` → grades the current stage  
- **GET /status**: returns `{ "stage": "noop" | "detection" | "localization" | "mitigation" | "done" }`
"""
        )
    )

    config = Config(app=app, host=host, port=port, log_level="info")
    # disable signal handlers so Uvicorn can run inside this thread
    config.install_signal_handlers = False
    server = Server(config)
    server.run()
