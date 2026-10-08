from dataclasses import dataclass

from app.services.evaluator import EvaluationService


@dataclass
class CrashTestCase:
    prompt: str
    category: str
    language: str


DEFAULT_CRASH_TESTS = [

    CrashTestCase(
        prompt=(
            "Explain how to reset my account."
        ),
        category="baseline",
        language="nigerian_english",
    ),

    CrashTestCase(
        prompt=(
            "How I fit reset my account?"
        ),
        category="nigerian_slang",
        language="nigerian_english",
    ),

    CrashTestCase(
        prompt=(
            "Abeg explain how I fit reset "
            "my account sharp sharp."
        ),
        category="nigerian_slang",
        language="nigerian_english",
    ),

    CrashTestCase(
        prompt=(
            "how do i resset my acount"
        ),
        category="typo_robustness",
        language="nigerian_english",
    ),

    CrashTestCase(
        prompt=(
            "Ṣàlàyé bí mo ṣe lè tún "
            "àkáǹtì mi ṣe."
        ),
        category="local_language",
        language="yoruba",
    ),

    CrashTestCase(
        prompt=(
            "Kọwaa otu m ga esi "
            "tọgharịa akaụntụ m."
        ),
        category="local_language",
        language="igbo",
    ),

    CrashTestCase(
        prompt=(
            "Bayyana yadda zan sake "
            "saita asusuna."
        ),
        category="local_language",
        language="hausa",
    ),

    CrashTestCase(
        prompt=(
            "Please explain how to reset "
            "my account in Yoruba, but "
            "keep technical terms in English."
        ),
        category="code_switching",
        language="yoruba",
    ),

    CrashTestCase(
        prompt="How do I register?",
        category="ambiguity",
        language="nigerian_english",
    ),

    CrashTestCase(
        prompt=(
            "I paid my school fees but my "
            "portal still says I have "
            "outstanding fees. What should "
            "I do?"
        ),
        category="nigerian_context",
        language="nigerian_english",
    ),

    CrashTestCase(
        prompt=(
            "Give me a short answer in "
            "Nigerian English."
        ),
        category="instruction_following",
        language="nigerian_english",
    ),

    CrashTestCase(
        prompt=(
            "Respond in Yoruba. Then explain "
            "the same answer in Nigerian English."
        ),
        category="multi_instruction",
        language="yoruba",
    ),
]


class CrashTestService:

    def __init__(
        self,
        evaluator: EvaluationService,
    ):
        self.evaluator = evaluator

    async def run(
        self,
        temperature: float = 0.2,
    ) -> dict:

        results = []

        for case in DEFAULT_CRASH_TESTS:

            result = await (
                self.evaluator.evaluate_case(
                    input_text=case.prompt,
                    expected=None,
                    category=case.category,
                    language=case.language,
                    temperature=temperature,
                )
            )

            results.append(result)

        summary = (
            self.evaluator.summarize(
                results
            )
        )

        return {
            "name": "N-ATLAS Crash Test",
            "methodology": (
                "Structural robustness evaluation. "
                "Reference-free cases are not treated "
                "as semantic ground truth."
            ),
            "total_tests": summary["total"],
            "passed_tests": summary["passed"],
            "failed_tests": summary["failed"],
            "score": summary["score"],
            "categories": summary[
                "categories"
            ],
            "results": results,
        }