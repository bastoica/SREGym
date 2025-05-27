from aiopslab.orchestrator.evaluators.quantitative import is_exact_match, is_subset
from aiopslab.orchestrator.oracles.base import Oracle


class LocalizationOracle(Oracle):
    def __init__(self, problem, expected: list[str]):
        super().__init__(problem)
        self.expected = expected

    def evaluate(self, solution) -> dict:
        print("== Localization Evaluation ==")
        results = {}

        if not isinstance(solution, list):
            results["Localization Accuracy"] = 0.0
            results["success"] = False
            results["is_subset"] = False
            print("❌ Invalid format: expected list")
            return results

        is_exact = is_exact_match(solution, self.expected)
        is_sub = is_subset(solution, self.expected)

        if is_exact:
            acc = 100.0
            print(f"✅ Exact match: {solution}")
        elif is_sub:
            acc = (len(solution) / len(self.expected)) * 100.0
            print(f"⚠️ Subset match: {solution} | Accuracy: {acc:.2f}%")
        else:
            acc = 0.0
            print(f"❌ No match: {solution}")

        results["Localization Accuracy"] = acc
        results["success"] = is_exact or (
            is_sub and len(solution) == len(self.expected)
        )
        results["is_subset"] = is_sub

        return results
