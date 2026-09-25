---
name: cancer-buddy-organize
description: "Organize patient medical records into a provenance-preserving patient directory. Produces source-attributed summaries and schema-validated JSON while keeping source-reported, patient-reported and normalized layers separate. It does not infer diagnosis, stage, ECOG, response, progression, treatment line, prognosis or testing indications. Triggers on 病历整理, 整理报告, organize medical records."
---

# cancer-buddy-organize

Turn raw medical records into structured data every other sub-skill can use.

## 🔴 抗压缩不变量（读到这份 skill 就先记住这几条 —— 上下文被压缩后它们必须存活）

这条流程很长（18 步）。**当 host 压缩上下文时，“产出档案”的目标会存活，而“由谁来产”的机制会被摘掉**——于是编排者容易走捷径，自己手写 sidecar、结构化 JSON 或 HTML。这是**非法交付**。以下七条即使正文被摘要也不能丢：

1. **provenance-first：任何 `病情简要总结.html` 若不含 `<!-- template_sha256: … -->` provenance 注释 = 非法交付，必须经模板管线重生成。** HTML 的唯一合法产生路径是 `render_html_template.py` 从 `references/templates/case-summary.template.html` 渲染，永不手写 / 拼接 / 内联 HTML。
2. **段D 全管线在一个自包含 subagent 内完成并返回 `template_sha`**（Step 12）：编排者只派 subagent、收它返回的 `template_sha`、做 dated 快照。
3. **写入者白名单。** Phase 1 worker 只写 sidecar 与 `raw/` 下自己的文件；Phase 2 与 段C worker 写结构化 JSON 与 `INDEX.md`、`case_text.md`、`timeline.md`、`review_*.md`（Phase 2 在 `raw/` 下只写 `_SIDECAR_MAP.md`、只把旧产物移入 `_legacy_<ts>/`，脚本中间文本走管道），段C worker 另写 `<桶>/conversation_notes/*.md` 对话记录；段D subagent 写 `.case_summary_data.json` 与 HTML。编排者在 `<patient_dir>` 下**只**经这些固定动作写：`inventory_hash.py --mapping-out`、`library/index.json` 初值、向 `raw/_dispatch_log.jsonl` 追加派发/终止/重派记录（一行一条 JSON）、`record_gap_ask.py`、`fill_agents_md.py`、`write_organize_meta.py`、终态门 `validate_structured_outputs.py`（会并入 `UNTRUSTED-*` flag 并同步其日志哈希）、Step 12 的快照 `cp`、Step 17 的清理。其余一切——哪怕 worker 超时、被杀、看起来“很快就能自己写完”——都不手写、不用脚本写。用户在对话里作出的决定，交给执行它的 worker 落盘并记日志（Step 14）。worker 卡住就按 Step 4 终止、重派、写 stub——不接手。
4. **存活规则**：Phase 1/Phase 2 worker **10 分钟无新产物写入，或连续 30 次只读工具调用**（或返回 `timed_out: true`）→ 终止 → Phase 1 按单文件 worker 重派，Phase 2 同提示词重派一次 → 再失败：Phase 1 由 stub worker 为该文件写 `[INGESTION_BLOCKED: timeout]`，然后停下向用户报告。每次派发、终止、重派都记进 `dispatch_log` 并追加到 `raw/_dispatch_log.jsonl`（上下文压缩后仍在盘上），由 Phase 2 写入 `update_log.json`。
5. **Definition of Done（终态硬门）：本次 organize 未完成，直到文末「Definition of Done」六项全绿**——① Step 17 的 `validate_structured_outputs.py <patient_dir> --final` exit 0 且其 OK 行（含 `template_sha256`）已贴给用户；② 段D HTML 带 provenance；③ Step 12.5 语义 PII 复扫 `clean=true`；④ Phase 2.5 已跑并由 `faithfulness_patch` 记入 `update_log.json`；⑤ 每个 sidecar 的 `EXTRACTOR` 在日志 `workers[]` 里；⑥ `acute_findings.json` / `organize_meta.json` / AGENTS.md 已写。
6. **回合纪律**：一次性长任务（约 1.5–2 小时）。发出不带工具调用的消息前先跑 `validate_structured_outputs.py <patient_dir> --can-stop`，非 0 就继续；给用户的内容（急症、摘要、时效句、进度）与下一次工具调用同条发出；后台 worker 只阻塞等待，不会被唤醒。
7. **`<skill_dir>` 运行期只读**：不写、不改、不删；发现技能缺陷就停在该步，记 `raw/_dispatch_log.jsonl`（`event: skill_defect`）并写进报告。

## When to use

- User provides a folder path or set of files (PDF, JPG, PNG, DOCX, ZIP).
- User asks: 病历整理 / 帮我整理这些报告 / 我有一堆检查单.
- Any other sub-skill needs a source-attributed patient archive. Missing fields limit only the affected output; they do not block general education.

## Inputs

- Path to a folder OR a single PDF/DOCX OR a zip/rar/7z/tar.gz archive.
- Optional, only with the user's explicit authorization: an earlier organized archive to digest as history (see「旧档案摘录模式」).

## Outputs and read map

Written under `patients/<patient_code>/`. Producer = Phase 2 worker unless noted. A consumer reads **selectively**, in the order of the patient-facing read protocol (`../cancer-buddy/SKILL.md` → 档案读取协议).

