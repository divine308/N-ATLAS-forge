from collections import defaultdict

from app.services.natlas import (
    NAtlasService,
)
from app.utils.text import evaluate_output


class EvaluationService:

    def __init__(
        self,
        natlas: NAtlasService,
    ):
        self.natlas = natlas

    async def evaluate_case(
        self,
        input_text: str,
        expected: str | None,
        category: str,
        language: str | None,
        temperature: float = 0.2,
    ) -> dict:

        response = await self.natlas.chat(
            messages=[
                {
                    "role": "user",
                    "content": input_text,
                }
            ],
            temperature=temperature,
        )

        actual = self.natlas.extract_text(
            response["data"]
        )

        metrics = evaluate_output(
            expected,
            actual,
        )

        return {
            "input": input_text,
            "expected": expected,
            "actual": actual,
            "category": category,
            "language": language,
            "passed": metrics["passed"],
            "similarity_score": metrics[
                "similarity_score"
            ],
            "quality_score": metrics[
                "quality_score"
            ],
            "failure_reasons": metrics[
                "failure_reasons"
            ],
            "latency_ms": response[
                "latency_ms"
            ],
        }

    @staticmethod
    def summarize(
        results: list[dict],
    ) -> dict:

        total = len(results)

        passed = sum(
            1
            for result in results
            if result.get("passed") is True
        )

        failed = total - passed

        score = (
            round(
                (passed / total) * 100,
                2,
            )
            if total
            else 0
        )

        categories = defaultdict(
            lambda: {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "score": 0,
            }
        )

        for result in results:

            category = (
                result.get("category")
                or "general"
            )

            categories[category]["total"] += 1

            if result.get("passed") is True:
                categories[category][
                    "passed"
                ] += 1
            else:
                categories[category][
                    "failed"
                ] += 1

        for category, data in categories.items():

            data["score"] = (
                round(
                    (
                        data["passed"]
                        / data["total"]
                    )
                    * 100,
                    2,
                )
                if data["total"]
                else 0
            )

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "score": score,
            "categories": dict(categories),
        }