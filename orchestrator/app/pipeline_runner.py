"""PipelineRunner — the connective driver that runs a request past intake.

`IntakeRunner` carries a request to `record_ready`; this composes the rest of the
spine into one runnable flow: analysis (stack-check -> triage -> ROM) -> Gate 1a
-> deep-dive -> Gate 1b -> build (+needs-input loop) -> QA -> security
(reconciled) -> Gate 2 -> deploy_and_register.

Deterministic, per the non-negotiables: the orchestrator sequences, routes, gates,
and logs; judgment lives only in the agents it invokes. The runner halts at the
three Director gates and the two embedded stops (build needs-input, R&D sign-off),
returning a PipelineStep that says where and why it paused and carries the payload
the Director needs to decide. Resume entry points feed the decision back in.

Gateway-agnostic and seam-agnostic: the same code runs on the fakes or the real
OpenRouter gateway + Resend/Airtable adapters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .agents import (
    load_build_spec,
    load_cost_deepdive_spec,
    load_cost_rom_spec,
    load_functional_qa_spec,
    load_security_gov_spec,
    load_security_vuln_spec,
    load_stack_check_spec,
    load_triage_spec,
    stack_check_finding_schema,
)
from .enums import BuildType, Outcome, Weight
from .invocation import AgentSpec, InputEnvelope
from .logging_audit import AuditLog
from .ports.chat import ChatGateway
from .ports.datastore import Datastore
from .ports.emailer import Emailer
from .ports.gateway import ModelGateway
from .registry.source import RegistrySource
from .retry_loop import DEFAULT_MAX_ATTEMPTS, run_structured
from .security_review import SecurityOutcome, reconcile_security
from .state_machine import (
    AnalysisStep,
    DIRECTOR_GATES,
    Gate1aDecision,
    Pipeline,
    Stage,
)

# An empty-but-present scanner block: every scanner type ran and found nothing.
# The real producer (ADR 0001: Semgrep + Trivy + Gitleaks -> normalizer) lands in
# the build-artifact CI; the runner injects whatever the producer hands it.
_EMPTY_SCANNER_FINDINGS = {"sast": [], "sca": [], "secrets": []}

# Operator-supplied at deployment time; a placeholder keeps the offline flow runnable.
_DEFAULT_GOVERNANCE_STANDARD = "(governance standard supplied by the operator at deploy time)"

# Safety bound on the build<->QA / build<->security remediation loops so a
# persistently failing build cannot spin forever. Not a contract gate — a backstop.
_MAX_REMEDIATION_CYCLES = 5


class PipelineError(RuntimeError):
    """Unrecoverable driver condition (e.g. remediation cap hit, missing option)."""


@dataclass
class PipelineStep:
    """Where the run paused and what the decider needs. The terminal result too."""

    kind: str  # awaiting_gate | awaiting_build_input | awaiting_security_adjudication
    #            | awaiting_rnd_signoff | terminal
    stage: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunState:
    """Accumulated agent outputs threaded between stages (+ persisted for resume)."""

    intake_record: dict
    transcript: str
    stack_check_finding: dict | None = None
    triage_output: dict | None = None
    rom_output: dict | None = None
    deepdive_output: dict | None = None
    approved_option: dict | None = None
    build_manifest: dict | None = None
    qa_verdict: dict | None = None
    security_vuln: dict | None = None
    security_gov: dict | None = None
    director_responses: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class PipelineRunner:
    """Drives one request from `record_ready` to a terminal stage, pausing at stops."""

    def __init__(
        self,
        *,
        pipeline: Pipeline,
        state: RunState,
        request_id: str,
        gateway: ModelGateway,
        datastore: Datastore,
        emailer: Emailer,
        audit: AuditLog,
        registry_source: RegistrySource,
        chat_gateway: ChatGateway | None = None,
        director_email: str = "director@example.com",
        governance_standard: str = _DEFAULT_GOVERNANCE_STANDARD,
        scanner_findings: dict | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self.pipeline = pipeline
        self.state = state
        self.request_id = request_id
        self.gateway = gateway
        # stack-check needs a tool-use chat round-trip; the prod gateway is both.
        self.chat_gateway = chat_gateway or _as_chat(gateway)
        self.datastore = datastore
        self.emailer = emailer
        self.audit = audit
        self.registry_source = registry_source
        self.director_email = director_email
        self.governance_standard = governance_standard
        self.scanner_findings = scanner_findings or dict(_EMPTY_SCANNER_FINDINGS)
        self.max_attempts = max_attempts

        # Decision state captured at a stop and consumed on resume.
        self._security_outcome: SecurityOutcome | None = None
        self._security_director_cleared = False
        self._rnd_signed_off = False
        self._remediation_cycles = 0

        # Specs (loaded once; the gateway keys on spec.name).
        self._stack_check = load_stack_check_spec()
        self._triage = load_triage_spec()
        self._rom = load_cost_rom_spec()
        self._deepdive = load_cost_deepdive_spec()
        self._build = load_build_spec()
        self._qa = load_functional_qa_spec()
        self._sec_vuln = load_security_vuln_spec()
        self._sec_gov = load_security_gov_spec()

    # == the drive loop ======================================================
    def advance(self) -> PipelineStep:
        """Run automatic stages until the next stop or a terminal stage."""
        while True:
            p = self.pipeline
            if p.is_terminal:
                return self._terminal_step()
            if p.stage in DIRECTOR_GATES:
                return self._gate_step()

            if p.stage is Stage.ANALYSIS:
                self._run_analysis_step()
            elif p.stage is Stage.COST_DEEPDIVE:
                self._run_deepdive()
            elif p.stage is Stage.BUILD:
                paused = self._run_build()
                if paused is not None:
                    return paused
            elif p.stage is Stage.QA_FUNCTIONAL:
                self._run_qa()
            elif p.stage is Stage.SECURITY_REVIEW:
                paused = self._run_security()
                if paused is not None:
                    return paused
            else:  # pragma: no cover - exhaustive over automatic stages
                raise PipelineError(f"no driver for stage {p.stage.value}")

    # == resume entry points (one per stop) ==================================
    def resume_gate_1a(
        self,
        decision: Gate1aDecision,
        *,
        selected_options: tuple[str, ...] = (),
        decided_by: str = "Director",
        rationale: str = "",
    ) -> PipelineStep:
        self.audit.gate_decision(
            request_id=self.request_id, stage=Stage.GATE_1A.value,
            decision=decision.value, decided_by=decided_by, rationale=rationale,
        )
        self.pipeline.apply_gate_1a(decision, selected_options=selected_options)
        if decision is Gate1aDecision.DEEP_DIVE and selected_options:
            # Carry the selected subset onto the run for deep-dive context.
            self.state.approved_option = self._option_by_id(selected_options[0])
        self._persist()
        return self.advance()

    def resume_gate_1b(self, *, approved: bool, decided_by: str = "Director", rationale: str = "") -> PipelineStep:
        self.audit.gate_decision(
            request_id=self.request_id, stage=Stage.GATE_1B.value,
            decision="approved" if approved else "declined", decided_by=decided_by, rationale=rationale,
        )
        self.pipeline.apply_gate_1b(approved=approved)
        self._persist()
        return self.advance()

    def resume_gate_2(self, *, accepted: bool, decided_by: str = "Director", rationale: str = "") -> PipelineStep:
        self.audit.gate_decision(
            request_id=self.request_id, stage=Stage.GATE_2.value,
            decision="accepted" if accepted else "rejected", decided_by=decided_by, rationale=rationale,
        )
        self.pipeline.apply_gate_2(accepted=accepted)
        self._persist()
        return self.advance()

    def provide_build_answers(self, responses: dict[str, str]) -> PipelineStep:
        """Director answered build-agent's needs_input questions; re-invoke build."""
        self.state.director_responses = responses
        self.pipeline.build_provide_responses()
        self._persist()
        return self.advance()

    def resume_security_adjudication(self, *, cleared: bool, decided_by: str = "Director", rationale: str = "") -> PipelineStep:
        """Director adjudicates a High finding / material disagreement."""
        self.audit.gate_decision(
            request_id=self.request_id, stage=Stage.SECURITY_REVIEW.value,
            decision="cleared" if cleared else "blocked", decided_by=decided_by, rationale=rationale,
        )
        self._security_director_cleared = cleared
        if not cleared:
            # Director sends it back for remediation (security stays non-bypassable
            # upward, but the Director may still reject downward).
            self.pipeline._go(Stage.BUILD)  # noqa: SLF001 - deterministic routing
            self._persist()
            return self.advance()
        return self._apply_security_outcome()

    def record_rnd_signoff(self) -> PipelineStep:
        """The R&D security sign-off arrived (heavy/sensitive embedded stop)."""
        self._rnd_signed_off = True
        return self._apply_security_outcome()

    # == stage runners =======================================================
    def _run_analysis_step(self) -> None:
        step = self.pipeline.analysis_step
        if step is AnalysisStep.STACK_CHECK:
            finding = self._run_stack_check()
            self.state.stack_check_finding = finding
        elif step is AnalysisStep.TRIAGE:
            triage = self._structured(self._triage, self._triage_blocks(), Stage.ANALYSIS.value)
            self.state.triage_output = triage
            outcome = Outcome(triage["recommendation"]["outcome"])
            self.pipeline.set_triage_recommendation(outcome)
            self.state.approved_option = self._recommended_option(triage)
        elif step is AnalysisStep.COST_ROM:
            self.state.rom_output = self._structured(self._rom, self._rom_blocks(), Stage.ANALYSIS.value)
        self.pipeline.advance_analysis()
        self._persist()

    def _run_stack_check(self) -> dict:
        from .agent_runtime import run_stack_check

        finding = run_stack_check(
            self.chat_gateway, self._stack_check,
            intake_record_json=json.dumps(self.state.intake_record),
            source=self.registry_source, schema=stack_check_finding_schema(),
        )
        self.audit.agent_call(
            request_id=self.request_id, stage=Stage.ANALYSIS.value, agent_name=self._stack_check.name,
            prompt_version=self._stack_check.version, commit_hash=self._stack_check.commit_hash,
            input_rendered=json.dumps(self.state.intake_record), output=finding,
            sensitivity=self.pipeline.data_sensitivity, validation_result="valid", retry_count=0,
        )
        return finding

    def _run_deepdive(self) -> None:
        self.state.deepdive_output = self._structured(
            self._deepdive, self._deepdive_blocks(), Stage.COST_DEEPDIVE.value
        )
        self.pipeline.deepdive_complete()
        self._persist()

    def _run_build(self) -> PipelineStep | None:
        self._resolve_approved_option()
        self.pipeline.weight = _option_weight(self.state.approved_option)
        manifest = self._structured(self._build, self._build_blocks(), Stage.BUILD.value)
        self.state.build_manifest = manifest
        self.state.director_responses = None  # consumed
        if manifest["build_status"] == "needs_input":
            question_ids = _question_ids(manifest.get("questions", []))
            self.pipeline.build_needs_input(question_ids)
            self._email(kind="build_needs_input", subject="Build needs input",
                        body=json.dumps(manifest.get("questions", [])))
            self._persist()
            return PipelineStep(
                kind="awaiting_build_input", stage=Stage.BUILD.value,
                payload={"questions": manifest.get("questions", [])},
            )
        self.pipeline.build_complete()
        self._persist()
        return None

    def _run_qa(self) -> None:
        verdict = self._structured(self._qa, self._qa_blocks(), Stage.QA_FUNCTIONAL.value)
        self.state.qa_verdict = verdict
        passed = verdict["qa_status"] in ("pass", "pass_pending_apply")
        if not passed:
            self._enter_remediation("QA failed")
        self.pipeline.apply_qa(passed=passed)
        self._persist()

    def _run_security(self) -> PipelineStep | None:
        # Both agents run BLIND (neither sees the other); the orchestrator reconciles.
        self.state.security_vuln = self._structured(
            self._sec_vuln, self._security_blocks(gov=False), Stage.SECURITY_REVIEW.value
        )
        self.state.security_gov = self._structured(
            self._sec_gov, self._security_blocks(gov=True), Stage.SECURITY_REVIEW.value
        )
        self._security_outcome = reconcile_security(
            self.state.security_vuln.get("findings", []),
            self.state.security_gov.get("findings", []),
            weight=self.pipeline.weight, data_sensitivity=self.pipeline.data_sensitivity,
        )
        return self._apply_security_outcome()

    def _apply_security_outcome(self) -> PipelineStep | None:
        outcome = self._security_outcome
        assert outcome is not None
        if outcome.blocked:
            self._enter_remediation("Critical security finding")
            self.pipeline.apply_reconciled_security(outcome)  # -> BUILD
            self._persist()
            return self.advance()
        if outcome.to_director and not self._security_director_cleared:
            self._email(kind="security_adjudication", subject="Security adjudication",
                        body=self._security_summary())
            self._persist()
            return PipelineStep(
                kind="awaiting_security_adjudication", stage=Stage.SECURITY_REVIEW.value,
                payload={"summary": self._security_summary(), "disagreement": outcome.disagreement},
            )
        if outcome.rnd_signoff_required and not self._rnd_signed_off:
            self._persist()
            return PipelineStep(
                kind="awaiting_rnd_signoff", stage=Stage.SECURITY_REVIEW.value,
                payload={"summary": self._security_summary()},
            )
        self.pipeline.apply_reconciled_security(
            outcome, rnd_signed_off=self._rnd_signed_off, director_cleared=self._security_director_cleared,
        )
        self._persist()
        return self.advance()

    # == context assembly (the one piece of genuinely new threading) =========
    def _triage_blocks(self) -> dict[str, str]:
        return {
            "intake_record": json.dumps(self.state.intake_record),
            "transcript": self.state.transcript,
            "stack_check_result": json.dumps(self.state.stack_check_finding),
        }

    def _rom_blocks(self) -> dict[str, str]:
        return {
            "INTAKE RECORD": json.dumps(self.state.intake_record),
            "OPTION LIST": json.dumps(self.state.triage_output["options"]),
        }

    def _deepdive_blocks(self) -> dict[str, str]:
        return {
            "intake_extract": json.dumps(self.state.intake_record),
            "transcript": self.state.transcript,
            "stack_check_finding": json.dumps(self.state.stack_check_finding),
            "rom_output": json.dumps(self.state.rom_output),
            "selected_options": json.dumps(list(self.pipeline.selected_options)),
        }

    def _build_blocks(self) -> dict[str, str]:
        option = self.state.approved_option or {}
        blocks = {
            "approved_option": json.dumps(option),
            "acceptance_criteria": json.dumps(self._acceptance_criteria()),
            "build_type": _build_type(option),
            "spec_context": json.dumps({
                "problem": self.state.intake_record.get("problem"),
                "acceptance_criteria": self._acceptance_criteria(),
            }),
            "target_context": json.dumps({
                "avenue": option.get("avenue"), "engine": option.get("engine"),
                "weight": option.get("weight"),
            }),
        }
        if self.state.director_responses is not None:
            blocks["director_responses"] = json.dumps(self.state.director_responses)
        return blocks

    def _qa_blocks(self) -> dict[str, str]:
        return {
            "build_manifest": json.dumps(self.state.build_manifest),
            "acceptance_criteria": json.dumps(self._acceptance_criteria()),
            "build_type": _build_type(self.state.approved_option or {}),
        }

    def _security_blocks(self, *, gov: bool) -> dict[str, str]:
        blocks = {
            "build_type": _build_type(self.state.approved_option or {}),
            "intake_extract": json.dumps(self.state.intake_record),
            "transcript": self.state.transcript,
            "stack_check_finding": json.dumps(self.state.stack_check_finding),
            "scanner_findings": json.dumps(self.scanner_findings),
            "qa_findings": json.dumps(self.state.qa_verdict),
        }
        if gov:
            blocks["governance_standard"] = self.governance_standard
        return blocks

    # == helpers =============================================================
    def _structured(self, spec: AgentSpec, blocks: dict[str, str], stage: str) -> dict:
        envelope = InputEnvelope(spec=spec, blocks=blocks)
        record = run_structured(
            self.gateway, envelope, max_attempts=self.max_attempts,
            log_event=lambda e: self.audit.raw(self.request_id, e),
        )
        self.audit.agent_call(
            request_id=self.request_id, stage=stage, agent_name=spec.name,
            prompt_version=spec.version, commit_hash=spec.commit_hash,
            input_rendered=envelope.render(), output=record,
            sensitivity=self.pipeline.data_sensitivity, validation_result="valid", retry_count=0,
        )
        return record

    def _resolve_approved_option(self) -> None:
        """The option being built: deep-dive's pick if present, else triage's pick."""
        if self.state.deepdive_output is not None:
            rec_id = self.state.deepdive_output.get("recommended_option_id")
            if rec_id:
                opt = self._option_by_id(rec_id)
                if opt:
                    self.state.approved_option = opt
        if self.state.approved_option is None:
            self.state.approved_option = self._recommended_option(self.state.triage_output or {})
        if self.state.approved_option is None:
            raise PipelineError("no approved option resolved for build")

    def _recommended_option(self, triage: dict) -> dict | None:
        rec_id = (triage.get("recommendation") or {}).get("recommended_option_id")
        return self._option_by_id(rec_id) if rec_id else None

    def _option_by_id(self, option_id: str | None) -> dict | None:
        if option_id is None or self.state.triage_output is None:
            return None
        for opt in self.state.triage_output.get("options", []):
            if opt.get("option_id") == option_id:
                return opt
        return None

    def _acceptance_criteria(self) -> Any:
        return self.state.intake_record.get("acceptance_criteria", [])

    def _enter_remediation(self, why: str) -> None:
        self._remediation_cycles += 1
        if self._remediation_cycles > _MAX_REMEDIATION_CYCLES:
            raise PipelineError(f"remediation cap hit ({why}); request not converging")

    def _security_summary(self) -> str:
        parts = []
        for label, out in (("vulnerabilities", self.state.security_vuln), ("governance", self.state.security_gov)):
            if out is not None:
                parts.append(f"{label}: {out.get('human_summary', '')}")
        return "\n\n".join(parts)

    def _email(self, *, kind: str, subject: str, body: str) -> None:
        self.emailer.send(to=self.director_email, subject=subject, body=body, kind=kind)

    def _gate_step(self) -> PipelineStep:
        stage = self.pipeline.stage
        payload = self._gate_payload(stage)
        self._email(kind="gate_prompt", subject=f"Decision needed: {stage.value}", body=json.dumps(payload)[:2000])
        self._persist()
        return PipelineStep(kind="awaiting_gate", stage=stage.value, payload=payload)

    def _gate_payload(self, stage: Stage) -> dict[str, Any]:
        if stage is Stage.GATE_1A:
            return {"options": (self.state.triage_output or {}).get("options", []),
                    "recommendation": (self.state.triage_output or {}).get("recommendation", {}),
                    "rom": self.state.rom_output}
        if stage is Stage.GATE_1B:
            return {"deepdive": self.state.deepdive_output, "rom": self.state.rom_output}
        return {"build_manifest": self.state.build_manifest, "qa": self.state.qa_verdict,
                "security": self._security_summary()}

    def _terminal_step(self) -> PipelineStep:
        return PipelineStep(kind="terminal", stage=self.pipeline.stage.value,
                            payload={"approved_option": self.state.approved_option})

    def _persist(self) -> None:
        self.datastore.set_stage(self.request_id, self.pipeline.stage.value)
        self.datastore.store_record(f"{self.request_id}:state", self.state.to_dict())


# == module helpers ==========================================================
def _as_chat(gateway: ModelGateway) -> ChatGateway:
    if isinstance(gateway, ChatGateway):
        return gateway
    raise PipelineError(
        "stack-check needs a ChatGateway; pass chat_gateway= or a gateway that implements both"
    )


def _build_type(option: dict) -> str:
    avenue = option.get("avenue")
    if avenue in {bt.value for bt in BuildType}:
        return avenue
    return BuildType.CODE.value


def _option_weight(option: dict | None) -> Weight:
    raw = (option or {}).get("weight")
    return Weight(raw) if raw in {w.value for w in Weight} else Weight.LIGHT


def _question_ids(questions: list) -> tuple[str, ...]:
    ids = []
    for i, q in enumerate(questions):
        if isinstance(q, dict):
            ids.append(str(q.get("id", q.get("question_id", f"q{i + 1}"))))
        else:
            ids.append(f"q{i + 1}")
    return tuple(ids) or ("q1",)
