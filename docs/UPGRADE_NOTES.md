# CONTROLPC — Upgrade Notes (Fable 5 review, 2026-06-12)

A full-codebase review (6 reviewers, UI-weighted) produced ~75 recommendations.
This file is the durable record. Items marked **[DONE]** were implemented by Opus
in the same pass; **[DEFERRED]** items are larger/riskier refactors left for a
follow-up so they can be implemented and verified with proper care (they were not
done right before a release + shutdown on purpose).

Severity: 🔴 high · 🟡 medium · ⚪ low.

---

## 1. UI / UX (frontend/src/App.jsx) — user's top priority

- 🔴 **[DONE]** Connection indicator never re-polled → `Send` could stay disabled
  forever. Now `fetchStatus()` sets `isConnected` on success/failure + idle poll.
- 🔴 **[DONE]** Stale screenshot under the click reticle at approval time
  (safety-critical). Now a screenshot is fetched on *every* transition into
  `waiting_approval`.
- 🔴 **[DONE]** No visible keyboard focus → added `:focus-visible` styles (App.css).
- 🔴 **[DEFERRED]** Full ARIA tablist/tabpanel + aria-live alertdialog for the
  approval prompt + auto-focus Approve + Enter/Esc shortcuts. (Partial: composer
  placeholder corrected; full a11y semantics deferred.)
- 🟡 **[DONE]** Screen tab dead-end when idle → added "📸 Capture now" button +
  auto-capture when the Screen tab opens.
- 🟡 **[DONE]** Blocking native `alert()` for errors → replaced with in-chat error
  bubbles / inline hints.
- 🟡 **[DONE]** Approve/Reject failed silently → in-flight disabled state + inline
  error if the backend is unreachable.
- 🟡 **[DEFERRED]** Elapsed-time counter on the "Thinking on the GPU…" bubble and
  disabling the model `<select>` during a switch.
- 🟡 **[DEFERRED]** Reject-with-reason input (steering signal for the next plan).
- ⚪ **[DONE]** Hardcoded greeting timestamp (fake fixed clock) → uses real time.
- ⚪ **[DONE]** Remote "Grant access" / "Enable" buttons now disabled until a bot
  token is set.
- ⚪ **[DEFERRED]** Associate edit-form `<label>`s with inputs via `htmlFor/id`.

## 2. Visual design / CSS (App.css, index.css)

- 🟡 **[DONE]** Missing `.st-paused` pill style (a real status rendered unstyled).
- 🟡 **[DONE]** Low-contrast `--text-faint` → lightened the token (the per-class
  font-size bumps were left for a later polish pass).
- 🟡 **[DONE]** `:focus-visible` ring for all interactive controls.
- 🟡 **[DEFERRED]** Self-host Inter/JetBrains Mono instead of the Google Fonts
  `@import` (privacy + offline determinism). Needs `@fontsource/*` deps.
- 🟡 **[DEFERRED]** Small-window responsiveness (≤640px breakpoint, topbar wrap,
  icon-only tabs).
- ⚪ **[DEFERRED]** Remove dead CSS (`.switch/.slider/.field.row`, `.model-path`,
  `.spin`, `.msg.system`).
- ⚪ **[DONE]** `prefers-reduced-motion` support.
- ⚪ **[DONE]** Truncate long task text in the chat header (+ `title`).
- ⚪ **[DEFERRED]** Tokenize the type scale + border radii; unify button hover/active;
  replace emoji icons with lucide; reduce backdrop-filter cost; remove nested
  scroll traps. (Polish — low risk, batched for later.)

## 3. Agent core (executor.py, planner.py, llm.py)

- 🔴 **[DONE]** Loop-guard generic "runaway" finish was cached as a *successful*
  learned plan + journaled as success. Now the generic brake marks the task failed
  and skips `save_task_plan`/`append_task`.
- 🔴 **[DONE]** `focus_window_by_title` result was ignored → keystrokes could hit the
  wrong window. Now a focus failure fails the step instead of typing blind.
- 🔴 **[DEFERRED]** Recursive `next_step`→`execute_pending_action` runs the whole
  task synchronously under the lock (breaks SSE handoff, delays `/api/stop`). This
  is a *large* control-flow refactor (invert to one-step + worker-driven loop);
  deferred to avoid shipping an unverified rewrite.
- 🟡 **[DEFERRED]** Enrich the planner observation with the structured
  `executed_steps` trace (reduces loop-guard reliance).
- 🟡 **[DEFERRED]** `enum`-constrain `action` in `ACTION_JSON_SCHEMA`; feed the
  validation error back on retry instead of lowering temperature.
- 🟡 **[DEFERRED]** Verify the Win+R fallback actually launched the app before
  marking success / caching it.
- 🟡 **[DONE]** `LocalLLM` `_base_url` read-after-unlock race (capture URL under the
  lock). Combined with the earlier `stop_server` RLock fix.
