from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


class EvaluationCaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    input: str = Field(..., min_length=1, max_length=20000)
    expected: str | None = Field(default=None, max_length=20000)
    category: str = Field(default="general", max_length=50)
    language: str = Field(default="nigerian_english", max_length=50)
    position: int = Field(default=0, ge=0)
    enabled: bool = True
    dataset_record_index: int | None = Field(default=None, ge=0)


class EvaluationCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    suite_id: int
    name: str
    input: str
    expected: str | None
    category: str
    language: str
    position: int
    enabled: bool
    dataset_record_index: int | None
    created_at: datetime
    updated_at: datetime


class EvaluationTargetFileInput(BaseModel):
    project_file_id: int


class EvaluationSuiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    category: str = Field(default="general", max_length=50)

    dataset_id: int | None = None
    dataset_version: int | None = Field(default=None, ge=1)

    target_file_ids: list[int] = Field(default_factory=list)

    configuration: dict = Field(default_factory=dict)


class EvaluationSuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=50)

    dataset_id: int | None = None
    dataset_version: int | None = Field(default=None, ge=1)

    target_file_ids: list[int] | None = None

    configuration: dict | None = None
    active: bool | None = None


class EvaluationTargetFileResponse(BaseModel):
    id: int
    project_file_id: int
    path: str
    language: str | None
    size: int
    is_binary: bool


class EvaluationLastRunResponse(BaseModel):
    id: int
    status: str
    score: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    created_at: datetime


class EvaluationSuiteResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: str | None
    category: str

    dataset_id: int | None
    dataset_version: int | None

    configuration: dict

    active: bool

    case_count: int
    target_files: list[EvaluationTargetFileResponse]

    last_run: EvaluationLastRunResponse | None

    created_at: datetime
    updated_at: datetime


class EvaluationRunRequest(BaseModel):
    model_name: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)


class EvaluationRunResponse(BaseModel):
    id: int
    project_id: int
    suite_name: str
    dataset_id: int | None
    dataset_version: int | None

    status: str

    total_tests: int
    passed_tests: int
    failed_tests: int

    score: float

    category_summary: dict | None
    results: list | None

    created_at: datetime


class EvaluationRunListItem(BaseModel):
    id: int
    suite_name: str
    status: str

    total_tests: int
    passed_tests: int
    failed_tests: int
    score: float

    dataset_id: int | None
    dataset_version: int | None

    created_at: datetime


class RegressionCase(BaseModel):
    case_id: int
    case_name: str
    category: str

    baseline_passed: bool
    candidate_passed: bool

    baseline_score: float
    candidate_score: float
    score_change: float

    expected: str | None

    baseline_actual: str
    candidate_actual: str

    baseline_failure_reasons: list
    candidate_failure_reasons: list

    baseline_latency_ms: float | int | None
    candidate_latency_ms: float | int | None


class RegressionCategory(BaseModel):
    category: str
    baseline_score: float
    candidate_score: float
    change: float


class RegressionComparison(BaseModel):
    same_suite: bool
    same_dataset: bool
    same_dataset_version: bool

    shared_case_count: int
    baseline_case_count: int
    candidate_case_count: int

    baseline_only_cases: list[int]
    candidate_only_cases: list[int]


class RegressionCategoryComparison(BaseModel):
    regressions: list[RegressionCategory]
    improvements: list[RegressionCategory]
    unchanged: list[RegressionCategory]


class RegressionCaseComparison(BaseModel):
    regressions: list[RegressionCase]
    improvements: list[RegressionCase]
    unchanged: list[RegressionCase]


class RegressionRequest(BaseModel):
    baseline_run_id: int
    candidate_run_id: int


class RegressionResponse(BaseModel):
    baseline_run_id: int
    candidate_run_id: int

    baseline_score: float
    candidate_score: float
    score_change: float

    improved: bool
    comparable: bool

    comparison: RegressionComparison

    category_comparison: RegressionCategoryComparison

    case_comparison: RegressionCaseComparison

    regressions: list[RegressionCase]
    improvements: list[RegressionCase]
    unchanged: list[RegressionCase]