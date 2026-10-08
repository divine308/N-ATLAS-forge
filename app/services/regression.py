from __future__ import annotations


CATEGORY_REGRESSION_THRESHOLD = 5.0
CASE_SCORE_CHANGE_THRESHOLD = 0.05


def _score(result: dict | None) -> float:
    if not result:
        return 0.0

    value = result.get("quality_score")

    if value is None:
        value = result.get("similarity_score", 0)

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_reasons(value) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        return [value]

    return [str(value)]


def _compare_categories(
    baseline: dict,
    candidate: dict,
) -> tuple[list, list, list]:
    baseline_categories = (
        baseline.get("category_summary", {})
        or {}
    )

    candidate_categories = (
        candidate.get("category_summary", {})
        or {}
    )

    if not isinstance(baseline_categories, dict):
        baseline_categories = {}

    if not isinstance(candidate_categories, dict):
        candidate_categories = {}

    # _forge contains run metadata, not an evaluation category.
    baseline_categories.pop("_forge", None)
    candidate_categories.pop("_forge", None)

    all_categories = sorted(
        set(baseline_categories)
        | set(candidate_categories)
    )

    regressions = []
    improvements = []
    unchanged = []

    for category in all_categories:
        baseline_data = (
            baseline_categories.get(category)
            or {}
        )

        candidate_data = (
            candidate_categories.get(category)
            or {}
        )

        baseline_score = float(
            baseline_data.get("score", 0) or 0
        )

        candidate_score = float(
            candidate_data.get("score", 0) or 0
        )

        change = round(
            candidate_score - baseline_score,
            2,
        )

        item = {
            "category": category,
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "change": change,
        }

        if change <= -CATEGORY_REGRESSION_THRESHOLD:
            regressions.append(item)

        elif change >= CATEGORY_REGRESSION_THRESHOLD:
            improvements.append(item)

        else:
            unchanged.append(item)

    return (
        regressions,
        improvements,
        unchanged,
    )


def _compare_cases(
    baseline: dict,
    candidate: dict,
) -> tuple[list, list, list]:
    baseline_results = {
        item.get("case_id"): item
        for item in (
            baseline.get("results", [])
            or []
        )
        if item.get("case_id") is not None
    }

    candidate_results = {
        item.get("case_id"): item
        for item in (
            candidate.get("results", [])
            or []
        )
        if item.get("case_id") is not None
    }

    regressions = []
    improvements = []
    unchanged = []

    shared_case_ids = sorted(
        set(baseline_results)
        & set(candidate_results)
    )

    for case_id in shared_case_ids:
        baseline_result = baseline_results[case_id]
        candidate_result = candidate_results[case_id]

        baseline_score = _score(
            baseline_result
        )

        candidate_score = _score(
            candidate_result
        )

        score_change = round(
            candidate_score - baseline_score,
            4,
        )

        baseline_passed = bool(
            baseline_result.get("passed", False)
        )

        candidate_passed = bool(
            candidate_result.get("passed", False)
        )

        category = (
            candidate_result.get("category")
            or baseline_result.get("category")
            or "general"
        )

        item = {
            "case_id": case_id,
            "case_name": (
                candidate_result.get("case_name")
                or baseline_result.get("case_name")
                or f"Case {case_id}"
            ),
            "category": category,
            "baseline_passed": baseline_passed,
            "candidate_passed": candidate_passed,
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "score_change": score_change,
            "expected": (
                candidate_result.get("expected")
                if candidate_result.get("expected") is not None
                else baseline_result.get("expected")
            ),
            "baseline_actual": baseline_result.get(
                "actual",
                "",
            ),
            "candidate_actual": candidate_result.get(
                "actual",
                "",
            ),
            "baseline_failure_reasons": _normalize_reasons(
                baseline_result.get(
                    "failure_reasons"
                )
            ),
            "candidate_failure_reasons": _normalize_reasons(
                candidate_result.get(
                    "failure_reasons"
                )
            ),
            "baseline_latency_ms": baseline_result.get(
                "latency_ms"
            ),
            "candidate_latency_ms": candidate_result.get(
                "latency_ms"
            ),
        }

        # A previously passing case that now fails is
        # always a regression.
        if baseline_passed and not candidate_passed:
            regressions.append(item)
            continue

        # A previously failing case that now passes is
        # always an improvement.
        if not baseline_passed and candidate_passed:
            improvements.append(item)
            continue

        # If both passed or both failed, meaningful score
        # movement still matters.
        if score_change <= -CASE_SCORE_CHANGE_THRESHOLD:
            regressions.append(item)

        elif score_change >= CASE_SCORE_CHANGE_THRESHOLD:
            improvements.append(item)

        else:
            unchanged.append(item)

    return (
        regressions,
        improvements,
        unchanged,
    )


