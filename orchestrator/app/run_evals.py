"""Eval-harness CLI — the CI merge gate (contract §7.3).

  python -m app.run_evals                 # replay mode (every commit; gates merges)
  python -m app.run_evals --mode live     # live model eval; needs OPENROUTER_API_KEY

Exit code 0 = all cases pass; 1 = any case failed (merge blocked).
Live mode with no key prints a skip notice and exits 0 (so a key-less CI job is a
no-op rather than a failure).
"""

from __future__ import annotations

import argparse
import sys

from .agents import (
    intake_record_schema,
    load_intake_conversation_spec,
    load_intake_extraction_spec,
)
from .config import load_gateway_config
from .evals.runner import (
    SuiteResult,
    run_intake_suite_live,
    run_intake_suite_replay,
)
from .ports.gateway import OpenRouterGateway


def _report(suite: SuiteResult, mode: str) -> int:
    print(f"intake-evals ({mode} mode): {len(suite.cases)} case(s)")
    for case in suite.cases:
        status = "PASS" if case.passed else "FAIL"
        print(f"  [{status}] {case.case_id}")
        for fmsg in case.failures:
            print(f"      - {fmsg}")
        for soft in case.soft_signals:
            print(f"      ~ soft: {soft}")
    if suite.ok:
        print(f"intake-evals: PASS ({len(suite.cases)} case(s))")
        return 0
    print(f"intake-evals: FAIL ({len(suite.failed)}/{len(suite.cases)} case(s) failed)")
    return 1


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Run the intake eval suite.")
    parser.add_argument("--mode", choices=["replay", "live"], default="replay")
    args = parser.parse_args(argv)

    schema = intake_record_schema()

    if args.mode == "replay":
        return _report(run_intake_suite_replay(schema), "replay")

    config = load_gateway_config()
    if not config.has_key:
        print("intake-evals (live mode): skipped — OPENROUTER_API_KEY not set.")
        return 0
    models = {
        "intake-conversation": (config.conversation_model, config.conversation_max_tokens),
        "intake-extraction": (config.extraction_model, config.extraction_max_tokens),
    }
    gateway = OpenRouterGateway(config, models)
    suite = run_intake_suite_live(
        schema, gateway, load_intake_conversation_spec(), load_intake_extraction_spec()
    )
    return _report(suite, "live")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
