from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset, DatasetVersion
from app.models.evaluation import (
    EvaluationCase,
    EvaluationRun,
    EvaluationRunTarget,
    EvaluationSuite,
    EvaluationSuiteTarget,
)
from app.models.experiment import Experiment
from app.models.project import Project
from app.models.project_file import ProjectFile


class SDKGenerationError(Exception):
    """Raised when Forge cannot generate a requested SDK/project."""


@dataclass
class GeneratedFile:
    path: str
    content: str


@dataclass
class SDKGenerationResult:
    target: str
    language: str
    framework: str
    files: list[GeneratedFile] = field(default_factory=list)
    install_command: str = ""
    run_command: str = ""
    env_filename: str = ".env.example"
    env_example: str = ""
    usage: str = ""
    warnings: list[str] = field(default_factory=list)
    project: dict[str, Any] = field(default_factory=dict)
    workflow: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)


class SDKService:
    """
    Workflow-aware N-ATLAS Forge project generator.

    Forge context:
        Project
        Codebase
        Playground
        Datasets
        Evaluation suites
        Evaluation runs
        Regression context

    Generated applications never receive the Forge/server API key.
    """

    MAX_CONTEXT_FILES = 120
    MAX_FILE_CHARS = 50_000
    MAX_EXPERIMENTS = 40
    MAX_DATASETS = 30
    MAX_SUITES = 30
    MAX_RUNS = 50
    MAX_CASES_PER_SUITE = 100

    VALID_TARGETS = {
        "frontend",
        "backend",
        "fullstack",
        "sdk",
    }

    VALID_LANGUAGES = {
        "typescript",
        "javascript",
        "python",
        "java",
        "go",
        "csharp",
        "php",
        "ruby",
        "rust",
        "kotlin",
        "swift",
    }

    FRAMEWORK_ALIASES = {
        # Full-stack
        "react-express": "react-express",
        "react+express": "react-express",
        "react-express-typescript": "react-express",
        "react-fastify": "react-fastify",
        "vue-express": "vue-express",
        "vue-fastify": "vue-fastify",
        "angular-express": "angular-express",
        "svelte-express": "svelte-express",
        "svelte-fastify": "svelte-fastify",
        "vanilla-express": "vanilla-express",

        # Frontend
        "react": "react",
        "react-vite": "react-vite",
        "vite-react": "react-vite",
        "react_vite": "react-vite",
        "vue": "vue",
        "vue-vite": "vue",
        "angular": "angular",
        "svelte": "svelte",
        "vanilla": "vanilla",

        # Backend
        "fastapi": "fastapi",
        "flask": "flask",
        "django": "django",
        "express": "express",
        "fastify": "fastify",
        "spring-boot": "spring-boot",
        "spring": "spring-boot",
        "gin": "gin",
        "fiber": "fiber",
        "aspnet": "aspnet",
        "laravel": "laravel",
        "rails": "rails",
        "sinatra": "sinatra",
        "axum": "axum",
        "actix": "actix",
        "ktor": "ktor",
        "vapor": "vapor",

        # SDK / client
        "client": "client",
        "python-client": "client",
        "typescript-client": "client",

        # Languages
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
    }
    def __init__(self, db: Session):
        self.db = db

    # ============================================================
    # PUBLIC API
    # ============================================================

    def generate(
        self,
        project: Project,
        target: str = "fullstack",
        language: str = "typescript",
        framework: str = "react-express",
    ) -> SDKGenerationResult:
        target = self._normalize(target)
        language = self._normalize(language)
        framework = self._normalize(framework)

        self._validate_request(target, language, framework)

        workflow = self.collect_workflow(project)

        result = self._generate_project(
            project=project,
            workflow=workflow,
            target=target,
            language=language,
            framework=framework,
        )

        result.project = self._project_summary(project, workflow)
        result.workflow = workflow
        result.manifest = self._build_manifest(
            project=project,
            workflow=workflow,
            target=target,
            language=language,
            framework=framework,
            files=result.files,
        )

        return result

    # ============================================================
    # NORMALIZATION / VALIDATION
    # ============================================================

    def _normalize(self, value: Any) -> str:
        if value is None:
            return ""

        value = str(value).strip().lower()

        value = value.replace("_", "-")
        value = re.sub(r"\s+", "-", value)
        value = re.sub(r"-+", "-", value)

        return self.FRAMEWORK_ALIASES.get(value, value)

    def _validate_request(
        self,
        target: str,
        language: str,
        framework: str,
    ) -> None:
        if target not in self.VALID_TARGETS:
            raise SDKGenerationError(
                f"Unsupported generation target '{target}'. "
                f"Supported targets: {', '.join(sorted(self.VALID_TARGETS))}."
            )

        if language not in self.VALID_LANGUAGES:
            raise SDKGenerationError(
                f"Unsupported language '{language}'. "
                f"Supported languages: {', '.join(sorted(self.VALID_LANGUAGES))}."
            )

        if framework not in self.FRAMEWORK_ALIASES:
            raise SDKGenerationError(
                f"Unsupported framework '{framework}'."
            )

        if target == "frontend":
            allowed = {
                "react",
                "react-vite",
                "vue",
                "angular",
                "svelte",
                "vanilla",
                "react-express",
                "react-fastify",
                "vue-express",
                "vue-fastify",
                "angular-express",
                "svelte-express",
                "vanilla-express",
            }

            if framework not in allowed:
                raise SDKGenerationError(
                    f"Framework '{framework}' cannot be used for a frontend target."
                )

            if language not in {
                "typescript",
                "javascript",
            }:
                raise SDKGenerationError(
                    f"Language '{language}' cannot be used for a frontend target. "
                    "Frontend targets currently support TypeScript and JavaScript."
                )

        elif target == "backend":
            allowed = {
                "express",
                "fastify",
                "fastapi",
                "flask",
                "django",
                "spring-boot",
                "gin",
                "fiber",
                "aspnet",
                "laravel",
                "rails",
                "sinatra",
                "axum",
                "actix",
                "ktor",
                "vapor",
                "react-express",
                "react-fastify",
            }

            if framework not in allowed:
                raise SDKGenerationError(
                    f"Framework '{framework}' cannot be used for a backend target."
                )

            if language not in {
                "typescript",
                "javascript",
                "python",
                "java",
                "go",
                "csharp",
                "php",
                "ruby",
                "rust",
                "kotlin",
                "swift",
            }:
                raise SDKGenerationError(
                    f"Language '{language}' cannot be used for a backend target."
                )

        elif target == "fullstack":
            allowed = {
                "react-express",
                "react-fastify",
                "vue-express",
                "vue-fastify",
                "svelte-express",
                "svelte-fastify",
                "angular-express",
                "vanilla-express",
            }

            if framework not in allowed:
                raise SDKGenerationError(
                    f"Framework '{framework}' cannot be used for a fullstack target."
                )

            if language not in {
                "typescript",
                "javascript",
            }:
                raise SDKGenerationError(
                    f"Language '{language}' cannot be used for a fullstack target. "
                    "Fullstack targets currently support TypeScript and JavaScript."
                )

        elif target == "sdk":
            allowed = {
                "client",
                "python-client",
                "typescript-client",
            }

            if framework not in allowed:
                raise SDKGenerationError(
                    f"Framework '{framework}' cannot be used for an SDK target."
                )

            if language not in {
                "python",
                "typescript",
                "javascript",
            }:
                raise SDKGenerationError(
                    f"Language '{language}' cannot be used for an SDK target."
                )
        
    # ============================================================
    # WORKFLOW
    # ============================================================

    def collect_workflow(self, project: Project) -> dict[str, Any]:
        project_id = int(project.id)

        files = self._load_project_files(project_id)
        experiments = self._load_experiments(project_id)
        datasets = self._load_datasets(project_id)
        suites = self._load_evaluation_suites(project_id)
        runs = self._load_evaluation_runs(project_id)

        codebase: list[dict[str, Any]] = []
        natlas_files: list[dict[str, Any]] = []

        for project_file in files:
            path = project_file.path or ""

            if self._should_skip_context_file(path):
                continue

            content = ""

            if not project_file.is_binary:
                content = project_file.content or ""

            sanitized = self._sanitize_source(content)

            item = {
                "id": project_file.id,
                "path": self._sanitize_path(path),
                "language": self._safe_text(
                    project_file.language
                ),
                "size": int(
                    project_file.size
                    or len(content)
                ),
                "is_binary": bool(
                    project_file.is_binary
                ),
                "content": sanitized,
                "sha256": self._sha256(content),
            }

            codebase.append(item)

            if self._contains_natlas(content):
                natlas_files.append({
                    "path": item["path"],
                    "language": item["language"],
                })

            if len(codebase) >= self.MAX_CONTEXT_FILES:
                break

        experiment_context = []

        for experiment in experiments:
            experiment_context.append({
                "id": experiment.id,
                "name": self._safe_text(
                    experiment.name
                ),
                "system_prompt": self._safe_text(
                    experiment.system_prompt
                ),
                "user_prompt": self._safe_text(
                    experiment.user_prompt
                ),
                "language": self._safe_text(
                    experiment.language
                ),
                "model_name": self._safe_text(
                    experiment.model_name
                ),
                "request": self._sanitize_config(
                    experiment.request_payload
                ),
                "response": self._sanitize_config(
                    experiment.response_payload
                ),
                "response_text": self._safe_text(
                    self._extract_response(
                        experiment.response_payload
                    )
                ),
                "latency_ms": self._number(
                    experiment.latency_ms
                ),
                "created_at": self._serialize_datetime(
                    experiment.created_at
                ),
            })

        dataset_context = []

        for dataset in datasets:
            version = self._latest_dataset_version(
                dataset
            )

            dataset_context.append({
                "id": dataset.id,
                "name": self._safe_text(
                    dataset.name
                ),
                "description": self._safe_text(
                    dataset.description
                ),
                "format": self._safe_text(
                    dataset.format
                ),
                "latest_version": int(
                    dataset.latest_version or 1
                ),
                "version": (
                    self._dataset_version_summary(
                        version
                    )
                    if version
                    else None
                ),
            })

        suite_context = []

        for suite in suites:
            cases = self._load_suite_cases(
                suite.id
            )
            targets = self._load_suite_targets(
                suite.id
            )

            suite_context.append({
                "id": suite.id,
                "name": self._safe_text(
                    suite.name
                ),
                "description": self._safe_text(
                    suite.description
                ),
                "category": self._safe_text(
                    suite.category
                ),
                "dataset_id": suite.dataset_id,
                "dataset_version": suite.dataset_version,
                "configuration": self._sanitize_config(
                    suite.configuration
                ),
                "active": bool(suite.active),
                "cases": [
                    self._case_summary(case)
                    for case in cases[
                        : self.MAX_CASES_PER_SUITE
                    ]
                ],
                "target_files": [
                    self._suite_target_summary(target)
                    for target in targets
                ],
                "case_count": len(cases),
            })

        run_context = [
            self._serialize_run(run)
            for run in runs
        ]

        best_run = self._best_run(runs)

        return {
            "project": {
                "id": project.id,
                "name": self._safe_text(
                    project.name
                ),
                "description": self._safe_text(
                    project.description
                ),
                "default_language": self._safe_text(
                    project.default_language
                ),
                "model_name": self._safe_text(
                    project.model_name
                ),
                "configuration": self._sanitize_config(
                    project.configuration
                ),
            },
            "codebase": {
                "file_count": len(codebase),
                "files": codebase,
                "natlas_integrated": bool(
                    natlas_files
                ),
                "natlas_files": natlas_files,
            },
            "playground": {
                "experiment_count": len(
                    experiment_context
                ),
                "experiments": experiment_context,
            },
            "datasets": {
                "dataset_count": len(
                    dataset_context
                ),
                "datasets": dataset_context,
            },
            "evaluations": {
                "suite_count": len(
                    suite_context
                ),
                "suites": suite_context,
                "run_count": len(run_context),
                "runs": run_context,
                "best_run": (
                    self._serialize_run(best_run)
                    if best_run
                    else None
                ),
                "regression": self._build_regression_context(
                    runs
                ),
            },
            "natlas": {
                "integrated": bool(
                    natlas_files
                ),
                "files": natlas_files,
                "model": self._safe_text(
                    project.model_name or "N-ATLAS"
                ),
            },
        }

    # ============================================================
    # DATABASE
    # ============================================================

    def _load_project_files(
        self,
        project_id: int,
    ) -> list[ProjectFile]:
        return list(
            self.db.scalars(
                select(ProjectFile)
                .where(
                    ProjectFile.project_id
                    == project_id
                )
                .order_by(
                    ProjectFile.path.asc()
                )
            ).all()
        )

    def _load_experiments(
        self,
        project_id: int,
    ) -> list[Experiment]:
        return list(
            self.db.scalars(
                select(Experiment)
                .where(
                    Experiment.project_id
                    == project_id
                )
                .order_by(
                    Experiment.created_at.desc()
                )
                .limit(
                    self.MAX_EXPERIMENTS
                )
            ).all()
        )

    def _load_datasets(
        self,
        project_id: int,
    ) -> list[Dataset]:
        return list(
            self.db.scalars(
                select(Dataset)
                .where(
                    Dataset.project_id
                    == project_id
                )
                .order_by(
                    Dataset.updated_at.desc()
                )
                .limit(
                    self.MAX_DATASETS
                )
            ).all()
        )

    def _load_evaluation_suites(
        self,
        project_id: int,
    ) -> list[EvaluationSuite]:
        return list(
            self.db.scalars(
                select(EvaluationSuite)
                .where(
                    EvaluationSuite.project_id
                    == project_id
                )
                .order_by(
                    EvaluationSuite.updated_at.desc()
                )
                .limit(
                    self.MAX_SUITES
                )
            ).all()
        )

    def _load_evaluation_runs(
        self,
        project_id: int,
    ) -> list[EvaluationRun]:
        return list(
            self.db.scalars(
                select(EvaluationRun)
                .where(
                    EvaluationRun.project_id
                    == project_id
                )
                .order_by(
                    EvaluationRun.created_at.desc()
                )
                .limit(
                    self.MAX_RUNS
                )
            ).all()
        )

    def _load_suite_cases(
        self,
        suite_id: int,
    ) -> list[EvaluationCase]:
        return list(
            self.db.scalars(
                select(EvaluationCase)
                .where(
                    EvaluationCase.suite_id
                    == suite_id
                )
                .order_by(
                    EvaluationCase.position.asc(),
                    EvaluationCase.id.asc(),
                )
                .limit(
                    self.MAX_CASES_PER_SUITE
                )
            ).all()
        )

    def _load_suite_targets(
        self,
        suite_id: int,
    ) -> list[EvaluationSuiteTarget]:
        return list(
            self.db.scalars(
                select(EvaluationSuiteTarget)
                .where(
                    EvaluationSuiteTarget.suite_id
                    == suite_id
                )
                .order_by(
                    EvaluationSuiteTarget.id.asc()
                )
            ).all()
        )

    def _load_run_targets(
        self,
        run_id: int,
    ) -> list[EvaluationRunTarget]:
        return list(
            self.db.scalars(
                select(EvaluationRunTarget)
                .where(
                    EvaluationRunTarget.run_id
                    == run_id
                )
                .order_by(
                    EvaluationRunTarget.id.asc()
                )
            ).all()
        )

    def _latest_dataset_version(
        self,
        dataset: Dataset,
    ) -> DatasetVersion | None:
        version = self.db.scalar(
            select(DatasetVersion)
            .where(
                DatasetVersion.dataset_id
                == dataset.id,
                DatasetVersion.version
                == dataset.latest_version,
            )
        )

        if version:
            return version

        return self.db.scalar(
            select(DatasetVersion)
            .where(
                DatasetVersion.dataset_id
                == dataset.id
            )
            .order_by(
                DatasetVersion.version.desc()
            )
        )

    # ============================================================
    # SERIALIZATION
    # ============================================================

    def _serialize_run(
        self,
        run: EvaluationRun | None,
    ) -> dict[str, Any]:
        if not run:
            return {}

        targets = self._load_run_targets(
            run.id
        )

        return {
            "id": run.id,
            "suite_name": self._safe_text(
                run.suite_name
            ),
            "dataset_id": run.dataset_id,
            "dataset_version": run.dataset_version,
            "status": self._safe_text(
                run.status
            ),
            "total_tests": int(
                run.total_tests or 0
            ),
            "passed_tests": int(
                run.passed_tests or 0
            ),
            "failed_tests": int(
                run.failed_tests or 0
            ),
            "score": self._number(
                run.score
            ),
            "results": self._sanitize_records(
                run.results
            ),
            "category_summary": self._sanitize_config(
                run.category_summary
            ),
            "created_at": self._serialize_datetime(
                run.created_at
            ),
            "target_files": [
                {
                    "project_file_id":
                        target.project_file_id,
                    "path":
                        self._sanitize_path(
                            target.path_snapshot
                        ),
                    "content_hash":
                        self._safe_text(
                            target.content_hash
                        ),
                    "language":
                        self._safe_text(
                            target.language_snapshot
                        ),
                    "size": int(
                        target.file_size_snapshot
                        or 0
                    ),
                }
                for target in targets
            ],
        }

    def _case_summary(
        self,
        case: EvaluationCase,
    ) -> dict[str, Any]:
        return {
            "id": case.id,
            "name": self._safe_text(
                case.name
            ),
            "input": self._safe_text(
                case.input
            ),
            "expected": self._safe_text(
                case.expected
            ),
            "category": self._safe_text(
                case.category
            ),
            "language": self._safe_text(
                case.language
            ),
            "position": int(
                case.position or 0
            ),
            "enabled": bool(
                case.enabled
            ),
            "dataset_record_index":
                case.dataset_record_index,
        }

    def _suite_target_summary(
        self,
        target: EvaluationSuiteTarget,
    ) -> dict[str, Any]:
        project_file = target.project_file

        return {
            "project_file_id":
                target.project_file_id,
            "path": self._sanitize_path(
                project_file.path
                if project_file
                else ""
            ),
            "language": self._safe_text(
                project_file.language
                if project_file
                else ""
            ),
        }

    def _dataset_version_summary(
        self,
        version: DatasetVersion,
    ) -> dict[str, Any]:
        return {
            "id": version.id,
            "version": int(
                version.version or 1
            ),
            "record_count": int(
                version.record_count or 0
            ),
            "validation_report":
                self._sanitize_config(
                    version.validation_report
                ),
            "records_preview":
                self._sanitize_records(
                    version.records,
                    limit=10,
                ),
            "created_at":
                self._serialize_datetime(
                    version.created_at
                ),
        }

    # ============================================================
    # SECURITY
    # ============================================================

    def _sanitize_source(
        self,
        content: Any,
    ) -> str:
        if content is None:
            return ""

        text = str(content)

        if len(text) > self.MAX_FILE_CHARS:
            text = (
                text[: self.MAX_FILE_CHARS]
                + "\n\n# [Forge] Source truncated for safety.\n"
            )

        patterns = [
            (
                r'(?im)^(\s*(?:NATLAS_API_KEY|OPENAI_API_KEY|'
                r'ANTHROPIC_API_KEY|GOOGLE_API_KEY|API_KEY|'
                r'SECRET_KEY|ACCESS_TOKEN|AUTH_TOKEN|PASSWORD|'
                r'PASSWD|CLIENT_SECRET|PRIVATE_KEY)\s*[=:]\s*)(.+)$',
                r'\1[REDACTED]',
            ),
            (
                r'(?i)(["\']?(?:api[_-]?key|secret[_-]?key|'
                r'access[_-]?token|auth[_-]?token|client[_-]?secret|'
                r'password|passwd|private[_-]?key)["\']?\s*[:=]\s*)'
                r'(["\'])(.*?)\2',
                r'\1\2[REDACTED]\2',
            ),
            (
                r'(?i)(authorization\s*[:=]\s*["\']?\s*bearer\s+)'
                r'[A-Za-z0-9._\-]+',
                r'\1[REDACTED]',
            ),
            (
                r'(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}',
                "Bearer [REDACTED]",
            ),
            (
                r'\bsk-[A-Za-z0-9_-]{20,}\b',
                "[REDACTED]",
            ),
            (
                r'\bAIza[0-9A-Za-z_-]{20,}\b',
                "[REDACTED]",
            ),
            (
                r'(?i)(\b(?:token|access_token|auth_token|'
                r'secret|secret_key)\b\s*[:=]\s*)'
                r'(["\']?)[A-Za-z0-9._\-]{20,}\2',
                r'\1\2[REDACTED]\2',
            ),
        ]

        for pattern, replacement in patterns:
            text = re.sub(
                pattern,
                replacement,
                text,
            )

        return text


    def _build_manifest(
        self,
        project: Project,
        workflow: dict[str, Any],
        target: str,
        language: str,
        framework: str,
        files: list[GeneratedFile] | None = None,
    ) -> dict[str, Any]:
        """Build the machine-readable manifest for generated output."""

        if not isinstance(workflow, dict):
            workflow = {}

        codebase = workflow.get("codebase", {})
        datasets = workflow.get("datasets", {})
        evaluations = workflow.get("evaluations", {})
        playground = workflow.get("playground", {})

        if not isinstance(codebase, dict):
            codebase = {}

        if not isinstance(datasets, dict):
            datasets = {}

        if not isinstance(evaluations, dict):
            evaluations = {}

        if not isinstance(playground, dict):
            playground = {}

        generated_files = files or []

        file_manifest = []

        for generated_file in generated_files:
            if isinstance(generated_file, GeneratedFile):
                path = generated_file.path
                content = generated_file.content
            elif isinstance(generated_file, dict):
                path = str(generated_file.get("path", ""))
                content = str(generated_file.get("content", ""))
            else:
                path = str(getattr(generated_file, "path", ""))
                content = str(getattr(generated_file, "content", ""))

            file_manifest.append(
                {
                    "path": path,
                    "size": len(content.encode("utf-8")),
                    "sha256": hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest(),
                }
            )

        return {
            "name": getattr(project, "name", "N-ATLAS project"),
            "project_id": getattr(project, "id", None),
            "generator": "N-ATLAS Forge",
            "version": "1.0",
            "target": target,
            "language": language,
            "framework": framework,
            "model": getattr(project, "model_name", "N-ATLAS"),

            "integration": {
                "provider": "N-ATLAS",
                "required_environment": [
                    "NATLAS_API_KEY",
                    "NATLAS_BASE_URL",
                    "NATLAS_CHAT_ENDPOINT",
                    "NATLAS_MODEL",
                ],
            },

            "workflow": {
                "codebase_files": codebase.get("file_count", 0),
                "datasets": datasets.get("dataset_count", 0),
                "evaluation_suites": evaluations.get("suite_count", 0),
                "evaluation_runs": evaluations.get("run_count", 0),
                "playground_experiments": playground.get(
                    "experiment_count",
                    0,
                ),
            },

            "generated_output": {
                "file_count": len(file_manifest),
                "files": file_manifest,
            },

            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value into JSON-safe output."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, dict):
            return {
                str(key): self._serialize_value(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                self._serialize_value(item)
                for item in value
            ]

        return str(value)


    def _is_secret_key(
        self,
        key: str,
    ) -> bool:
        normalized = re.sub(
            r"[^a-z0-9]",
            "",
            str(key).lower(),
        )

        secret_markers = {
            "natlasapikey",
            "apikey",
            "apikeyvalue",
            "secret",
            "secretkey",
            "accesstoken",
            "authtoken",
            "authorization",
            "password",
            "passwd",
            "clientsecret",
            "privatekey",
        }

        return (
            normalized in secret_markers
            or normalized.endswith("apikey")
            or normalized.endswith("secret")
            or normalized.endswith("password")
            or normalized.endswith("token")
        )

    def _should_skip_context_file(
        self,
        path: str,
    ) -> bool:
        normalized = (
            str(path)
            .replace("\\", "/")
            .lower()
        )

        ignored = (
            "node_modules/",
            ".git/",
            ".next/",
            "dist/",
            "build/",
            ".venv/",
            "venv/",
            "__pycache__/",
            ".idea/",
            ".vscode/",
        )

        if any(
            part in normalized
            for part in ignored
        ):
            return True

        filename = normalized.rsplit(
            "/",
            1,
        )[-1]

        return filename in {
            ".env",
            ".env.local",
            ".env.production",
            ".env.development",
        }

    def _generation_warnings(
        self,
        workflow: dict[str, Any],
        target: str,
    ) -> list[str]:
        """Build warnings for generated project output."""
        warnings: list[str] = []

        if not isinstance(workflow, dict):
            workflow = {}

        codebase = workflow.get("codebase", {})
        datasets = workflow.get("datasets", {})
        evaluations = workflow.get("evaluations", {})

        if not isinstance(codebase, dict):
            codebase = {}

        if not isinstance(datasets, dict):
            datasets = {}

        if not isinstance(evaluations, dict):
            evaluations = {}

        try:
            file_count = int(codebase.get("file_count", 0) or 0)
        except (TypeError, ValueError):
            file_count = 0

        try:
            dataset_count = int(datasets.get("dataset_count", 0) or 0)
        except (TypeError, ValueError):
            dataset_count = 0

        try:
            suite_count = int(evaluations.get("suite_count", 0) or 0)
        except (TypeError, ValueError):
            suite_count = 0

        if file_count == 0:
            warnings.append(
                "No project source files were available when the SDK was generated."
            )

        if dataset_count == 0:
            warnings.append(
                "No datasets are currently attached to this Forge project."
            )

        if suite_count == 0:
            warnings.append(
                "No evaluation suites are currently configured for this project."
            )

        warnings.append(
            "The generated project expects NATLAS_API_KEY to be supplied "
            "through its environment configuration."
        )

        warnings.append(
            f"Generated target: {target}. "
            "Review the generated integration before production deployment."
        )

        return warnings

    def _sanitize_path(
        self,
        path: Any,
    ) -> str:
        value = str(
            path or ""
        ).replace("\\", "/")

        value = re.sub(
            r"^\./",
            "",
            value,
        )

        value = value.replace(
            "..",
            "",
        )

        return value[:1000]

    def _contains_natlas(
        self,
        content: Any,
    ) -> bool:
        if content is None:
            return False

        text = str(content).lower()

        markers = (
            "n-atlas",
            "natlas",
            "n_atlas",
            "n atlas",
            "natlas_api_key",
            "natlas_base_url",
            "natlas_model",
            "natlas_chat_endpoint",
            "/v1/chat/completions",
            "chat/completions",
        )

        return any(
            marker in text
            for marker in markers
        )

    # ============================================================
    # HELPERS
    # ============================================================

    def _safe_text(
        self,
        value: Any,
        max_length: int = 20_000,
    ) -> str:
        if value is None:
            return ""

        text = str(value)

        if len(text) > max_length:
            return (
                text[:max_length]
                + "\n[truncated]"
            )

        return text

    def _number(
        self,
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

    def _serialize_datetime(
        self,
        value: Any,
    ) -> str:
        if value is None:
            return ""

        if isinstance(value, datetime):
            return value.isoformat()

        return str(value)

    def _sha256(
        self,
        value: Any,
    ) -> str:
        return hashlib.sha256(
            str(value or "")
            .encode("utf-8", errors="replace")
        ).hexdigest()


    def _safe_json(self, value: Any) -> Any:
        """Convert a value into JSON-safe data without exposing secrets."""
        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, dict):
            return {
                str(key): self._safe_json(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                self._safe_json(item)
                for item in value
            ]

        if hasattr(value, "model_dump"):
            try:
                return self._safe_json(value.model_dump())
            except Exception:
                pass

        if hasattr(value, "dict"):
            try:
                return self._safe_json(value.dict())
            except Exception:
                pass

        return str(value)



    def _sanitize_records(
        self,
        records: Any,
        limit: int = 20,
    ) -> Any:
        if records is None:
            return []

        if isinstance(records, list):
            return [
                self._sanitize_config(item)
                for item in records[:limit]
            ]

        if isinstance(records, dict):
            return self._sanitize_config(
                records
            )

        return self._safe_text(records)

    def _sanitize_config(
        self,
        value: Any,
    ) -> Any:
        if value is None:
            return None

        if isinstance(value, str):
            return self._sanitize_source(
                value
            )

        if isinstance(value, dict):
            result = {}

            for key, item in value.items():
                key_text = str(key)

                if self._is_secret_key(
                    key_text
                ):
                    result[key_text] = (
                        "[REDACTED]"
                    )
                else:
                    result[key_text] = (
                        self._sanitize_config(
                            item
                        )
                    )

            return result

        if isinstance(value, list):
            return [
                self._sanitize_config(item)
                for item in value[:100]
            ]

        if isinstance(value, tuple):
            return [
                self._sanitize_config(item)
                for item in value[:100]
            ]

        if isinstance(
            value,
            (int, float, bool),
        ):
            return value

        return self._safe_text(value)

    def _extract_response(
        self,
        response: Any,
    ) -> str:
        if response is None:
            return ""

        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            choices = response.get(
                "choices"
            )

            if (
                isinstance(choices, list)
                and choices
            ):
                first = choices[0]

                if isinstance(
                    first,
                    dict,
                ):
                    message = first.get(
                        "message"
                    )

                    if isinstance(
                        message,
                        dict,
                    ):
                        content = message.get(
                            "content"
                        )

                        if isinstance(
                            content,
                            str,
                        ):
                            return content

                        if isinstance(
                            content,
                            list,
                        ):
                            parts = []

                            for item in content:
                                if not isinstance(
                                    item,
                                    dict,
                                ):
                                    continue

                                text = item.get(
                                    "text"
                                )

                                if isinstance(
                                    text,
                                    str,
                                ):
                                    parts.append(
                                        text
                                    )

                            if parts:
                                return "\n".join(
                                    parts
                                )

                    text = first.get("text")

                    if isinstance(
                        text,
                        str,
                    ):
                        return text

            for key in (
                "response",
                "output",
                "content",
                "text",
                "answer",
                "result",
                "message",
            ):
                value = response.get(key)

                if isinstance(
                    value,
                    str,
                ):
                    return value

                if isinstance(
                    value,
                    dict,
                ):
                    nested = (
                        self._extract_response(
                            value
                        )
                    )

                    if nested:
                        return nested

            return ""

        if isinstance(
            response,
            list,
        ):
            parts = []

            for item in response:
                extracted = (
                    self._extract_response(
                        item
                    )
                )

                if extracted:
                    parts.append(
                        extracted
                    )

            return "\n".join(parts)

        return str(response)

    def _best_run(
        self,
        runs: list[Any],
    ) -> Any:
        if not runs:
            return None

        def value(
            obj: Any,
            *names: str,
            default: Any = None,
        ) -> Any:
            for name in names:
                if isinstance(
                    obj,
                    dict,
                ) and name in obj:
                    return obj[name]

                if hasattr(obj, name):
                    result = getattr(
                        obj,
                        name,
                    )

                    if result is not None:
                        return result

            return default

        def number(
            obj: Any,
            *names: str,
        ) -> float:
            return self._number(
                value(
                    obj,
                    *names,
                    default=0,
                )
            )

        def timestamp(
            obj: Any,
        ) -> str:
            raw = value(
                obj,
                "created_at",
                "completed_at",
                "started_at",
                default="",
            )

            return (
                ""
                if raw is None
                else str(raw)
            )

        return max(
            runs,
            key=lambda run: (
                number(
                    run,
                    "score",
                    "quality_score",
                    "overall_score",
                ),
                number(
                    run,
                    "pass_rate",
                    "passed_rate",
                    "success_rate",
                ),
                timestamp(run),
            ),
        )

    def _build_regression_context(
        self,
        runs: list[EvaluationRun],
    ) -> dict[str, Any]:
        if not runs:
            return {
                "available": False,
                "latest": None,
                "previous": None,
                "score_delta": 0,
            }

        ordered = sorted(
            runs,
            key=lambda run: (
                run.created_at
                or datetime.min
            ),
            reverse=True,
        )

        latest = ordered[0]
        previous = (
            ordered[1]
            if len(ordered) > 1
            else None
        )

        latest_score = self._number(
            latest.score
        )

        previous_score = (
            self._number(
                previous.score
            )
            if previous
            else None
        )

        return {
            "available": True,
            "latest": self._serialize_run(
                latest
            ),
            "previous": (
                self._serialize_run(
                    previous
                )
                if previous
                else None
            ),
            "score_delta": (
                latest_score
                - previous_score
                if previous_score is not None
                else 0
            ),
        }


    def _escape_html(self, value: Any) -> str:
        """Escape text safely for generated HTML."""
        if value is None:
            return ""

        text = str(value)

        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )


    # ============================================================
    # PROJECT GENERATION
    # ============================================================

    def _generate_project(
        self,
        project: Project,
        workflow: dict[str, Any],
        target: str,
        language: str,
        framework: str,
    ) -> SDKGenerationResult:
        result = SDKGenerationResult(
            target=target,
            language=language,
            framework=framework,
        )

        if target == "fullstack":
            self._generate_fullstack(
                result,
                project,
                workflow,
                framework,
            )

        elif target == "frontend":
            self._generate_frontend(
                result,
                project,
                workflow,
                framework,
            )

        elif target == "backend":
            self._generate_backend(
                result,
                project,
                workflow,
                framework,
            )

        elif target == "sdk":
            self._generate_sdk(
                result,
                project,
                workflow,
                language,
            )

        result.env_filename = ".env.example"
        result.env_example = (
            self._env_example()
        )

        result.files.append(
            GeneratedFile(
                ".env.example",
                result.env_example,
            )
        )

        result.files.append(
            GeneratedFile(
                ".gitignore",
                self._gitignore(),
            )
        )

        result.files.append(
            GeneratedFile(
                "README.md",
                self._readme(
                    project,
                    workflow,
                    target,
                    language,
                    framework,
                ),
            )
        )

        result.usage = self._usage(
            project,
            target,
            framework,
        )

        result.warnings = (
            self._generation_warnings(
                workflow,
                target,
            )
        )

        return result

    def _generate_fullstack(
        self,
        result: SDKGenerationResult,
        project: Project,
        workflow: dict[str, Any],
        framework: str,
    ) -> None:
        if framework in {
            "react-express",
            "react-fastify",
            "vue-express",
            "vue-fastify",
            "angular-express",
            "svelte-express",
            "vanilla-express",
        }:
            frontend = self._frontend_framework(
                framework
            )

            backend = self._backend_framework(
                framework
            )

            self._add_frontend_files(
                result,
                project,
                workflow,
                frontend,
            )

            self._add_backend_files(
                result,
                project,
                workflow,
                backend,
            )

            result.files.append(
                GeneratedFile(
                    "package.json",
                    self._typescript_root_package(
                        project
                    ),
                )
            )

            result.files.append(
                GeneratedFile(
                    "tsconfig.json",
                    self._root_tsconfig(),
                )
            )

            result.install_command = (
                "npm run install:all"
            )

            result.run_command = "npm run dev"

            return

        self._generate_frontend(
            result,
            project,
            workflow,
            framework,
        )

        self._generate_backend(
            result,
            project,
            workflow,
            "express",
        )

    def _generate_frontend(
        self,
        result: SDKGenerationResult,
        project: Project,
        workflow: dict[str, Any],
        framework: str,
    ) -> None:
        framework = self._frontend_framework(
            framework
        )

        self._add_frontend_files(
            result,
            project,
            workflow,
            framework,
        )

        result.install_command = (
            "npm install"
        )

        result.run_command = (
            "npm run dev"
        )

    def _generate_backend(
        self,
        result: SDKGenerationResult,
        project: Project,
        workflow: dict[str, Any],
        framework: str,
    ) -> None:
        framework = self._backend_framework(
            framework
        )

        self._add_backend_files(
            result,
            project,
            workflow,
            framework,
        )

        result.install_command = (
            "npm install"
        )

        result.run_command = (
            "npm run dev"
        )

    def _generate_sdk(
        self,
        result: SDKGenerationResult,
        project: Project,
        workflow: dict[str, Any],
        language: str,
    ) -> None:
        if language == "python":
            result.files.extend([
                GeneratedFile(
                    "natlas_client.py",
                    self._python_sdk(),
                ),
                GeneratedFile(
                    "example.py",
                    self._python_sdk_example(project, workflow)
                ),
                GeneratedFile(
                    "pyproject.toml",
                    self._python_pyproject(
                        project
                    ),
                ),
            ])

            result.install_command = (
                "pip install requests python-dotenv"
            )

            result.run_command = (
                "python example.py"
            )

            return

        result.files.extend([
            GeneratedFile(
                "src/natlas-client.ts",
                self._typescript_sdk(),
            ),
            GeneratedFile(
                "src/index.ts",
                self._typescript_sdk_index(),
            ),
            GeneratedFile(
                "package.json",
                self._sdk_package(
                    project,
                    language,
                ),
            ),
            GeneratedFile(
                "tsconfig.json",
                self._backend_tsconfig(),
            ),
        ])

        result.install_command = (
            "npm install"
        )

        result.run_command = (
            "npm run build"
        )

    # ============================================================
    # FRONTEND
    # ============================================================

    def _frontend_framework(
        self,
        framework: str,
    ) -> str:
        framework = self._normalize(
            framework
        )

        mapping = {
            "react-express": "react",
            "react-fastify": "react",
            "vue-express": "vue",
            "vue-fastify": "vue",
            "angular-express": "angular",
            "svelte-express": "svelte",
            "vanilla-express": "vanilla",
        }

        return mapping.get(
            framework,
            framework,
        )

    def _backend_framework(
        self,
        framework: str,
    ) -> str:
        framework = self._normalize(
            framework
        )

        mapping = {
            "react-express": "express",
            "react-fastify": "fastify",
            "vue-express": "express",
            "vue-fastify": "fastify",
            "angular-express": "express",
            "svelte-express": "express",
            "vanilla-express": "express",
        }

        return mapping.get(
            framework,
            framework,
        )

    def _json_file(self, data: Any) -> str:
        """Serialize generated project metadata/package files as readable JSON."""
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    def _escape_ts(self, value: Any) -> str:
        """
        Safely escape a Python value for insertion into a generated
        TypeScript/JavaScript string literal.
        """
        if value is None:
            return ""

        text = str(value)

        return (
            text
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace('"', '\\"')
            .replace("'", "\\'")
        )


    def _project_summary(
        self,
        project: Project,
        workflow: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the project metadata returned with generated SDK output."""
        if not isinstance(workflow, dict):
            workflow = {}

        codebase = workflow.get("codebase", {})
        datasets = workflow.get("datasets", {})
        evaluations = workflow.get("evaluations", {})
        playground = workflow.get("playground", {})

        if not isinstance(codebase, dict):
            codebase = {}
        if not isinstance(datasets, dict):
            datasets = {}
        if not isinstance(evaluations, dict):
            evaluations = {}
        if not isinstance(playground, dict):
            playground = {}

        return {
            "id": getattr(project, "id", None),
            "name": getattr(project, "name", None),
            "description": getattr(project, "description", None),
            "default_language": getattr(project, "default_language", None),
            "model_name": getattr(project, "model_name", None),
            "configuration": self._safe_json(
                getattr(project, "configuration", None) or {}
            ),
            "created_at": self._serialize_value(
                getattr(project, "created_at", None)
            ),
            "updated_at": self._serialize_value(
                getattr(project, "updated_at", None)
            ),
            "codebase": {
                "file_count": codebase.get("file_count", 0),
                "languages": codebase.get("languages", {}),
                "natlas_detected": codebase.get("natlas_detected", False),
            },
            "datasets": {
                "dataset_count": datasets.get("dataset_count", 0),
            },
            "evaluations": {
                "suite_count": evaluations.get("suite_count", 0),
                "run_count": evaluations.get("run_count", 0),
            },
            "playground": {
                "experiment_count": playground.get("experiment_count", 0),
            },
        }


    def _project_slug(self, name: Any) -> str:
        """Convert a project name into a safe npm/package/project slug."""
        value = str(name or "natlas-project").strip().lower()

        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = re.sub(r"-{2,}", "-", value)
        value = value.strip("-")

        if not value:
            value = "natlas-project"

        # npm/package names should not exceed this comfortably.
        return value[:80]


    def _usage(
        self,
        project: Project,
        target: str,
        framework: str,
    ) -> str:
        """Describe how the generated N-ATLAS project should be used."""
        project_name = str(
            getattr(project, "name", None) or "N-ATLAS project"
        )

        return (
            f"{project_name} was generated by N-ATLAS Forge "
            f"for the {target} target using the {framework} framework.\n\n"
            "The generated application is configured for N-ATLAS "
            "through the environment variables in .env.example. "
            "Set NATLAS_API_KEY before running the backend.\n\n"
            "The generated project preserves the N-ATLAS integration "
            "workflow captured by Forge and provides a ready-to-run "
            "starting point for development."
        )

    def _add_frontend_files(
        self,
        result: SDKGenerationResult,
        project: Project,
        workflow: dict[str, Any],
        framework: str,
    ) -> None:
        framework = self._frontend_framework(
            framework
        )

        if framework == "react":
            result.files.extend([
                GeneratedFile(
                    "frontend/package.json",
                    self._frontend_package(
                        "react"
                    ),
                ),
                GeneratedFile(
                    "frontend/index.html",
                    self._react_index(),
                ),
                GeneratedFile(
                    "frontend/src/main.tsx",
                    self._react_main(),
                ),
                GeneratedFile(
                    "frontend/src/App.tsx",
                    self._react_app(
                        project,
                        workflow,
                    ),
                ),
                GeneratedFile(
                    "frontend/src/index.css",
                    self._frontend_css(),
                ),
                GeneratedFile(
                    "frontend/vite.config.ts",
                    self._vite_config(
                        "react"
                    ),
                ),
            ])

        elif framework == "vue":
            result.files.extend([
                GeneratedFile(
                    "frontend/package.json",
                    self._frontend_package(
                        "vue"
                    ),
                ),
                GeneratedFile(
                    "frontend/index.html",
                    self._vue_index(),
                ),
                GeneratedFile(
                    "frontend/src/main.ts",
                    self._vue_main(),
                ),
                GeneratedFile(
                    "frontend/src/App.vue",
                    self._vue_app(
                        project,
                        workflow,
                    ),
                ),
                GeneratedFile(
                    "frontend/src/style.css",
                    self._frontend_css(),
                ),
                GeneratedFile(
                    "frontend/vite.config.ts",
                    self._vite_config(
                        "vue"
                    ),
                ),
            ])

        elif framework == "svelte":
            result.files.extend([
                GeneratedFile(
                    "frontend/package.json",
                    self._frontend_package(
                        "svelte"
                    ),
                ),
                GeneratedFile(
                    "frontend/index.html",
                    self._svelte_index(),
                ),
                GeneratedFile(
                    "frontend/src/main.ts",
                    self._svelte_main(),
                ),
                GeneratedFile(
                    "frontend/src/App.svelte",
                    self._svelte_app(
                        project,
                        workflow,
                    ),
                ),
                GeneratedFile(
                    "frontend/src/app.css",
                    self._frontend_css(),
                ),
                GeneratedFile(
                    "frontend/vite.config.ts",
                    self._vite_config(
                        "svelte"
                    ),
                ),
            ])

        elif framework == "angular":
            result.files.extend([
                GeneratedFile(
                    "frontend/package.json",
                    self._frontend_package(
                        "angular"
                    ),
                ),
                GeneratedFile(
                    "frontend/src/main.ts",
                    self._angular_main(),
                ),
                GeneratedFile(
                    "frontend/src/app/app.component.ts",
                    self._angular_component(
                        project
                    ),
                ),
                GeneratedFile(
                    "frontend/src/styles.css",
                    self._frontend_css(),
                ),
            ])

        else:
            result.files.extend([
                GeneratedFile(
                    "frontend/package.json",
                    self._frontend_package(
                        "vanilla"
                    ),
                ),
                GeneratedFile(
                    "frontend/index.html",
                    self._vanilla_index(
                        project
                    ),
                ),
                GeneratedFile(
                    "frontend/src/main.ts",
                    self._vanilla_main(
                        project,
                        workflow,
                    ),
                ),
                GeneratedFile(
                    "frontend/src/style.css",
                    self._frontend_css(),
                ),
                GeneratedFile(
                    "frontend/vite.config.ts",
                    self._vite_config(
                        "vanilla"
                    ),
                ),
            ])

    # ============================================================
    # BACKEND
    # ============================================================

    def _add_backend_files(
        self,
        result: SDKGenerationResult,
        project: Project,
        workflow: dict[str, Any],
        framework: str,
    ) -> None:
        framework = self._backend_framework(
            framework
        )

        if framework == "fastify":
            server = self._fastify_server(
                project,
                workflow,
            )

        else:
            server = self._express_server(
                project,
                workflow,
            )

        result.files.extend([
            GeneratedFile(
                "backend/package.json",
                self._backend_package(
                    framework
                ),
            ),
            GeneratedFile(
                "backend/tsconfig.json",
                self._backend_tsconfig(),
            ),
            GeneratedFile(
                "backend/src/server.ts",
                server,
            ),
        ])

    # ============================================================
    # REACT
    # ============================================================

    def _react_index(self) -> str:
        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1.0"
    />
    <title>N-ATLAS Forge</title>
  </head>
  <body>
    <div id="root"></div>
    <script
      type="module"
      src="/src/main.tsx"
    ></script>
  </body>
</html>
"""

    def _react_main(self) -> str:
        return """import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./index.css";

ReactDOM.createRoot(
  document.getElementById("root")!
).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""

    def _react_app(
        self,
        project: Project,
        workflow: dict[str, Any],
    ) -> str:
        project_name = self._escape_ts(
            project.name
            or "N-ATLAS App"
        )

        return """import { useState } from "react";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:3001";

export default function App() {
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function askNAtlas() {
    if (!prompt.trim()) return;

    setLoading(true);
    setError("");
    setResponse("");

    try {
      const result = await fetch(
        `${API_BASE_URL}/api/chat`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            prompt,
          }),
        }
      );

      const data = await result.json();

      if (!result.ok) {
        throw new Error(
          data?.error ||
            "N-ATLAS request failed."
        );
      }

      setResponse(data.response || "");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <span className="eyebrow">
          N-ATLAS • Forge
        </span>

        <h1>__PROJECT_NAME__</h1>

        <p>
          A production-ready N-ATLAS application
          generated from your Forge project.
        </p>

        <div className="card">
          <label htmlFor="prompt">
            Ask N-ATLAS
          </label>

          <textarea
            id="prompt"
            value={prompt}
            onChange={(event) =>
              setPrompt(event.target.value)
            }
            placeholder="Ask something..."
            rows={6}
          />

          <button
            type="button"
            onClick={askNAtlas}
            disabled={
              loading ||
              !prompt.trim()
            }
          >
            {loading
              ? "Thinking..."
              : "Send to N-ATLAS"}
          </button>

          {error && (
            <div className="error">
              {error}
            </div>
          )}

          {response && (
            <div className="response">
              <strong>Response</strong>
              <p>{response}</p>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
""".replace(
            "__PROJECT_NAME__",
            project_name,
        )

    # ============================================================
    # VUE
    # ============================================================

    def _vue_index(self) -> str:
        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1.0"
    />
    <title>N-ATLAS App</title>
  </head>
  <body>
    <div id="app"></div>
    <script
      type="module"
      src="/src/main.ts"
    ></script>
  </body>
</html>
"""

    def _vue_main(self) -> str:
        return """import { createApp } from "vue";

import App from "./App.vue";
import "./style.css";

createApp(App).mount("#app");
"""

    def _vue_app(
        self,
        project: Project,
        workflow: dict[str, Any],
    ) -> str:
        name = self._escape_html(
            project.name
            or "N-ATLAS App"
        )

        return """<script setup lang="ts">
import { ref } from "vue";

const prompt = ref("");
const response = ref("");
const error = ref("");
const loading = ref(false);

const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:3001";

async function askNAtlas() {
  if (!prompt.value.trim()) return;

  loading.value = true;
  error.value = "";
  response.value = "";

  try {
    const result = await fetch(
      `${apiBaseUrl}/api/chat`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt: prompt.value,
        }),
      }
    );

    const data = await result.json();

    if (!result.ok) {
      throw new Error(
        data?.error ||
          "N-ATLAS request failed."
      );
    }

    response.value =
      data.response || "";
  } catch (err) {
    error.value =
      err instanceof Error
        ? err.message
        : "Something went wrong.";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="app-shell">
    <section class="hero">
      <span class="eyebrow">
        N-ATLAS • Forge
      </span>

      <h1>__PROJECT_NAME__</h1>

      <p>
        A production-ready N-ATLAS application
        generated by Forge.
      </p>

      <div class="card">
        <label for="prompt">
          Ask N-ATLAS
        </label>

        <textarea
          id="prompt"
          v-model="prompt"
          rows="6"
          placeholder="Ask something..."
        />

        <button
          type="button"
          :disabled="
            loading ||
            !prompt.trim()
          "
          @click="askNAtlas"
        >
          {{
            loading
              ? "Thinking..."
              : "Send to N-ATLAS"
          }}
        </button>

        <div
          v-if="error"
          class="error"
        >
          {{ error }}
        </div>

        <div
          v-if="response"
          class="response"
        >
          <strong>Response</strong>
          <p>{{ response }}</p>
        </div>
      </div>
    </section>
  </main>
</template>
""".replace(
            "__PROJECT_NAME__",
            name,
        )

    # ============================================================
    # ANGULAR
    # ============================================================

    def _angular_main(self) -> str:
        return """import {
  bootstrapApplication,
} from "@angular/platform-browser";

import {
  AppComponent,
} from "./app/app.component";

bootstrapApplication(
  AppComponent
).catch(
  (error) =>
    console.error(error)
);
"""

    def _angular_component(
        self,
        project: Project,
    ) -> str:
        name = self._escape_html(
            project.name
            or "N-ATLAS App"
        )

        return """import {
  Component,
} from "@angular/core";

import {
  FormsModule,
} from "@angular/forms";

import {
  HttpClient,
  HttpClientModule,
} from "@angular/common/http";

import {
  firstValueFrom,
} from "rxjs";

@Component({
  selector: "app-root",
  standalone: true,
  imports: [
    FormsModule,
    HttpClientModule,
  ],
  template: `
    <main class="app-shell">
      <section class="hero">
        <span class="eyebrow">
          N-ATLAS • Forge
        </span>

        <h1>__PROJECT_NAME__</h1>

        <textarea
          [(ngModel)]="prompt"
          rows="6"
          placeholder="Ask something..."
        ></textarea>

        <button
          (click)="ask()"
          [disabled]="
            loading ||
            !prompt.trim()
          "
        >
          {{
            loading
              ? "Thinking..."
              : "Send to N-ATLAS"
          }}
        </button>

        <p
          *ngIf="error"
          class="error"
        >
          {{ error }}
        </p>

        <p *ngIf="response">
          {{ response }}
        </p>
      </section>
    </main>
  `,
})
export class AppComponent {
  prompt = "";
  response = "";
  error = "";
  loading = false;

  constructor(
    private http: HttpClient
  ) {}

  async ask() {
    if (!this.prompt.trim()) {
      return;
    }

    this.loading = true;
    this.error = "";
    this.response = "";

    try {
      const result =
        await firstValueFrom(
          this.http.post<{
            response?: string;
          }>(
            "http://localhost:3001/api/chat",
            {
              prompt: this.prompt,
            }
          )
        );

      this.response =
        result.response || "";
    } catch (error) {
      this.error =
        "N-ATLAS request failed.";
    } finally {
      this.loading = false;
    }
  }
}
""".replace(
            "__PROJECT_NAME__",
            name,
        )

    # ============================================================
    # SVELTE
    # ============================================================

    def _svelte_index(self) -> str:
        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1.0"
    />
    <title>N-ATLAS App</title>
  </head>
  <body>
    <div id="app"></div>
    <script
      type="module"
      src="/src/main.ts"
    ></script>
  </body>
</html>
"""

    def _svelte_main(self) -> str:
        return """import App from "./App.svelte";
import "./app.css";

const app =
  new App({
    target:
      document.getElementById(
        "app"
      )!,
  });

export default app;
"""

    def _svelte_app(
        self,
        project: Project,
        workflow: dict[str, Any],
    ) -> str:
        name = self._escape_html(
            project.name
            or "N-ATLAS App"
        )

        return """<script lang="ts">
  let prompt = "";
  let response = "";
  let error = "";
  let loading = false;

  const apiBaseUrl =
    import.meta.env.VITE_API_BASE_URL ||
    "http://localhost:3001";

  async function ask() {
    if (!prompt.trim()) return;

    loading = true;
    error = "";
    response = "";

    try {
      const result = await fetch(
        `${apiBaseUrl}/api/chat`,
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            prompt,
          }),
        }
      );

      const data =
        await result.json();

      if (!result.ok) {
        throw new Error(
          data?.error ||
            "N-ATLAS request failed."
        );
      }

      response =
        data.response || "";
    } catch (err) {
      error =
        err instanceof Error
          ? err.message
          : "Something went wrong.";
    } finally {
      loading = false;
    }
  }
</script>

<main class="app-shell">
  <section class="hero">
    <span class="eyebrow">
      N-ATLAS • Forge
    </span>

    <h1>__PROJECT_NAME__</h1>

    <textarea
      bind:value={prompt}
      rows="6"
      placeholder="Ask something..."
    />

    <button
      on:click={ask}
      disabled={
        loading ||
        !prompt.trim()
      }
    >
      {loading
        ? "Thinking..."
        : "Send to N-ATLAS"}
    </button>

    {#if error}
      <div class="error">
        {error}
      </div>
    {/if}

    {#if response}
      <div class="response">
        <strong>Response</strong>
        <p>{response}</p>
      </div>
    {/if}
  </section>
</main>
""".replace(
            "__PROJECT_NAME__",
            name,
        )

    # ============================================================
    # VANILLA
    # ============================================================

    def _vanilla_index(
        self,
        project: Project,
    ) -> str:
        title = self._escape_html(
            project.name
            or "N-ATLAS App"
        )

        return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1.0"
    />
    <title>__TITLE__</title>
  </head>
  <body>
    <div id="app"></div>
    <script
      type="module"
      src="/src/main.ts"
    ></script>
  </body>
</html>
""".replace(
            "__TITLE__",
            title,
        )

    def _vanilla_main(
        self,
        project: Project,
        workflow: dict[str, Any],
    ) -> str:
        name = self._escape_html(
            project.name
            or "N-ATLAS App"
        )

        return """const app =
  document.querySelector<HTMLDivElement>(
    "#app"
  );

if (!app) {
  throw new Error(
    "Application root not found."
  );
}

app.innerHTML = `
  <main class="app-shell">
    <section class="hero">
      <span class="eyebrow">
        N-ATLAS • Forge
      </span>

      <h1>__PROJECT_NAME__</h1>

      <textarea
        id="prompt"
        rows="6"
        placeholder="Ask something..."
      ></textarea>

      <button id="ask">
        Send to N-ATLAS
      </button>

      <div
        id="error"
        class="error"
      ></div>

      <div
        id="response"
        class="response"
      ></div>
    </section>
  </main>
`;

const prompt =
  document.querySelector<
    HTMLTextAreaElement
  >("#prompt");

const button =
  document.querySelector<
    HTMLButtonElement
  >("#ask");

const error =
  document.querySelector<
    HTMLDivElement
  >("#error");

const response =
  document.querySelector<
    HTMLDivElement
  >("#response");

button?.addEventListener(
  "click",
  async () => {
    if (!prompt?.value.trim()) {
      return;
    }

    button.disabled = true;

    if (error) {
      error.textContent = "";
    }

    if (response) {
      response.textContent = "";
    }

    try {
      const baseUrl =
        import.meta.env
          .VITE_API_BASE_URL ||
        "http://localhost:3001";

      const result =
        await fetch(
          `${baseUrl}/api/chat`,
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              prompt:
                prompt.value,
            }),
          }
        );

      const data =
        await result.json();

      if (!result.ok) {
        throw new Error(
          data?.error ||
            "N-ATLAS request failed."
        );
      }

      if (response) {
        response.textContent =
          data.response || "";
      }
    } catch (err) {
      if (error) {
        error.textContent =
          err instanceof Error
            ? err.message
            : "Something went wrong.";
      }
    } finally {
      button.disabled = false;
    }
  }
);
""".replace(
            "__PROJECT_NAME__",
            name,
        )

    # ============================================================
    # EXPRESS
    # ============================================================

    def _express_server(
        self,
        project: Project,
        workflow: dict[str, Any],
    ) -> str:
        model = self._escape_ts(
            project.model_name
            or "N-ATLAS"
        )

        return """import "dotenv/config";

import express from "express";
import cors from "cors";

const app = express();

const PORT = Number(
  process.env.PORT || 3001
);

const NATLAS_BASE_URL =
  process.env.NATLAS_BASE_URL ||
  "https://api.n-atlas.gov.ng";

const NATLAS_CHAT_ENDPOINT =
  process.env.NATLAS_CHAT_ENDPOINT ||
  "/v1/chat/completions";

const NATLAS_MODEL =
  process.env.NATLAS_MODEL ||
  "__MODEL__";

const NATLAS_API_KEY =
  process.env.NATLAS_API_KEY;

app.use(cors());
app.use(
  express.json({
    limit: "1mb",
  })
);

app.get(
  "/api/health",
  (_req, res) => {
    res.json({
      ok: true,
      service:
        "N-ATLAS application",
      model: NATLAS_MODEL,
    });
  }
);

app.post(
  "/api/chat",
  async (req, res) => {
    try {
      if (!NATLAS_API_KEY) {
        return res.status(500).json({
          error:
            "NATLAS_API_KEY is not configured.",
        });
      }

      const prompt =
        typeof req.body?.prompt ===
        "string"
          ? req.body.prompt.trim()
          : "";

      if (!prompt) {
        return res.status(400).json({
          error:
            "prompt is required.",
        });
      }

      const upstream =
        await fetch(
          `${NATLAS_BASE_URL}${NATLAS_CHAT_ENDPOINT}`,
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
              Authorization:
                `Bearer ${NATLAS_API_KEY}`,
            },
            body:
              JSON.stringify({
                model:
                  NATLAS_MODEL,
                messages: [
                  {
                    role: "user",
                    content:
                      prompt,
                  },
                ],
              }),
          }
        );

      const data =
        await upstream.json();

      if (!upstream.ok) {
        return res
          .status(upstream.status)
          .json({
            error:
              data?.error?.message ||
              data?.error ||
              "N-ATLAS request failed.",
          });
      }

      const response =
        data?.choices?.[0]
          ?.message?.content ||
        data?.response ||
        data?.output ||
        data?.content ||
        data?.text ||
        "";

      return res.json({
        response,
        raw: data,
      });
    } catch (error) {
      console.error(error);

      return res.status(500).json({
        error:
          error instanceof Error
            ? error.message
            : "Unexpected server error.",
      });
    }
  }
);

app.listen(
  PORT,
  () => {
    console.log(
      `N-ATLAS server running on http://localhost:${PORT}`
    );
  }
);
""".replace(
            "__MODEL__",
            model,
        )

    # ============================================================
    # FASTIFY
    # ============================================================

    def _fastify_server(
        self,
        project: Project,
        workflow: dict[str, Any],
    ) -> str:
        model = self._escape_ts(
            project.model_name
            or "N-ATLAS"
        )

        return """import "dotenv/config";

import Fastify from "fastify";
import cors from "@fastify/cors";

const app = Fastify({
  logger: true,
});

const PORT = Number(
  process.env.PORT || 3001
);

const NATLAS_BASE_URL =
  process.env.NATLAS_BASE_URL ||
  "https://api.n-atlas.gov.ng";

const NATLAS_CHAT_ENDPOINT =
  process.env.NATLAS_CHAT_ENDPOINT ||
  "/v1/chat/completions";

const NATLAS_MODEL =
  process.env.NATLAS_MODEL ||
  "__MODEL__";

const NATLAS_API_KEY =
  process.env.NATLAS_API_KEY;

await app.register(
  cors,
  {
    origin: true,
  }
);

app.get(
  "/api/health",
  async () => ({
    ok: true,
    service:
      "N-ATLAS application",
    model: NATLAS_MODEL,
  })
);

app.post(
  "/api/chat",
  async (
    request,
    reply
  ) => {
    try {
      if (!NATLAS_API_KEY) {
        return reply
          .code(500)
          .send({
            error:
              "NATLAS_API_KEY is not configured.",
          });
      }

      const body =
        request.body as {
          prompt?: string;
        };

      const prompt =
        typeof body?.prompt ===
        "string"
          ? body.prompt.trim()
          : "";

      if (!prompt) {
        return reply
          .code(400)
          .send({
            error:
              "prompt is required.",
          });
      }

      const upstream =
        await fetch(
          `${NATLAS_BASE_URL}${NATLAS_CHAT_ENDPOINT}`,
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
              Authorization:
                `Bearer ${NATLAS_API_KEY}`,
            },
            body:
              JSON.stringify({
                model:
                  NATLAS_MODEL,
                messages: [
                  {
                    role: "user",
                    content:
                      prompt,
                  },
                ],
              }),
          }
        );

      const data =
        await upstream.json();

      if (!upstream.ok) {
        return reply
          .code(upstream.status)
          .send({
            error:
              data?.error?.message ||
              data?.error ||
              "N-ATLAS request failed.",
          });
      }

      const response =
        data?.choices?.[0]
          ?.message?.content ||
        data?.response ||
        data?.output ||
        data?.content ||
        data?.text ||
        "";

      return {
        response,
        raw: data,
      };
    } catch (error) {
      request.log.error(
        error
      );

      return reply
        .code(500)
        .send({
          error:
            error instanceof Error
              ? error.message
              : "Unexpected server error.",
        });
    }
  }
);

await app.listen({
  port: PORT,
  host: "0.0.0.0",
});
""".replace(
            "__MODEL__",
            model,
        )

    # ============================================================
    # PACKAGES
    # ============================================================

    def _typescript_root_package(
        self,
        project: Project,
    ) -> str:
        return self._json_file({
            "name": self._project_slug(
                project.name
            ),
            "private": True,
            "version": "1.0.0",
            "scripts": {
                "install:all":
                    "npm --prefix frontend install && "
                    "npm --prefix backend install",
                "dev":
                    "concurrently "
                    "\"npm --prefix frontend run dev\" "
                    "\"npm --prefix backend run dev\"",
                "build":
                    "npm --prefix frontend run build && "
                    "npm --prefix backend run build",
            },
            "devDependencies": {
                "concurrently":
                    "^9.1.2",
            },
        })

    def _frontend_package(
        self,
        framework: str,
    ) -> str:
        if framework == "react":
            package = {
                "name":
                    "natlas-frontend",
                "private": True,
                "version":
                    "1.0.0",
                "type":
                    "module",
                "scripts": {
                    "dev": "vite",
                    "build":
                        "tsc -b && vite build",
                    "preview":
                        "vite preview",
                },
                "dependencies": {
                    "react":
                        "^19.0.0",
                    "react-dom":
                        "^19.0.0",
                },
                "devDependencies": {
                    "@types/react":
                        "^19.0.0",
                    "@types/react-dom":
                        "^19.0.0",
                    "@vitejs/plugin-react":
                        "^4.3.4",
                    "typescript":
                        "^5.7.2",
                    "vite":
                        "^6.0.5",
                },
            }

        elif framework == "vue":
            package = {
                "name":
                    "natlas-frontend",
                "private": True,
                "version":
                    "1.0.0",
                "type":
                    "module",
                "scripts": {
                    "dev": "vite",
                    "build":
                        "vue-tsc -b && vite build",
                    "preview":
                        "vite preview",
                },
                "dependencies": {
                    "vue":
                        "^3.5.13",
                },
                "devDependencies": {
                    "@vitejs/plugin-vue":
                        "^5.2.1",
                    "typescript":
                        "^5.7.2",
                    "vite":
                        "^6.0.5",
                    "vue-tsc":
                        "^2.2.0",
                },
            }

        elif framework == "svelte":
            package = {
                "name":
                    "natlas-frontend",
                "private": True,
                "version":
                    "1.0.0",
                "type":
                    "module",
                "scripts": {
                    "dev": "vite",
                    "build":
                        "vite build",
                    "preview":
                        "vite preview",
                },
                "dependencies": {
                    "svelte":
                        "^5.19.0",
                },
                "devDependencies": {
                    "@sveltejs/vite-plugin-svelte":
                        "^4.0.4",
                    "typescript":
                        "^5.7.2",
                    "vite":
                        "^6.0.5",
                },
            }

        elif framework == "angular":
            package = {
                "name":
                    "natlas-frontend",
                "private": True,
                "version":
                    "1.0.0",
                "scripts": {
                    "dev": "ng serve",
                    "build": "ng build",
                },
                "dependencies": {
                    "@angular/common":
                        "^19.0.0",
                    "@angular/core":
                        "^19.0.0",
                    "@angular/forms":
                        "^19.0.0",
                    "@angular/platform-browser":
                        "^19.0.0",
                },
                "devDependencies": {
                    "@angular/cli":
                        "^19.0.0",
                    "typescript":
                        "^5.7.2",
                },
            }

        else:
            package = {
                "name":
                    "natlas-frontend",
                "private": True,
                "version":
                    "1.0.0",
                "type":
                    "module",
                "scripts": {
                    "dev": "vite",
                    "build":
                        "tsc && vite build",
                    "preview":
                        "vite preview",
                },
                "devDependencies": {
                    "typescript":
                        "^5.7.2",
                    "vite":
                        "^6.0.5",
                },
            }

        return self._json_file(
            package
        )

    def _backend_package(
        self,
        framework: str,
    ) -> str:
        if framework == "fastify":
            package = {
                "name":
                    "natlas-backend",
                "private": True,
                "version":
                    "1.0.0",
                "type":
                    "module",
                "scripts": {
                    "dev":
                        "tsx watch src/server.ts",
                    "build":
                        "tsc",
                    "start":
                        "node dist/server.js",
                },
                "dependencies": {
                    "@fastify/cors":
                        "^10.0.2",
                    "dotenv":
                        "^16.4.7",
                    "fastify":
                        "^5.2.1",
                },
                "devDependencies": {
                    "@types/node":
                        "^22.10.5",
                    "tsx":
                        "^4.19.2",
                    "typescript":
                        "^5.7.2",
                },
            }

        else:
            package = {
                "name":
                    "natlas-backend",
                "private": True,
                "version":
                    "1.0.0",
                "type":
                    "module",
                "scripts": {
                    "dev":
                        "tsx watch src/server.ts",
                    "build":
                        "tsc",
                    "start":
                        "node dist/server.js",
                },
                "dependencies": {
                    "cors":
                        "^2.8.5",
                    "dotenv":
                        "^16.4.7",
                    "express":
                        "^4.21.2",
                },
                "devDependencies": {
                    "@types/cors":
                        "^2.8.17",
                    "@types/express":
                        "^5.0.0",
                    "@types/node":
                        "^22.10.5",
                    "tsx":
                        "^4.19.2",
                    "typescript":
                        "^5.7.2",
                },
            }

        return self._json_file(
            package
        )

    def _sdk_package(
        self,
        project: Project,
        language: str,
    ) -> str:
        return self._json_file({
            "name":
                f"{self._project_slug(project.name)}-natlas-sdk",
            "version":
                "1.0.0",
            "private":
                True,
            "type":
                "module",
            "scripts": {
                "build":
                    "tsc",
            },
            "dependencies": {},
            "devDependencies": {
                "@types/node":
                    "^22.10.5",
                "typescript":
                    "^5.7.2",
            },
        })

    def _root_tsconfig(self) -> str:
        return self._json_file({
            "compilerOptions": {
                "target":
                    "ES2022",
                "module":
                    "ESNext",
                "moduleResolution":
                    "Bundler",
                "strict":
                    True,
                "skipLibCheck":
                    True,
                "esModuleInterop":
                    True,
                "allowSyntheticDefaultImports":
                    True,
                "resolveJsonModule":
                    True,
                "noEmit":
                    True,
            },
        })

    def _backend_tsconfig(self) -> str:
        return self._json_file({
            "compilerOptions": {
                "target":
                    "ES2022",
                "module":
                    "NodeNext",
                "moduleResolution":
                    "NodeNext",
                "strict":
                    True,
                "esModuleInterop":
                    True,
                "skipLibCheck":
                    True,
                "outDir":
                    "dist",
                "rootDir":
                    "src",
            },
            "include": [
                "src/**/*.ts"
            ],
        })

    def _vite_config(
        self,
        framework: str,
    ) -> str:
        if framework == "react":
            return """import {
  defineConfig,
} from "vite";

import react from
  "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
"""

        if framework == "vue":
            return """import {
  defineConfig,
} from "vite";

import vue from
  "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
});
"""

        if framework == "svelte":
            return """import {
  defineConfig,
} from "vite";

import {
  svelte,
} from
  "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
});
"""

        return """import {
  defineConfig,
} from "vite";

export default defineConfig({});
"""

    # ============================================================
    # PYTHON SDK
    # ============================================================

    def _python_sdk(self) -> str:
        return '''from __future__ import annotations

import os
from typing import Any

import requests


class NAtlasClient:
    """OpenAI-compatible N-ATLAS client."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        chat_endpoint: str | None = None,
    ):
        self.base_url = (
            base_url
            or os.getenv(
                "NATLAS_BASE_URL",
                "https://api.n-atlas.gov.ng",
            )
        ).rstrip("/")

        self.api_key = (
            api_key
            or os.getenv("NATLAS_API_KEY")
        )

        self.model = (
            model
            or os.getenv(
                "NATLAS_MODEL",
                "N-ATLAS",
            )
        )

        self.chat_endpoint = (
            chat_endpoint
            or os.getenv(
                "NATLAS_CHAT_ENDPOINT",
                "/v1/chat/completions",
            )
        )

    def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "NATLAS_API_KEY is not configured."
            )

        messages: list[dict[str, Any]] = []

        if system:
            messages.append({
                "role": "system",
                "content": system,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        response = requests.post(
            f"{self.base_url}{self.chat_endpoint}",
            headers={
                "Authorization":
                    f"Bearer {self.api_key}",
                "Content-Type":
                    "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        return (
            data.get(
                "choices",
                [{}],
            )[0]
            .get(
                "message",
                {},
            )
            .get(
                "content"
            )
            or data.get("response")
            or data.get("output")
            or data.get("content")
            or data.get("text")
            or ""
        )
'''

    def _python_sdk_example(
        self,
        project: Project,
        workflow: dict[str, Any],
    ) -> str:
        return '''from dotenv import load_dotenv

from natlas_client import NAtlasClient


load_dotenv()

client = NAtlasClient()

answer = client.chat(
    "Explain what this application does."
)

print(answer)
'''

    def _python_pyproject(
        self,
        project: Project,
    ) -> str:
        name = self._project_slug(
            project.name
        )

        return f"""[project]
name = "{name}"
version = "1.0.0"
description = "N-ATLAS application generated by Forge"
requires-python = ">=3.10"
dependencies = [
    "requests>=2.32.0",
    "python-dotenv>=1.0.1",
]
"""

    # ============================================================
    # TYPESCRIPT SDK
    # ============================================================

    def _typescript_sdk(self) -> str:
        return """export interface NAtlasClientOptions {
  baseUrl?: string;
  apiKey?: string;
  model?: string;
  chatEndpoint?: string;
}

export interface ChatOptions {
  system?: string;
  temperature?: number;
}

export class NAtlasClient {
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly model: string;
  private readonly chatEndpoint: string;

  constructor(
    options: NAtlasClientOptions = {}
  ) {
    this.baseUrl = (
      options.baseUrl ||
      process.env.NATLAS_BASE_URL ||
      "https://api.n-atlas.gov.ng"
    ).replace(/\\/$/, "");

    this.apiKey =
      options.apiKey ||
      process.env.NATLAS_API_KEY;

    this.model =
      options.model ||
      process.env.NATLAS_MODEL ||
      "N-ATLAS";

    this.chatEndpoint =
      options.chatEndpoint ||
      process.env.NATLAS_CHAT_ENDPOINT ||
      "/v1/chat/completions";
  }

  async chat(
    prompt: string,
    options: ChatOptions = {}
  ): Promise<string> {
    if (!this.apiKey) {
      throw new Error(
        "NATLAS_API_KEY is not configured."
      );
    }

    const messages: Array<{
      role:
        | "system"
        | "user";
      content: string;
    }> = [];

    if (options.system) {
      messages.push({
        role: "system",
        content: options.system,
      });
    }

    messages.push({
      role: "user",
      content: prompt,
    });

    const response =
      await fetch(
        `${this.baseUrl}${this.chatEndpoint}`,
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
            Authorization:
              `Bearer ${this.apiKey}`,
          },
          body:
            JSON.stringify({
              model: this.model,
              messages,
              temperature:
                options.temperature ?? 0.2,
            }),
        }
      );

    const data =
      await response.json();

    if (!response.ok) {
      throw new Error(
        data?.error?.message ||
        data?.error ||
        "N-ATLAS request failed."
      );
    }

    return (
      data?.choices?.[0]
        ?.message?.content ||
      data?.response ||
      data?.output ||
      data?.content ||
      data?.text ||
      ""
    );
  }
}
"""

    def _typescript_sdk_index(self) -> str:
        return """export {
  NAtlasClient,
} from "./natlas-client";

export type {
  NAtlasClientOptions,
  ChatOptions,
} from "./natlas-client";
"""

    # ============================================================
    # CSS
    # ============================================================

    def _frontend_css(self) -> str:
        return """* {
  box-sizing: border-box;
}

:root {
  font-family:
    Inter,
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;

  color: #f4f7fb;
  background: #07111f;
  font-synthesis: none;
  text-rendering:
    optimizeLegibility;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background:
    radial-gradient(
      circle at top,
      #122746 0,
      #07111f 45%,
      #030811 100%
    );
}

button,
textarea {
  font: inherit;
}

.app-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
}

.hero {
  width: min(760px, 100%);
}

.eyebrow {
  display: inline-block;
  margin-bottom: 12px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  opacity: 0.65;
}

h1 {
  margin: 0;
  font-size:
    clamp(
      36px,
      7vw,
      72px
    );
  line-height: 0.98;
  letter-spacing: -0.05em;
}

p {
  color: #aab8cb;
  line-height: 1.7;
}

.card {
  margin-top: 32px;
  padding: 22px;
  border:
    1px solid
    rgba(
      255,
      255,
      255,
      0.09
    );
  border-radius: 20px;
  background:
    rgba(
      12,
      25,
      43,
      0.82
    );
  box-shadow:
    0 24px 80px
    rgba(
      0,
      0,
      0,
      0.28
    );
}

label {
  display: block;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 700;
}

textarea {
  width: 100%;
  resize: vertical;
  border:
    1px solid
    rgba(
      255,
      255,
      255,
      0.1
    );
  border-radius: 14px;
  padding: 15px;
  color: #f4f7fb;
  background: #07111f;
  outline: none;
}

textarea:focus {
  border-color:
    rgba(
      126,
      164,
      255,
      0.75
    );
}

button {
  margin-top: 14px;
  border: 0;
  border-radius: 12px;
  padding: 12px 18px;
  color: white;
  background: #2f6fed;
  cursor: pointer;
  font-weight: 700;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  margin-top: 16px;
  padding: 12px;
  border-radius: 10px;
  color: #ffb4b4;
  background:
    rgba(
      160,
      30,
      30,
      0.2
    );
}

.response {
  margin-top: 20px;
  padding: 16px;
  border-radius: 14px;
  background:
    rgba(
      255,
      255,
      255,
      0.04
    );
}
"""

    # ============================================================
    # ENV / README
    # ============================================================

    def _env_example(self) -> str:
        return """# N-ATLAS configuration
# Never commit your real API key.

NATLAS_BASE_URL=https://api.n-atlas.gov.ng
NATLAS_CHAT_ENDPOINT=/v1/chat/completions
NATLAS_API_KEY=
NATLAS_MODEL=N-ATLAS

# Frontend
VITE_API_BASE_URL=http://localhost:3001

# Backend
PORT=3001
"""

    def _gitignore(self) -> str:
        return """.env
.env.*
!.env.example

node_modules/
dist/
build/
coverage/

.venv/
venv/
__pycache__/
*.py[cod]

.idea/
.vscode/
.DS_Store
"""

    def _readme(
        self,
        project: Project,
        workflow: dict[str, Any],
        target: str,
        language: str,
        framework: str,
    ) -> str:
        name = (
            project.name
            or "N-ATLAS Application"
        )

        integrated = bool(
            workflow["natlas"]["integrated"]
        )

        return f"""# {name}

Generated by **N-ATLAS Forge**.

## Target

- Target: `{target}`
- Language: `{language}`
- Framework: `{framework}`

## Forge context

- Codebase files: {workflow["codebase"]["file_count"]}
- Playground experiments: {workflow["playground"]["experiment_count"]}
- Datasets: {workflow["datasets"]["dataset_count"]}
- Evaluation suites: {workflow["evaluations"]["suite_count"]}
- Evaluation runs: {workflow["evaluations"]["run_count"]}
- Existing N-ATLAS integration detected: {"yes" if integrated else "no"}

## Configuration

Copy `.env.example` to `.env`.

```env
NATLAS_BASE_URL=https://api.n-atlas.gov.ng
NATLAS_CHAT_ENDPOINT=/v1/chat/completions
NATLAS_API_KEY=your_key_here
NATLAS_MODEL=N-ATLAS
VITE_API_BASE_URL=http://localhost:3001
PORT=3001
"""