def compare_runs(
    baseline: dict,
    candidate: dict,
) -> dict:
    baseline_score = float(
        baseline.get("score", 0) or 0
    )

    candidate_score = float(
        candidate.get("score", 0) or 0
    )

    overall_change = round(
        candidate_score - baseline_score,
        2,
    )

    (
        category_regressions,
        category_improvements,
        category_unchanged,
    ) = _compare_categories(
        baseline,
        candidate,
    )

    (
        case_regressions,
        case_improvements,
        case_unchanged,
    ) = _compare_cases(
        baseline,
        candidate,
    )

    baseline_results = {
        item.get("case_id")
        for item in (
            baseline.get("results", [])
            or []
        )
        if item.get("case_id") is not None
    }

    candidate_results = {
        item.get("case_id")
        for item in (
            candidate.get("results", [])
            or []
        )
        if item.get("case_id") is not None
    }

    shared_case_count = len(
        baseline_results
        & candidate_results
    )

    baseline_only_cases = sorted(
        baseline_results - candidate_results
    )

    candidate_only_cases = sorted(
        candidate_results - baseline_results
    )

    baseline_metadata = (
        baseline.get("category_summary", {})
        or {}
    )

    candidate_metadata = (
        candidate.get("category_summary", {})
        or {}
    )

    baseline_forge = (
        baseline_metadata.get("_forge", {})
        if isinstance(
            baseline_metadata,
            dict,
        )
        else {}
    )

    candidate_forge = (
        candidate_metadata.get("_forge", {})
        if isinstance(
            candidate_metadata,
            dict,
        )
        else {}
    )

    same_suite = (
        baseline_forge.get("suite_id")
        is not None
        and candidate_forge.get("suite_id")
        is not None
        and baseline_forge.get("suite_id")
        == candidate_forge.get("suite_id")
    )

    same_dataset = (
        baseline.get("dataset_id")
        == candidate.get("dataset_id")
    )

    same_dataset_version = (
        baseline.get("dataset_version")
        == candidate.get("dataset_version")
    )

    comparable = (
        same_suite
        and same_dataset
        and same_dataset_version
        and shared_case_count > 0
    )

    return {
        "baseline_score": baseline_score,
        "candidate_score": candidate_score,
        "score_change": overall_change,
        "improved": overall_change > 0,

        "comparable": comparable,

        "comparison": {
            "same_suite": same_suite,
            "same_dataset": same_dataset,
            "same_dataset_version": same_dataset_version,
            "shared_case_count": shared_case_count,
            "baseline_case_count": len(
                baseline_results
            ),
            "candidate_case_count": len(
                candidate_results
            ),
            "baseline_only_cases": baseline_only_cases,
            "candidate_only_cases": candidate_only_cases,
        },

        "category_comparison": {
            "regressions": category_regressions,
            "improvements": category_improvements,
            "unchanged": category_unchanged,
        },

        "case_comparison": {
            "regressions": case_regressions,
            "improvements": case_improvements,
            "unchanged": case_unchanged,
        },

        # Keep these top-level aliases so the response
        # remains convenient for consumers.
        "regressions": case_regressions,
        "improvements": case_improvements,
        "unchanged": case_unchanged,
    }