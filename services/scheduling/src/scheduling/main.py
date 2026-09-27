"""Точка входа сервиса scheduling: `uvicorn scheduling.main:app`."""

from fastapi import FastAPI

from dutyflow_common.app import create_service_app
from dutyflow_common.auth import TokenVerifier
from scheduling.api import allocation, assignments, audit, duty_types, internal, limits, schedules
from scheduling.people import PeopleLoader, http_people_loader
from scheduling.refs import RefsLoader, http_refs_loader
from scheduling.settings import SchedulingSettings
from scheduling.solver import Jobs, Solver, http_jobs, http_solver


def create_app(
    settings: SchedulingSettings | None = None,
    token_verifier: TokenVerifier | None = None,
    refs_loader: RefsLoader | None = None,
    people_loader: PeopleLoader | None = None,
    solver: Solver | None = None,
    jobs: Jobs | None = None,
) -> FastAPI:
    settings = settings or SchedulingSettings()
    app = create_service_app(settings, title="DutyFlow scheduling", token_verifier=token_verifier)
    app.state.refs_loader = refs_loader or http_refs_loader(settings)
    app.state.people_loader = people_loader or http_people_loader(settings)
    app.state.solver = solver or http_solver(settings)
    app.state.jobs = jobs or http_jobs(settings)
    for module in (duty_types, schedules, assignments, limits, allocation, audit, internal):
        app.include_router(module.router)
    return app


app = create_app()
