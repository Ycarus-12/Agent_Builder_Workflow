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
    cost_rom_schema,
    intake_record_schema,
    load_intake_conversation_spec,
    load_intake_extraction_spec,
    stack_check_finding_schema,
    triage_output_schema,
)
from .config import load_gateway_config
from .evals.runner import (
    SuiteResult,
    run_cost_rom_suite_replay,
    run_intake_suite_live,
    run_intake_suite_replay,
    run_stack_check_suite_replay,
    run_triage_suite_replay,
)
from .ports.gateway import OpenRouterGateway

_REPLAY_SUITES = {
    "intake": lambda: run_intake_suite_replay(intake_record_schema()),
    "stack-check": lambda: run_stack_check_suite_replay(stack_check_finding_schema()),
    "triage": lambda: run_triage_suite_replay(triage_output_schema()),
    "rom": lambda: run_cost_rom_suite_replay(cost_rom_schema()),
}


def _report(label: str, suite: SuiteResult, mode: str) -> int:
    print(f"{label} ({mode} mode): {len(suite.cases)} case(s)")
    for case in suite.cases:
        status = "PASS" if case.passed else "FAIL"
        print(f"  [{status}] {case.case_id}")
        for fmsg in case.failures:
            print(f"      - {fmsg}")
        for soft in case.soft_signals:
            print(f"      ~ soft: {soft}")
    if suite.ok:
        print(f"{label}: PASS ({len(suite.cases)} case(s))")
        return 0
    print(f"{label}: FAIL ({len(suite.failed)}/{len(suite.cases)} case(s) failed)")
    return 1


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Run agent eval suites.")
    parser.add_argument("--mode", choices=["replay", "live"], default="replay")
    parser.add_argument(
        "--suite", choices=["intake", "stack-check", "triage", "rom", "all"], default="all"
    )
    args = parser.parse_args(argv)

    if args.mode == "replay":
        suites = list(_REPLAY_SUITES) if args.suite == "all" else [args.suite]
        rc = 0
        for name in suites:
            rc |= _report(f"{name}-evals", _REPLAY_SUITES[name](), "replay")
        return rc

    # Live mode: intake is wired; stack-check/triage live runners are a follow-up.
    if args.suite not in ("intake", "all"):
        print(f"{args.suite}-evals (live mode): not yet wired — replay is the active gate.")
        return 0
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
        intake_record_schema(), gateway, load_intake_conversation_spec(), load_intake_extraction_spec()
    )
    return _report("intake-evals", suite, "live")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
