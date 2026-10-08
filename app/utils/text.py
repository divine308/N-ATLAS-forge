import re
from difflib import SequenceMatcher


FAILURE_PHRASES = [
    "internal server error",
    "something went wrong",
    "i cannot process",
    "unable to process",
    "error occurred",
]


def normalize_text(
    text: str,
) -> str:

    text = text.lower().strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


def similarity_score(
    expected: str,
    actual: str,
) -> float:

    if not expected:
        return 0.0

    expected_normalized = normalize_text(
        expected
    )

    actual_normalized = normalize_text(
        actual
    )

    return round(
        SequenceMatcher(
            None,
            expected_normalized,
            actual_normalized,
        ).ratio(),
        4,
    )


def token_overlap_score(
    expected: str,
    actual: str,
) -> float:

    expected_tokens = set(
        normalize_text(expected).split()
    )

    actual_tokens = set(
        normalize_text(actual).split()
    )

    if not expected_tokens:
        return 0.0

    overlap = (
        expected_tokens
        & actual_tokens
    )

    return round(
        len(overlap)
        / len(expected_tokens),
        4,
    )


def quality_score(
    actual: str,
) -> tuple[float, list[str]]:

    reasons: list[str] = []

    text = actual.strip()

    if not text:
        return 0.0, ["empty_response"]

    score = 1.0

    if len(text) < 10:
        score -= 0.25
        reasons.append(
            "very_short_response"
        )

    normalized = normalize_text(text)

    for phrase in FAILURE_PHRASES:

        if phrase in normalized:

            score -= 0.50

            reasons.append(
                "provider_or_generation_error"
            )

            break

    if len(text) > 15000:
        score -= 0.10

        reasons.append(
            "unusually_long_response"
        )

    score = max(
        0.0,
        min(1.0, score),
    )

    return round(score, 4), reasons


def evaluate_output(
    expected: str | None,
    actual: str,
) -> dict:

    structural_score, reasons = (
        quality_score(actual)
    )

    if expected:

        semantic_similarity = (
            similarity_score(
                expected,
                actual,
            )
        )

        overlap = token_overlap_score(
            expected,
            actual,
        )

        combined = (
            (
                semantic_similarity * 0.6
            )
            + (
                overlap * 0.4
            )
        )

        final_score = round(
            (
                combined * 0.7
            )
            + (
                structural_score * 0.3
            ),
            4,
        )

        passed = final_score >= 0.70

    else:

        semantic_similarity = 0.0
        final_score = structural_score

        # Without a reference answer, this is
        # a structural/robustness test rather
        # than a semantic correctness test.
        passed = structural_score >= 0.70

    if not passed:
        reasons.append(
            "below_evaluation_threshold"
        )

    return {
        "passed": passed,
        "similarity_score": round(
            semantic_similarity,
            4,
        ),
        "quality_score": round(
            final_score,
            4,
        ),
        "failure_reasons": list(
            dict.fromkeys(reasons)
        ),
    }