| File | Role | Read it when |
|---|---|---|
| `profile.json` | Slim first-read snapshot (`cancer_buddy_profile_v3`): identity, `locale`, `summary`, `latest_status` (the ongoing episode's regimen, `as_of` and `status_basis` — an imaging-request indication or an undated family statement is not an administration record), `demographics` (copy of `patient_summary.demographics`, incl. `performance_status_verbatim[]`); schema: [`../../references/patient-profile-schema.md`](../../references/patient-profile-schema.md) | Always first |
| `readiness.json` | Documentation coverage, review flags graded by `kind` + `severity`, source recency (`latest_source_date`, `days_since_latest`, `as_of_run_date`); no clinical grade | Second — disclose uncertainty for the affected field |
| `acute_findings.json` | Source-worded acute/incidental findings with fixed-table `acuity`; **always written** (`findings: []` when none) | Before any answer about current condition |
| `INDEX.md` | Manifest (first line `# patient_code: <code>`; columns incl. 页码) | To map fact → sidecar |
| `patient_summary.json` | Authoritative demographics / diagnosis / current_status rollup (`age` etc. carry `_as_of`) | Diagnosis, staging, demographics |
| `molecular.json` / `labs.json` / `treatment_lines.json` / `timeline.json` / `comorbidities.json` | Schema-validated domain files, every row with `source_refs[]`; `hla_typing[]`, lab `pairing_method`, episode `status`/`status_basis` (one episode per regimen course — cycles are `cycle_label_verbatim`, never lines), event `conflict_group`, medication `administration_setting` | The matching question — read **one**, not all |
| `longitudinal_observations.json` | Time series (conditional) | Trend questions |
| `case_text.md` / `timeline.md` | Anchored human-readable narrative / timeline | Verbatim citation |
| `source_inventory.json` | `file_id ↔ sidecar ↔ raw_path`, sha256/size/pages, `page_label`, `source_kind`, `worker_id`, `independent_reread`, `skipped_inputs[]` | Deep-link to a `raw/` original |
| `missing_items.json` / `gap_asks.json` | Existing-document gaps incl. `missing_pages`; ask-once ledger — never a test recommendation | Completeness |
| `review_summary.md` / `review_flags.md` | Always-written spot-check; flag rendering grouped by severity/kind | Audit |
| `update_log.json` | Append-only run log (`update_log.schema.json`): `inputs[]` by sha256, `added`/`removed`, `workers[]` (every sidecar `EXTRACTOR`), `degradations[]`, optional `outputs[]` hashes | Audit / update diff |
| `organize_meta.json` | Skill version/commit/fingerprint, written by `scripts/write_organize_meta.py` at finalize | Downstream provenance (SMTB reads it) |
| `AGENTS.md` | Agent-facing recall pointer (Step 13) | Auto-loaded by harnesses |
| `病情简要总结.html` + `case_summary_versions/` | 段D summary (latest at root, dated immutable snapshots) | Hand to the patient as-is |
| `01_…14_` buckets / `raw/` | Text-masked sidecars (the downstream-only read source, no plaintext PII) / access-controlled originals under de-identified names | Sidecars via `source_refs`; `raw/` only when authorized |

`.case_summary_data.json` is a hidden render intermediate — never read it for Q&A. Uploaded originals stay once in `raw/`; they are never copied into a bucket, silently overwritten, transformed or deleted. An optional alias is a protected, user-chosen, non-clinical profile field; no diagnosis-bearing symlink or alias map is created. Derived exports require host authentication and explicit confirmation (Step 18).

## Locale (i18n)

This skill follows the shared locale contract in [`../../references/i18n.md`](../../references/i18n.md). organize is the canonical writer of `profile.json.locale`: a host-supplied `locale` wins; else reuse an existing `profile.json.locale`; else Phase 2 detects the primary record language and persists it. Patient-visible scaffold (bucket slugs from the two pinned sets, narrative prose, 段D template strings, 段E/段C cards) renders in that locale. **Source strings are always preserved**: a labeled translation may be added beside the original, but it never silently replaces a drug, gene/variant, TNM/stage string, value, unit or biomarker label. An explicit user language override updates `profile.json.locale`.

## Workflow

> **路径**：本文件与各 worker 提示词里的 `scripts/…`、`references/…` 都相对本 skill 目录。派发每个 worker（Phase 1 / 2 / 2.5、段D、PII 复扫）都传 `skill_dir` = 本目录的绝对路径——子代理的工作目录不是它，编排者自己运行脚本时同样用 `<skill_dir>/scripts/…`。

> **跨 host 提示**：Step 2–5 的 `Agent` 并行 fan-out + reduce 是 Claude Code 参考绑定，不是契约。单进程 host 以 [`references/organize-contract.md`](references/organize-contract.md) + [`references/runtime-bindings/headless-codex.md`](references/runtime-bindings/headless-codex.md) 为准：顺序逐源调用，产物集与不变量完全一致。

1. **Resolve input** — confirm the path with the user. `$src` is the directory Step 1 inventories: a folder the user gave is used in place (`src=<that folder>`); only an archive is unpacked, into a fresh private temp dir `unpack_dir=$(mktemp -d)` (mode 0700), and then `src=$unpack_dir`. Note `unpack_dir`'s path (each shell call starts fresh) — it is the only directory Step 17 removes.
   **Never removed**: `$src` itself, `raw/` and the user's input folder hold patient originals.
   Then:
   - **Run-start question (always ask before dispatching)**: “开始整理前确认一下：除了这次提供的文件，是否已有比这些更新的检查或记录（例如最近的影像、化验或门诊记录）？如果有，建议一并提供后再开始。” Non-interactive hosts make it a non-blocking confirm item.
   - **Input manifest**: once `<patient_dir>/raw/` exists (update run; new patient: after Step 2a) run `python3 "<skill_dir>/scripts/inventory_hash.py" "$src" --mapping-out "<patient_dir>/raw/_INPUT_HANDLES_<YYYYMMDDTHHMMSS>.json"` (sha256, size, page count; `.DS_Store` / `__MACOSX` / empty / duplicate sha256 / archive container listed as skipped). Its stdout carries only de-identified handles (`in-NNN` inputs, `skip-NNN` skipped); the handle → upload-path map stays in that `raw/_…` file, passed to Phase 1 as `input_handles`. Assign `source_id`s (`s001`…) in handle order; a prior-archive digest gets the next `sNNN` after them.
   - **Update case** (existing `<patient_dir>`): run `python3 "<skill_dir>/scripts/validate_structured_outputs.py" --generation <patient_dir>` — the validator's own predicate (a current-contract marker: `organize_meta.json`, `readiness.json` ≥ 2.1, a structured file at its current version, a ledger entry with `workers[]`, a sidecar `EXTRACTOR`; `acute_findings.json` is not one). `current` → diff the manifest **by sha256** against the last `update_log.json` entry with a non-empty `inputs[]` plus `source_inventory.json.skipped_inputs[]` (earlier duplicates/quarantined files) → only new sha256 are ingested; report added/removed to the user. `legacy` (a `schema_version: "1"` ledger of legacy-shaped entries included) → **legacy upgrade** (see「Incremental and update runs」); only with **no new files** and the user deferring the one-time re-transcription may Phase 2 alone re-run (`legacy_phase2_only`). Never patch old results with new files by hand.
   - **Prior archive**: if an earlier organized archive for this patient is visible, ask whether it may be used; without an explicit yes it is ignored (「旧档案摘录模式」).

2. **Plan slicing** — 2a (patient code + dirs, below) → Step 1 manifest → 2b slicing: **MAX 15 image-like inputs per Phase 1 worker on Claude Code** (a per-conversation image budget; host-tunable, not a contract invariant). Single-pass ≤ 15 files; ≥ 2 subdirectories → one worker per subdir, splitting any subdir > 15 files into parts; flat > 15 files → `batch_a`/`batch_b`… Workers run in parallel.
   Generate `patient_code` as `"PT-" + secrets.token_hex(5).upper()` (upper-case hex — every schema rejects lower case; never derived from a name, path, diagnosis or timestamp; reject a supplied real-world identifier). Resolve `patient_data_root` from `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients`; `mkdir -p` **only `ocr/` + `raw/` + `library/`** and seed `library/index.json` as `{"entries": []}`. **Do NOT pre-create the 14 clinical buckets** (an empty bucket would imply “no such record”). `library/` is infrastructure, not a clinical bucket, and never a `source_refs` target.

3. **Dispatch Phase 1 source-fidelity workers (parallel)** — one `general-purpose` subagent per slice, `description: "Organize source-fidelity ingestion slice <slice_id>"`, prompt = full content of [`references/organizer-prompt-phase1-ocr.md`](references/organizer-prompt-phase1-ocr.md) plus `## Call parameters`: `worker_id` (`p1-<slice_id>-<n>`), `slice_id`, `slice_input_path`, `patient_dir`, `original_subdir`, `source_ids` and `input_handles` (from Step 1), `skill_dir`. Pixel pages: the model's whole-page transcription is the body, then `second_read_align.py` runs the OCR engine once (agree / no signal / conflict; only conflicts get tokens); born-digital pages: the text layer is the body, no OCR. Workers write only `ocr/` sidecars (12-key header, `EXTRACTOR` = worker id), `raw/` originals, their `raw/_extract/` files and their own `raw/_identity_denylist/<worker_id>.json`, and return `{worker_id, elapsed_s, timed_out, sidecars_written, sources, skipped_inputs, ingestion_blocked_files, pii_rescan_passed, continuation_needed, continuation_resume_from, …}`.

4. **Continuation and liveness** — a worker returning `continuation_needed: true` gets a continuation worker for the rest of its slice (complete sidecars are skipped — phase1 §1 idempotency: valid 12-key header, matching `SHA256`, `## PII` trailer, not an `in_progress_timeout_risk` stub, a script-written `## 高风险字段复读` block). While workers run, watch for new files in `ocr/` (Phase 2: new writes under `<patient_dir>`). **10 minutes without a new artifact, or ≥ 30 consecutive read-only tool calls** → stop the worker; keep its complete sidecars. Every unfinished file — no complete sidecar, or listed in a returned `timeout_risk_files` (`timed_out: true`) — is redispatched as a **single-file worker** (`p1-<source_id>-<n>`). A single-file worker that also times out (killed, or `timed_out: true`) → dispatch a stub worker (`mode: stub`, `p1stub-<source_id>`) that writes `[INGESTION_BLOCKED: timeout]`, then **stop and report** the blocked file to the user (retry, exclude, or continue with the stub as a known gap). Record every dispatch/kill/redispatch in `dispatch_log` (kill → `degradations[]`). Host-specific observation: [`references/runtime-bindings/`](references/runtime-bindings/).

5. **Dispatch the Phase 2 synthesis worker** — a single subagent with the full content of [`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md) plus `skill_dir`, `worker_id` (`p2-<n>`), `patient_dir`, `phase1_summary`, `dispatch_log`, `run_mode` (`full` | `legacy_upgrade` | `legacy_phase2_only` | `incremental` | …), `as_of_run_date` (the run's local date; the log's `at` is UTC), `input_manifest`, `locale`, `prior_archive_authorized`, `redispatch`. Phase 2 checks a write-ahead bucket plan with `scripts/check_bucket_path.py` **before any mkdir/mv**, relocates sidecars, and writes every structured artifact incl. `acute_findings.json` and the `update_log.json` entry. It returns `{worker_id, elapsed_s, timed_out, coverage_complete, missing_sidecars, bucket_precheck_rejections, missing_pages_groups, latest_source_date, days_since_latest, acute_findings_total, acute_findings_urgent_or_emergent, acute_findings_urgent[] (with verbatim_text, verbatim_is_translation), case_summary_rerender_required, review_flags_total, review_flags_red, review_flags_yellow, review_flags_info, review_flags_by_kind, …}`. Same liveness rule: one redispatch (`redispatch: true` — it resumes from `.rename_plan.json`), then stop and report.

6. **Coverage retry** — `coverage_complete: false` → mini Phase 1 for the `missing_sidecars` (incl. header-invalid ones), then Phase 2 again.

7. **Verify outputs** — parse Phase 2's JSON; confirm `profile.json` plus provenance fields validate. Missing diagnosis fields stay unknown; they limit only affected patient-specific output.

Steps 7.5–11.4 reach the user in the same message as the next tool call (invariant 6).

7.5. **Acute findings first (every mode)** — after any Phase 2 pass, legacy archives and Phase-2-only reruns included, if `acute_findings.json` (or Phase 2's returned `acute_findings_urgent[]`) has `emergent`/`urgent` rows, show them before anything else: each verbatim with date and source, stated as findings the report itself wrote that belong to the “tell the treating team soon” class, routed per `safety-guardrails.md` → Urgent physical symptoms; a `verbatim_is_translation: true` row is labelled “中文转述，非报告原句”, never presented as the report's own words. No cause, severity or management advice. Step 12 then re-renders 段D in its turn (mandatory, not asked). Rules: [`references/acute-findings.md`](references/acute-findings.md).

8. **Describe coverage, pages and recency** — no A–F grade. `document_gaps` are existing records not found, never a reason to order a test. Report missing-page groups (`missing_pages`) and, when `days_since_latest > 14`, relay the recency line from `readiness.json.warnings[]` verbatim — the one sentence `scripts/source_freshness.py` writes (`STALE_WARNING_TEMPLATE`: “本档案最新一份资料的日期为 {latest}，距本次整理已 {days} 天；请确认此后是否有新的检查报告或病历，时效说明需写明这一天数。”, phase2 §6.2); never reword it.

9. **Display review_summary.md (MANDATORY, ALWAYS)** — show it in full; it catches consistently-wrong transcription that flags cannot. Invite corrections as a separate patient-reported layer: “如果这里和你的理解不一致，我可以记录你的说法；正式临床字段仍需原报告更正或主诊医生核对。”

10. **Surface review_flags (MANDATORY)** — if `review_flags_total > 0`, show `review_flags.md`, grouped `red` → `yellow` → `info` and by `kind` (字迹不清 / 版面异常 / 文书删改 / 来源不一致 / 缺页与资料时效 / 其他). **`severity` grades extraction/archive-completeness uncertainty, not clinical severity.**
    - `red`: the affected field cannot be used for patient-specific reasoning until an amended source or authorized clinician attestation resolves it.
    - `yellow` / `info`: present as “建议核对”; do not block downstream routing.
    - `0` flags: say no unresolved extraction flags were raised and still ask for a look at the review_summary.
    - A user acknowledgment is logged but never clears a source-level conflict or promotes a candidate reading.
    - **Time-varying fields never produce a conflict flag for normal evolution** (age, weight, height, ECOG, performance status, `current_status.*` at different report dates) — [`references/organizer-prompt-phase2-synthesis.md`](references/organizer-prompt-phase2-synthesis.md) §2.1.

11. **Output profile card** (after Step 11.5 and its `faithfulness_patch`, so a flagged value is shown flagged) — [references/profile-card.md](references/profile-card.md), with `terminology.md` format rules. “🔍 待人工确认” comes from `readiness.json.review_flags[]`. **Downstream gate**: an unresolved red-flag field, an unconfirmed `document_intent` field or any `[OCR_UNCERTAIN:U-nnn]` field is never a premise for staging, pathology or treatment reasoning; unrelated safe functions continue with the limitation stated.

11.4. **补料信号** — one short, low-pressure offer to add an existing record directly relevant to the requested artifact, per [`references/gap-followup.md`](references/gap-followup.md). No clinical priority, no test recommendation. Before asking run `record_gap_ask.py <patient_dir> check --item-key <K>`; after asking, `… ask --item-key <K> --category <…> --trigger step_11_4` (the ask-once ledger `gap_asks.json`, its only writer).

11.5. **Phase 2.5 — faithfulness check (MANDATORY, before 段D)** — dispatch [`references/organizer-prompt-phase2_5-faithfulness.md`](references/organizer-prompt-phase2_5-faithfulness.md) (`p25-<n>`). A model rereading a sidecar or image is not independent evidence. **Always** follow it with a Phase 2 worker in `run_mode: faithfulness_patch` (phase2 §11; pass `faithfulness_results` and the `p25` worker id): it writes the graded flags for `not_faithful` / `needs_human_review` / `disputed` results, re-stitches `profile.json.summary.one_line_condition` without an unfaithful component, and appends the `update_log.json` entry that records the `phase2_5` worker even when everything was faithful — the only on-disk trace that Phase 2.5 ran. The orchestrator patches none of these files. Pass every `not_faithful` result with `severity: red` (`{file, json_path, value}`) as `unfaithful_values` to Step 12. Done-conditions: the Definition of Done below.

12. **Generate 病情简要总结.html (段D)** — mandatory after every Phase 2 pass that returns `case_summary_rerender_required: true` (it registered or changed an emergent/urgent finding, or its §9 run reported an `ERROR: .case_summary_data.json` line), and whenever any validator run reports such a line — e.g. a render made under an earlier 段D contract (the retired 「资料中有报告原文写到…」 lead): its stamp proves the data, not the contract, so no finding needs to change. Not asked, non-interactive hosts and `legacy_phase2_only` included (段D reads the current JSON as-is; it does not upgrade the archive). If it cannot render, Phase 2's stale notice stays in `review_summary.md` / `readiness.json.warnings[]` — tell the user. Dispatch the 段D subagent with [`references/case-summary-html-prompt.md`](references/case-summary-html-prompt.md), passing `unfaithful_values` and unresolved disputes (never an adjudicated winner). **🔴 The 段D subagent owns the whole pipeline** (data assembly → enrich → stamp `acute_findings_sha256` → render → validate, section「段D 管线」of that file) and returns either `{status:"ok", template_sha}` or `{status:"failed", reason, exit_code}` — never inline HTML. The orchestrator only dispatches, checks that a passing `template_sha` came back (redispatch on failure; never accept a hand-written HTML or a “done” without `template_sha`), then makes the dated snapshot:

    ```bash
    ver_date=$(date +%F); d="<patient_dir>/case_summary_versions"; mkdir -p "$d"
    snap="$d/病情简要总结_${ver_date}.html"; dsnap="$d/case_summary_data_${ver_date}.json"
    n=2; while [ -e "$snap" ]; do snap="$d/病情简要总结_${ver_date}_${n}.html"; dsnap="$d/case_summary_data_${ver_date}_${n}.json"; n=$((n+1)); done
    cp "<patient_dir>/病情简要总结.html" "$snap"; cp "<patient_dir>/.case_summary_data.json" "$dsnap"
    ```

    The renderer is a zero-medical-logic template engine that stamps a `template_sha256:` provenance comment; `null` renders as `资料缺失`; trends are descriptive only; ECOG/response are clinician-reported only; acute findings appear through caveats. Never mark a medical source `persist:false` to pass a gate.

12.5. **Semantic PII scan (Layer 1, MANDATORY)** — dispatch a subagent with [`references/pii-rescan-prompt.md`](references/pii-rescan-prompt.md) (`pii-<n>`; params `patient_dir`, `skill_dir`, `surfaces` = every bucket sidecar + the synthesized and delivered surfaces incl. `病情简要总结.html`). It returns `{worker_id, findings[{surface, line, category}], clean}` — never the matched values. Findings in a sidecar → redispatch that original to a single-file Phase 1 worker; in a synthesized/delivered surface → Phase 2 `run_mode: pii_remask` (phase2 §13; it records the `pii_rescan` worker in `update_log.json`), then re-render 段D if its data changed; then scan again, until `clean=true`. Record the clean worker in Step 17 (`--pii-layer1`).

13. **Generate AGENTS.md** — `python3 "<skill_dir>/scripts/fill_agents_md.py" "<patient_dir>"` (verify with `--check`) fills [`references/templates/agents-md.template.md`](references/templates/agents-md.template.md) from exactly two `profile.json` fields (`patient_code`, `summary.one_line_condition`). It fails on a residual placeholder, a stub, a wrong `patient_code`, a missing routing anchor or red line, or a stale template hash. Always runs on a full build, independent of the 段D outcome; idempotent on later runs. Never author a new template. The citation rendering spec stays in `../cancer-buddy/SKILL.md`「来源引用」节; AGENTS.md carries only the self-contained floor.

14. **无关文件处置门 (段E)** — Phase 2 has quarantined `likely_unrelated` / `possibly_relevant` files under `99_无关文件/`; show an item-specific preview and reason, and explain that silence means hold ([`references/relevance-gate.md`](references/relevance-gate.md)). Delete only on explicit item-specific confirmation; medical, medication, symptom, wound, device, billing and borderline material defaults to hold. Collect the decisions (`{item, action, confirmation_text, actor_role}`) and dispatch a Phase 2 worker with `run_mode: relevance_disposition` (phase2 §12): it executes them, re-synthesizes restored sources (inventory, domains, acute findings, pages, recency) and appends the `update_log.json` entry. A restore that returns `case_summary_rerender_required: true` sends you back to Step 12 before Step 17. The orchestrator neither moves/deletes these files nor writes `update_log.json`.

15. **Conversation-incremental capture (段C, on demand)** — see「Conversation-incremental mode」.

16. **Upload reconciliation (扩段C, on re-upload)** — see「Incremental and update runs」.

17. **Finalize** — after Phase 2 has recorded skipped inputs in `source_inventory.json`: remove stray `.DS_Store` files, remove `ocr/` only if empty (a non-empty `ocr/` means a sidecar was not placed — warn, do not delete), write the run metadata, run the terminal gate, and only then remove the Step 1 archive unpack dir:

    ```bash
    find "<patient_dir>" -name .DS_Store -type f -delete
    rmdir "<patient_dir>/ocr" 2>/dev/null || true
    python3 "<skill_dir>/scripts/write_organize_meta.py" "<patient_dir>" --pii-layer1 <pii-worker-id>   # → organize_meta.json
    python3 "<skill_dir>/scripts/validate_structured_outputs.py" "<patient_dir>" --final   # terminal gate (DoD 1)
    unpack_dir="<the path noted in Step 1; empty when no archive was unpacked>"
    [ -n "$unpack_dir" ] && case "$unpack_dir" in "${TMPDIR:-/tmp}"*) rm -rf "$unpack_dir";; esac
    ```

    That `rm` touches only an archive's temp unpack dir. `$src`, `raw/` and the user's input folder are never removed; a lost `unpack_dir` path is left to the OS, never guessed or globbed.

    `organize_meta.json` must exist before the terminal gate: its presence (like any current-contract marker) makes every current-contract check FAIL rather than WARN, and the gate requires its `pii_layer1_scan` (DoD 3 on disk). `--final` (terminal gate only; Phase 2 §9 runs without it) also requires `INDEX.md`, `timeline.md`, `case_text.md`, `review_summary.md`, AGENTS.md, the 段D HTML with its render's `acute_findings_sha256` stamp, an empty `ocr/` and a `phase2_5` worker logged after the last ingest run, and echoes the HTML's `template_sha256` in its OK line — compare it with the `template_sha` 段D returned. **Exception**: `legacy_phase2_only` (phase2 §4.0/§8) skips `write_organize_meta.py` — the file would declare the un-upgraded archive current — and tells the user the archive still needs one `legacy_upgrade`. The terminal gate runs without `--readonly` (it records untrusted-content flags in `readiness.json`), as does the Phase 2 worker's own §9 run (every `run_mode`); every other check — downstream, audits, replays — passes `--readonly`.

18. **Purpose-limited export (on demand)** — authenticate the actor, verify authority, confirm recipient, scope, purpose, de-identification choice and expiry, select only the necessary relative paths, rerun source-faithfulness and both PII layers; if any gate is unavailable or has findings, do not export. Then:

    ```bash
    python3 "<skill_dir>/scripts/export_share.py" <patient_dir> --out <dest> --include profile.json \
      --include 04_诊断与分期/病理报告/<selected-sidecar>.md --recipient <recipient> \
      --purpose <purpose> --expires-at <ISO-8601> --authorization-ref <host-audit-id>
    ```

    The exporter rejects broad/protected paths, excludes `raw/` and provenance/build files, requires future expiry and writes `_SHARE_MANIFEST.json`. The host remains responsible for legal basis, secure transfer, recipient verification, revocation and audit. A clean scan reduces risk but does not guarantee anonymity.

## Definition of Done（终态硬门 —— 结束前必过、必贴）

以下**全绿之前，本次 organize 未完成**，不许对用户说“整理好了”：

1. **结构化验收门 exit 0 且已贴输出**：Step 17 写完 `organize_meta.json` 之后运行 `validate_structured_outputs.py <patient_dir> --final`（schema + anchors + PII shape + source-shape fidelity + source inventory + sidecar headers + bucket paths + acute/page/recency/update_log/lab-pairing bindings + HTML form/provenance）。它不判断临床值是否正常或重要。它需要 `jsonschema>=4.18`：缺失时当前契约档案直接失败（`lightweight checks only` 从来不是完成）。贴出它的 `acceptance gate OK` 行（`--final` 在行内回显 HTML 的 `template_sha256`），它必须等于 Step 12 段D subagent 返回的 **`template_sha`**。
2. **段D HTML 带 provenance**：含 `<!-- template_sha256: … -->` 注释。
3. **PII Layer-1 语义扫描 clean**：Step 12.5 的 [`references/pii-rescan-prompt.md`](references/pii-rescan-prompt.md) 子代理返回 `clean=true`，其 worker id 经 `write_organize_meta.py --pii-layer1` 记入 `organize_meta.json`（验收门检查）。
4. **Phase 2.5 已跑且已处理**：`faithfulness_patch` 已把 `phase2_5` worker 记入 `update_log.json`（`--final` 检查），`severity: red` 的 `not_faithful` 值已写 flag、从 `one_line_condition` 去掉，段D 把它显示为“待核对”（不复述该值）。
5. **worker 来源可查**：桶内**每个** sidecar（`conversation_notes/` 除外）都有 12 键头部，`EXTRACTOR` 出现在 `update_log.json` 某条目的 `workers[]` 中；没有编排者署名或无头部的 sidecar。旧版档案没有例外：第一次更新即走旧档案升级（下文），重新转写全部原件（没有新文件时的 `legacy_phase2_only` 不是升级：档案仍待升级）。
6. **`acute_findings.json` 已写**（无发现时 `findings: []`；`legacy_phase2_only` 也写），**`organize_meta.json` 已写**（`legacy_phase2_only` 除外，见 Step 17），**AGENTS.md 已生成且非 stub**。

自检话术：`validate_structured_outputs.py exit 0 ✅ · template_sha=<…> ✅ · PII clean ✅`。任一非绿 → 回到对应 Step 修复重跑，不要把不合规产物留在 `patient_dir` 或报完成。

## Runtime adaptation

Step 2–5 (slicing → parallel `Agent` Phase 1 → continuation/liveness → single Phase 2, `sips` HEIC decode, model transcription of pixel pages with a script-run engine second read, text layers for born-digital pages) is the **Claude Code reference binding**. The runtime-neutral behavior contract is [`references/organize-contract.md`](references/organize-contract.md); per-host fill-ins (available read channels, how liveness is observed, worker ids) are in [`references/runtime-bindings/`](references/runtime-bindings/) (`claude-code.md`, `headless-codex.md`, `grok-build.md`, `_template.md`). Any host produces the same canonical output set and honors the same invariants: source strings and provenance are retained; reported, normalized and prior-archive layers stay separate; originals remain in `raw/`; derived and delivered surfaces are PII-scanned; unconfirmed user talk never becomes clinician fact; nothing is deleted irreversibly without explicit item-specific confirmation; only workers write sidecars and structured JSON. Parallelism only changes speed.

## Incremental and update runs

- **Incremental** (`run_mode: "incremental"`, `update_log.json` with `schema_version: "1"`): the Step 1 sha256 diff decides what is new; Phase 1 ingests only new sha256; Phase 2 classifies only the new sidecars, rewrites top-level artifacts only when their content changes, and appends an `update_log.json` entry (`inputs[]` = every original now in the archive, `added[]`, `removed[]`, `workers[]`, `degradations[]`). `profile.json.alias` is user-controlled and never regenerated. Use a full run for the first organize or after major changes.
- **Legacy upgrade** (archive without a `schema_version: "1"` `update_log.json`, i.e. organized before this contract): the first run is `run_mode: "legacy_upgrade"` — always a full Phase 1 re-transcription plus a full Phase 2, never a partial version bump (bumping some files flips the whole archive to the current contract and every untouched legacy file and header-less sidecar then fails the gate; `legacy_phase2_only` keeps the old version numbers, does not convert the old log, and Step 17 then writes no `organize_meta.json` — it would make the archive current-contract; phase2 §4.0/§8). `$src` = the archive's own `raw/` (`inventory_hash.py` ignores its `_*` entries) plus any new files (a new archive among them unpacks into `unpack_dir`, Step 1; `raw/` is never removed); Phase 1 re-transcribes every original under the 12-key header; Phase 2 first moves the old `01_`–`14_` buckets, the old `update_log.json` and the other rewritten top-level outputs into `raw/_legacy_<ts>/` (never deleted; inside the access-controlled vault because old surfaces may carry upload names), puts `conversation_notes/` back, and carries over `profile.json.alias` and conversation-anchored self-reports (phase2 §4.0). Tell the user this is a one-time re-transcription. From then on, sha256 diffs work.
- **Case-summary freshness gate**: after any run that changes a summary-source file (`profile.json`, `patient_summary.json`, `molecular.json`, `labs.json`, `treatment_lines.json`, `timeline.json`, `longitudinal_observations.json`, `acute_findings.json`) later than `病情简要总结.html`, ask in `profile.json.locale` (“你的病情记录有更新（<改了什么>）。要我重新生成一份病情简要总结吗？”). Only an explicit yes re-dispatches Step 12 (a non-interactive host does not regenerate: it reports the staleness and what changed); on no/defer nothing is written — the next session detects the same staleness and asks again. Every regeneration adds a dated snapshot; no silent rewrite, no loss of a shared version. **Safety override — a new or changed emergent/urgent finding is never asked about**: Step 12 re-renders without asking, in its turn (after Phase 2.5 when that runs; non-interactive hosts and `legacy_phase2_only` included). Until then Phase 2's pinned stale notice (phase2 §7) must stand in `review_summary.md` and `readiness.json.warnings[]`: without it the validator ERRORs (legacy archives too), with it `段D stale` is a WARN. A render that read the finding and left it out is an ERROR (the render stamps `acute_findings_sha256`), and `--final` ERRORs on any stale lead. Any `ERROR: .case_summary_data.json` line falls under the same override: dispatch Step 12, never ask.
- **Re-upload onto an existing archive** (`run_mode: "upload_reconciliation"`): 段E relevance gate per new file, then an LLM new/supersede/conflict judgment → a diff card (替换? 并存? 忽略?) behind the same **先确认** door (shared [`../../references/confirm-gate.md`](../../references/confirm-gate.md)); 替换 keeps the old sidecar and its anchors in place and records `superseded_by` (phase2 §12). The confirmed choices go to the reconciling Phase 2 worker as `user_decisions`; it applies them and records them in its `update_log.json` entry. Full logic: [`references/upload-reconciliation.md`](references/upload-reconciliation.md).

## 旧档案摘录模式（prior archive digest）

Only when the user **explicitly authorizes** using an earlier organized archive (the session record shows the authorization; silence or a general “继续” is not authorization):

- Dispatch a Phase 1 worker with `mode: prior_archive_digest` (`p1digest-<n>`), `prior_archive_dir`, `authorization_note`. It reads only the prior archive's de-identified sidecars/JSON (never its `raw/`) and writes one digest sidecar.
- Phase 2 files it in `03_病程与叙事文书/既往档案摘录/`; its inventory row has `source_kind: prior_archive_digest`, `raw_path: null`, `sha256: null` (header `SHA256: none`) and `digest_of {archive_ref, archive_generated_at, sidecar_refs[]}`; every fact it supports is `provenance_layer: prior_archive`. A digest-looking sidecar without the 12-key header is a legacy sidecar: it is regenerated (digest worker / `legacy_upgrade`), never filed as a digest by its content.
- History only: never `current_status`, `latest_status`, the current regimen, an acute finding or the basis of a recommendation; old consult recommendations, trial scores and line numbers are not carried over; conflicts with current originals stay side by side. Every surface citing it labels “来自既往摘要，原件未在本次资料中”.

## Conversation-incremental mode (段C)

`run_mode: "conversation_incremental"` uses [`references/conversation-incremental-prompt.md`](references/conversation-incremental-prompt.md) in two dispatches: `mode: propose` (returns a **diff card** with the speaker's words, writes nothing) → you show the card → `mode: write` with the user's `user_confirmation`. The user confirms only that the note faithfully captures what they said; on a legacy archive 段C writes no log entry and asks for `legacy_upgrade`. Confirmation archives only the `patient_reported`/`caregiver_reported` layer with `[[src:conversation:<ISO8601>]]`; it never turns stage, ECOG, response or progression into clinician-verified fact. Conflicts stay `disputed`. Urgent symptoms in the conversation are escalated before archiving.

## Optional alias, patient_code, root

- A user-chosen non-clinical, non-identifying alias may be stored as a protected profile field; Phase 2 never generates one and never creates a symlink. The random `patient_code` is the storage locator, not authentication.
- If a generated `patient_code` already exists, append `_2`, `_3` and announce the assigned code.
- `patients/` root: `$CANCER_BUDDY_PATIENTS_DIR` → `$VMTB_PATIENT_DATA_ROOT` → `$HOME/CancerDAO/patients` (shared with SMTB/vmtb).

## Safety

Organize does not make medical recommendations. Still:

- Never fabricate fields — an unreadable value is `null` (JSON) or a literal reading plus `[OCR_UNCERTAIN:U-nnn]` (text), with each channel's reading and lexicon-only candidates in the sidecar's `## 不确定字段` block (phase1 §5). Candidates are readings, never corrected values, and never enter a structured value field.
- Lab tables pair columns deterministically (phase1 §7): position-paired values are `candidate_value` only; if the item count differs from the result count, nothing is paired.
- A layout observation (strikethrough, overprint, stamp) is not a document intent unless two independent reads agree; otherwise it is recorded as “版面异常，字面读作 X”.
- Text masking masks PII only in the sidecar body — it never alters clinical characters (anti-anchoring). The MD sidecar is the downstream-only read source and must not carry plaintext PII. Delivered surfaces (INDEX.md / source_inventory.json / update_log.json / dotfiles / 病情简要总结.html) and synthesized surfaces are additionally scanned; de-identification covers the sidecar body AND every delivered surface. Uncertainty readings never contain PII.
- Downstream sub-skills apply the full `safety-guardrails.md` rule set ([`../../references/safety-guardrails.md`](../../references/safety-guardrails.md)); wrong data here poisons every downstream report.
- Original bytes are preserved under host access control; the skill does not promise anonymity or indefinite retention. Summaries and exports apply authorization, purpose limitation and data minimization; age, dates, institution and other quasi-identifiers are included only when necessary.

## Next-step guidance

After a successful organize, route to the most relevant companion; a clinical-decision request goes to the treating team, and no other tool is auto-installed or implied to have supplied a clinical conclusion:

- Newly diagnosed → `cancer-buddy-education` or the meta `cancer-buddy` router.
- Gene report and treatment questions → organize the report and questions, then route to the treating team or a formal second opinion; no actionability interpretation.
- Trials → `cancer-buddy-find-care` (listed sites and official contacts; no eligibility judgment).
- Clinic visit coming → `cancer-buddy-visit-prep`.
- Published comparable cases → `cancer-buddy-case-precedent` (a biased case-report search; no treatment direction or prognosis; never auto-search).

## Role behavior

Authoritative matrix in `../../references/roles.md`. For this skill:

- **Role = patient**: First-person. "帮我整理我的病历" → produce source-attributed archive files. Patient statements remain `patient_reported` and do not overwrite clinician-source facts.
  - *Disclosure*: organizing records may surface diagnosis details. A capable patient's explicit request for their own information is not overridden by family suppression; for another viewer, show only authorized content and route capacity/代理争议 to the treating institution ([`../../references/disclosure-behavior.md`](../../references/disclosure-behavior.md)).
- **Role = caregiver**: Second-person. "帮你家人整理报告". Require host authorization for the task and keep authorization/contact data outside the clinical summary. Tone may acknowledge caregiver workload without implying decision authority.
- **Role = family**: if authorized for this task, operate only within that documented scope; otherwise provide a blank organization checklist without reading/writing patient records. Relationship labels alone neither grant nor deny authorization.

## Charting an indicator the user asked about

When the user asks about a **specific named lab value or observation**, check `longitudinal_observations.json` / `labs.json` first: **≥ 2 comparable points** → answer in text and attach a chart (`python3 "<skill_dir>/../cancer-buddy-charts/scripts/render_chart.py" --chart trend --from-longitudinal <patient_dir>/longitudinal_observations.json --metric <analyte> --out-html <patient_dir>/charts/<analyte>_趋势.html`); fewer or not comparable → say in one line why there is no chart. Only confirmed `value`s are charted — never a `candidate_value`. A general question does not auto-chart; list the series and let the user pick; “都画出来” charts them all.

Answer the question rather than walling it off: what the indicator is, why reference ranges differ, what guidelines generally say about follow-up (verify a current primary source and cite it; route to `cancer-buddy-education`). Only a verdict on **this person's numbers** — response, progression, regimen change, prognosis — routes to the treating team, woven into the answer. Keep script names, exit codes and rule numbers out of the reply.

## References

- [organizer-prompt-phase1-ocr.md](references/organizer-prompt-phase1-ocr.md) — Phase 1 worker: 12-key sidecar header, read channels and independence, uncertainty block, lab column pairing, liveness, stub and prior-archive modes
- [organizer-prompt-phase2-synthesis.md](references/organizer-prompt-phase2-synthesis.md) — Phase 2 worker: provenance layers, conflicts, write-ahead bucket plan, structured JSON, flag grading, recency, update_log
- [organizer-prompt-phase2_5-faithfulness.md](references/organizer-prompt-phase2_5-faithfulness.md) — independent faithfulness check; reports only, never proposes a replacement value
- [acute-findings.md](references/acute-findings.md) — finding classes, fixed acuity table, allowed source-wording shifts
- [lexicons/](references/lexicons/) — one-term-per-line candidate lexicons (drugs, IHC markers, lymph-node stations); constraints for OCR candidates, not a judgment or translation table
- [conversation-incremental-prompt.md](references/conversation-incremental-prompt.md) — 段C diff-card capture of patient-reported facts
- [relevance-gate.md](references/relevance-gate.md) — 段E triage and quarantine; silence always holds
- [upload-reconciliation.md](references/upload-reconciliation.md) — 扩段C re-upload relations; a prior-archive digest is not an upload
- [case-summary-html-prompt.md](references/case-summary-html-prompt.md) — 段D data mapping and pipeline
- [templates/case-summary.template.html](references/templates/case-summary.template.html) / [templates/agents-md.template.md](references/templates/agents-md.template.md) — the only templates
- [profile-card.md](references/profile-card.md) · [gap-followup.md](references/gap-followup.md) · [bucket-taxonomy.md](references/bucket-taxonomy.md) · [PATIENT_DIR_CONTRACT.md](references/PATIENT_DIR_CONTRACT.md) (producer/consumer contract incl. SMTB)
- [references/schemas/](references/schemas/) and [anchor-contract.md](references/schemas/anchor-contract.md) — JSON Schemas and `[[src:…]]` anchor contract; [references/checklists/](references/checklists/) — existing-document inventories
- Scripts: [validate_structured_outputs.py](scripts/validate_structured_outputs.py) (acceptance gate; `--final` at Step 17, `--readonly` for audits, `--generation`), [render_html_template.py](scripts/render_html_template.py), [validate_case_summary_html.py](scripts/validate_case_summary_html.py), [pii_rescan.py](scripts/pii_rescan.py) (deterministic PII shape floor; Layer 1 is the semantic scan in `pii-rescan-prompt.md`), [export_share.py](scripts/export_share.py), [fill_agents_md.py](scripts/fill_agents_md.py); deterministic helpers `inventory_hash.py` (`--mapping-out`, `--quarantined`/`--exclude` for 段E skip rows), `pair_lab_columns.py` (`--text`/`--tsv`/`--columns`), `page_completeness.py` (`--inventory`), `source_freshness.py` (`--as-of`), `check_bucket_path.py` (`--taxonomy`), `write_organize_meta.py` (`--pii-layer1`, `--skill-dir`, `--generated-at`), `record_gap_ask.py`, `lexicon_candidates.py`, `stamp_case_summary_sources.py` (段D's `acute_findings_sha256`)
- Shared: [preflight.md](../../references/preflight.md) · [i18n.md](../../references/i18n.md) · [terminology.md](../../references/terminology.md) · [safety-guardrails.md](../../references/safety-guardrails.md) · [disclosure-behavior.md](../../references/disclosure-behavior.md) · [citation-format.md](../../references/citation-format.md) · [evidence-trust-tiers.md](../../references/evidence-trust-tiers.md) · [reference-library.md](../../references/reference-library.md) · [confirm-gate.md](../../references/confirm-gate.md)
