from __future__ import annotations

from pathlib import Path
from typing import Any

from agents import Agent, CodeInterpreterTool, FileSearchTool, ModelSettings, WebSearchTool
from agents.models.multi_provider import MultiProvider
from agents.tool import CodeInterpreter
from openai.types.shared import Reasoning

from .models import TaskResult, VerifierResult


def _read_prompt(path: str | Path) -> str:
    return Path(path).read_text().strip()


def _code_interpreter_tool(config: dict[str, Any], agent_key: str) -> CodeInterpreterTool:
    ci_cfg = config.get("code_interpreter", {}) or {}
    memory_limit = ci_cfg.get("memory_limit")
    container: dict[str, Any] = {"type": "auto", "file_ids": []}
    if memory_limit:
        container["memory_limit"] = memory_limit
    tool_config = CodeInterpreter(type="code_interpreter", container=container)
    return CodeInterpreterTool(tool_config=tool_config)


def _tools_for_agent(agent_key: str, config: dict[str, Any], vector_store_id: str | None) -> list[Any]:
    tools_cfg = config.get("tools", {}) or {}
    selected = None
    per_agent = tools_cfg.get("per_agent", {}) or {}
    if agent_key in per_agent:
        selected = per_agent.get(agent_key)
    if selected is None:
        selected = tools_cfg.get("default")

    if selected is None:
        if agent_key == "literature_scout":
            selected = ["web_search"]
        elif agent_key == "paper_reader":
            selected = ["file_search"]
        elif agent_key == "derivation_coder":
            selected = ["code_interpreter"]
        elif agent_key == "verifier":
            selected = ["file_search", "code_interpreter"]
        else:
            selected = []

    if isinstance(selected, str):
        selected = [selected]
    if not isinstance(selected, list):
        raise ValueError(f"tools for {agent_key} must be a list of strings")

    built: list[Any] = []
    for name in selected:
        if name == "web_search":
            built.append(WebSearchTool())
        elif name == "file_search":
            if vector_store_id:
                built.append(
                    FileSearchTool(vector_store_ids=[vector_store_id], max_num_results=5)
                )
        elif name == "code_interpreter":
            built.append(_code_interpreter_tool(config, agent_key))
        elif name in {"none", ""}:
            continue
        else:
            raise ValueError(
                f"Unknown tool '{name}' for agent '{agent_key}'. "
                "Supported: web_search, file_search, code_interpreter"
            )
    return built


def _merge_settings(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    merged.update(overrides)
    if "reasoning" in merged and isinstance(merged["reasoning"], dict):
        merged["reasoning"] = Reasoning(**merged["reasoning"])
    return merged


def _model_settings_for(agent_key: str, config: dict[str, Any]) -> ModelSettings:
    settings_cfg = config.get("model_settings", {})
    default_settings = settings_cfg.get("default", {})
    per_agent = settings_cfg.get("per_agent", {})
    merged = _merge_settings(default_settings, per_agent.get(agent_key, {}))
    return ModelSettings(**merged)


def _prompt_path(agent_key: str, config: dict[str, Any], prompts_dir: Path) -> Path:
    prompt_cfg = config.get("prompts", {})
    default_dir = Path(prompt_cfg.get("default_dir", str(prompts_dir)))
    per_agent = prompt_cfg.get("per_agent", {})
    if agent_key in per_agent:
        return Path(per_agent[agent_key])
    return default_dir / f"{agent_key}.md"


def _openai_provider_config(agent_key: str, config: dict[str, Any]) -> dict[str, Any]:
    providers_cfg = config.get("providers", {})
    default_openai = providers_cfg.get("default", {}).get("openai", {})
    per_agent_openai = providers_cfg.get("per_agent", {}).get(agent_key, {}).get("openai", {})
    merged = dict(default_openai)
    merged.update(per_agent_openai)
    normalized = {}
    for key, value in merged.items():
        if isinstance(value, str) and value.strip() == "":
            normalized[key] = None
        else:
            normalized[key] = value
    return normalized


def _model_for(agent_key: str, model_name: str | None, config: dict[str, Any]):
    provider_cfg = _openai_provider_config(agent_key, config)
    provider = MultiProvider(
        openai_api_key=provider_cfg.get("api_key"),
        openai_base_url=provider_cfg.get("base_url"),
        openai_organization=provider_cfg.get("organization"),
        openai_project=provider_cfg.get("project"),
        openai_use_responses=provider_cfg.get("use_responses"),
    )
    return provider.get_model(model_name)


def build_agents(config: dict[str, Any], prompts_dir: Path) -> dict[str, Agent]:
    models = config.get("models", {})
    vector_store_id = config.get("vector_store_id") or ""
    agents: dict[str, Agent] = {}
    agents["literature_scout"] = Agent(
        name="LiteratureScout",
        instructions=_read_prompt(_prompt_path("literature_scout", config, prompts_dir)),
        model=_model_for(
            "literature_scout",
            models.get("literature_scout", models.get("default")),
            config,
        ),
        model_settings=_model_settings_for("literature_scout", config),
        tools=_tools_for_agent("literature_scout", config, vector_store_id),
        output_type=TaskResult,
    )
    agents["paper_reader"] = Agent(
        name="PaperReader",
        instructions=_read_prompt(_prompt_path("paper_reader", config, prompts_dir)),
        model=_model_for(
            "paper_reader",
            models.get("paper_reader", models.get("default")),
            config,
        ),
        model_settings=_model_settings_for("paper_reader", config),
        tools=_tools_for_agent("paper_reader", config, vector_store_id),
        output_type=TaskResult,
    )
    agents["derivation_coder"] = Agent(
        name="DerivationCoder",
        instructions=_read_prompt(_prompt_path("derivation_coder", config, prompts_dir)),
        model=_model_for(
            "derivation_coder",
            models.get("derivation_coder", models.get("default")),
            config,
        ),
        model_settings=_model_settings_for("derivation_coder", config),
        tools=_tools_for_agent("derivation_coder", config, vector_store_id),
        output_type=TaskResult,
    )
    agents["verifier"] = Agent(
        name="Verifier",
        instructions=_read_prompt(_prompt_path("verifier", config, prompts_dir)),
        model=_model_for("verifier", models.get("verifier", models.get("default")), config),
        model_settings=_model_settings_for("verifier", config),
        tools=_tools_for_agent("verifier", config, vector_store_id),
        output_type=VerifierResult,
    )
    agents["orchestrator"] = Agent(
        name="Orchestrator",
        instructions=_read_prompt(_prompt_path("orchestrator", config, prompts_dir)),
        model=_model_for(
            "orchestrator",
            models.get("orchestrator", models.get("default")),
            config,
        ),
        model_settings=_model_settings_for("orchestrator", config),
        tools=_tools_for_agent("orchestrator", config, vector_store_id),
        output_type=TaskResult,
    )
    return agents
