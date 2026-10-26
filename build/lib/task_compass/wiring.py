"""Builds the services once, for the web app and the scripts."""

from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from task_compass import config
from task_compass.db import make_session_factory
from task_compass.interview.service import InterviewService
from task_compass.llm.gateway import Gateway, LLMClient
from task_compass.services.estimate import EstimateService
from task_compass.services.execution import ExecutionService
from task_compass.services.retro import RetroService


@dataclass
class Services:
    session_factory: sessionmaker
    settings: config.Settings
    interview: InterviewService
    estimate: EstimateService
    execution: ExecutionService
    retro: RetroService


def build_services(client: LLMClient | None = None, session_factory: sessionmaker | None = None,
                   settings: config.Settings | None = None) -> Services:
    settings = settings or config.Settings()
    session_factory = session_factory or make_session_factory()
    if client is None:
        from task_compass.llm.anthropic_client import AnthropicClient

        client = AnthropicClient(settings)
    gateway = Gateway(client, session_factory, settings)
    retro = RetroService(session_factory)
    return Services(
        session_factory=session_factory,
        settings=settings,
        interview=InterviewService(gateway, session_factory),
        estimate=EstimateService(gateway, session_factory),
        execution=ExecutionService(session_factory, retro),
        retro=retro,
    )