- ⚪ **[DEFERRED]** Generic loop brake should count *consecutive* repeats only.
- ⚪ **[DEFERRED]** Shape-validate replayed cached steps (drop on ValidationError).
- 🟡 **[DEFERRED]** Refactor the 200-line `execute_pending_action` elif ladder;
  normalize `tool`/`action` key duality; `memory.clear_chat_logs()` helper.

## 4. Security & safety

- 🔴 **[DONE]** Sender capability flags were stored but never enforced — any enabled
  remote sender could approve any high-risk action with the shared PIN. Now
  high-risk approvals require `can_approve_high_risk`.
- 🔴 **[DONE]** Shell allowlist used `startswith` prefix match → bypass via
  `dir & evil`. Now commands with shell metacharacters (`& | ; \` $ ( ) < > newline`)
  are rejected before the allowlist check.
- 🔴 **[DEFERRED]** No PIN brute-force lockout (rate limiter resets every 10s) +
  weak default `1234`. Needs a persistent failed-attempt counter + owner alert.
- 🔴 **[DEFERRED]** Unauthenticated local API + `CORS allow_origins=['*']` lets any
  local page flip `bypass`/add owner/enable gateway. Fix = per-session local auth
  token + tightened CORS; deferred because it must not break the PyWebView origin.
- 🟡 **[DEFERRED]** `risk.py` system-dir block uses naive substring match (misses
  `/`, 8.3, UNC, `..`). Delegate to `permissions.is_path_in_dirs`.
- 🟡 **[DEFERRED]** Audit chain is tamper-evident but not tamper-proof (no HMAC key,
  no external anchor; blank-hash rows skipped).
- 🟡 **[DEFERRED]** `/api/settings/import|export` unauthenticated + unvalidated.
- ⚪ **[DONE]** PIN compared with `==` → now `hmac.compare_digest` (both call sites).
- ⚪ **[DEFERRED]** Store a salted hash of the PIN instead of plaintext.
- 🟡 **[DEFERRED]** Confirm `learn` (knowledge-base poisoning) + treat remote-sourced
  goals as strictest-posture regardless of local mode.

## 5. Reliability & code quality

- 🟡 **[DONE]** `test_flag: hello_world` dev cruft removed from `config/permissions.json`.
- 🔴 **[DONE]** Shell metacharacter rejection (see §4).
- 🟡 **[DEFERRED]** Lock-protected `start()`/`stop()` + cancellation Event (depends
  on the §3 recursion refactor).
- 🔴 **[DEFERRED]** Stop seeding the placeholder `telegram:123456789` admin; refuse
  to start the gateway until a real owner is set. (Mitigated today: gateway is OFF
  by default and the placeholder is dropped on first `set_owner`.)
- 🟡 **[DEFERRED]** Atomic temp-file+`os.replace` for `permissions.json` / MEMORY.md /
  knowledge_base writes; abort on parse failure instead of resetting to `{}`.
- 🟡 **[DEFERRED]** `scan_start_menu` spawns one PowerShell per `.lnk` → batch into
  one invocation / COM `IShellLink`; persist results.
- 🟡 **[DEFERRED]** SQLite WAL + busy timeout + `LIMIT` on `get_chat_logs`.
- ⚪ **[DEFERRED]** Move worker/gateway/warm-up into a FastAPI `lifespan`; remove
  `reload=True`; drop dead `ROOT_DIR`/dup `import logging`/unused `List`.
- ⚪ **[DEFERRED]** `os_control` double-encodes PNG + `logging.basicConfig` in a lib.
- ⚪ **[DEFERRED]** `file_tool.rename_file` should use `shutil.move` (cross-drive).
- 🟡 **[DEFERRED]** `messaging_tool` mock send reports success as if real; sanitize
  the output filename; `open_thread` is a stub.
- ⚪ **[DEFERRED]** `discovery.find_file_in_folders` is dead code that bypasses
  permission checks — delete or delegate to `file_tool.search_files`.

## 6. Docs & release readiness

- 🔴 **[DONE]** New source files were untracked (a fresh clone crashed on import) →
  staged in the release commit (verified with `git status`).
- 🔴 **[DONE]** No `LICENSE` despite the MIT badge → added MIT `LICENSE`.
- 🔴 **[DONE]** README rewritten in English with the real install flow (clone → get
  llama.cpp CUDA build into `llama\` → download a GGUF into `models\` →
  `start.bat`), env-var table, accurate config, safety model, troubleshooting.
- 🟡 **[DONE]** `.claude/` added to `.gitignore` (was about to publish private notes).
- 🟡 **[DONE]** `download_models.ps1` made resumable (`curl -C -`, keep partial) +
  clearer guidance. URLs stay user-filled by design.
- ⚪ **[DONE]** `desktop.py` health-check "Gemma-4" → "GGUF model" (model-agnostic).
- ⚪ **[DONE]** `frontend/README.md` stock Vite template replaced.
- 🟡 **[DONE]** `test_flag` removed (see §5).
- 🟡 **[DEFERRED]** `docs/configuration_guide.md` / `remote_gateway_guide.md` still
  describe some keys/flows that drifted from code (email keys, Zalo/WhatsApp
  webhooks are roadmap-only) — tighten in a docs pass.
