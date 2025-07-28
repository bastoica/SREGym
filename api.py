import threading

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from srearena.conductor import Conductor
from srearena.conductor.parser import ResponseParser
from srearena.utils.sigint_aware_section import SigintAwareSection
from srearena.utils.status import SubmissionStatus

app = FastAPI()
conductor = Conductor()


class SubmitRequest(BaseModel):
    solution: str


@app.post("/submit")
async def submit_solution(req: SubmitRequest):
    if conductor.submission_stage is None:
        raise HTTPException(status_code=400, detail="No problem has been started")

    cmd = f"submit({req.solution})"
    try:
        parsed = conductor.parser.parse(cmd)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parsing error: {e}")

    if parsed.get("api_name") != "submit":
        raise HTTPException(status_code=400, detail="Invalid submit command")

    resp = await conductor.ask_env(cmd)
    if resp == SubmissionStatus.VALID_SUBMISSION:
        return {"status": "ok", "detail": "Mitigation stage evaluated"}
    return {"status": "ok", "detail": resp}


@app.get("/status")
async def get_status():
    return {"stage": conductor.submission_stage}


@app.post("/start/{problem_id}")
async def start_problem(problem_id: str):
    if conductor.submission_stage is not None:
        raise HTTPException(status_code=400, detail="Problem already in progress")

    conductor.problem_id = problem_id

    def _run():
        import asyncio

        asyncio.run(conductor.start_problem())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"message": f"Problem '{problem_id}' execution begun via conductor."}


@app.get("/results")
async def get_results():
    if conductor.submission_stage != "done":
        raise HTTPException(status_code=400, detail="Results not ready")
    return conductor.results


if __name__ == "__main__":
    import pyfiglet

    ascii_art = pyfiglet.figlet_format("SREArena")
    console = Console()
    console.print(
        Panel(
            ascii_art, title="SREArena CLI Web Server", subtitle="Access at http://localhost:8000", style="bold green"
        )
    )
    endpoints = """
**Available Endpoints**
- **POST /start/{problem_id}**: Initialize and start the problem run
- **POST /submit**: Submit a detection solution (JSON body: { "solution": "<your-solution>" })
- **GET /status**: Get the current submission stage
- **GET /results**: Retrieve the final results after completion
    """
    console.print(Markdown(endpoints))
    uvicorn.run(app, host="0.0.0.0", port=8000)
