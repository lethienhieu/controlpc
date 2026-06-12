import os
import time
import json
import logging
import re
from typing import List, Dict, Any, Optional

from agent.llm import LocalLLM
from agent.prompts import CHAT_REPLY_PROMPT
from agent.planner import IntentClassifier, ReActPlanner
from core import os_control, uia_control, discovery, safety
from database import memory, journal
from policy.action_policy import ActionPolicy
from tools.registry import TOOL_REGISTRY, execute_tool_call

logger = logging.getLogger("executor")

class AgentExecutor:
    def __init__(self):
        import threading
        self.lock = threading.RLock()
        self.current_goal: str = ""
        self.status: str = "idle"  # idle, running, waiting_approval, finished, paused, error
        self.current_step: int = 0
        self.max_steps: int = 12
        self.pending_action: Optional[Dict[str, Any]] = None
        self.ai_mode: str = "mock"  # mock, gemma4
        self.safety_confirmation: bool = True
        self.source_channel: str = "local_ui"
        self.sender_id: str = "user"
        
        self.llm = LocalLLM()
        self.policy = ActionPolicy()
        self.classifier = IntentClassifier(self.llm)
        self.planner = ReActPlanner(self.llm)
        self._discovery_cache: Dict[str, str] = {}  # Cache Start Menu scan results

        # Procedural memory / skill-library replay state
        self.cached_plan: Optional[List[Dict[str, Any]]] = None
        self.cached_index: int = 0
        self.replaying: bool = False
        self.executed_steps: List[Dict[str, Any]] = []
        self._action_sig_counts: Dict[str, int] = {}  # anti-loop: count repeated proposals
        self._loop_aborted: bool = False  # set when the loop-guard force-finished a runaway

    def start(self, goal: str, ai_mode: str = "mock", safety_confirmation: bool = True, source_channel: str = "local_ui", sender_id: str = "user"):
        self.current_goal = goal
        self.status = "running"
        self.current_step = 0
        self.pending_action = None
        self.ai_mode = ai_mode
        self.safety_confirmation = safety_confirmation
        self.source_channel = source_channel
        self.sender_id = sender_id

        # Procedural memory: reuse a learned plan for this goal if we have one.
        self.executed_steps = []
        self._action_sig_counts = {}
        self._loop_aborted = False
        self.cached_index = 0
        self.cached_plan = memory.get_task_plan(goal)
        self.replaying = bool(self.cached_plan)

        # Clear previous SQLite logs for the new session
        try:
            import sqlite3
            conn = sqlite3.connect(memory.SQLITE_PATH)
            conn.cursor().execute("DELETE FROM chat_logs")
            conn.commit()
            conn.close()
        except:
            pass

        self.add_log("system", f"Starting new task: '{goal}' (AI Mode: {ai_mode.upper()})", "info")
        if self.replaying:
            self.add_log("system", f"Reusing learned plan ({len(self.cached_plan)} steps) — running fast, no need to recompute.", "info")
        return self.next_step()

    def add_log(self, step_type: str, message: str, status: str = "info", action_data: Optional[Dict] = None):
        memory.save_chat_log(self.current_step, step_type, message, status, action_data)
        logger.info(f"[{step_type.upper()}] {message}")

    def handle_chat_input(self, message: str, ai_mode: str = "mock", safety_confirmation: bool = True) -> Dict[str, Any]:
        """
        Processes general chat or system control inputs.
        """
        self.ai_mode = ai_mode
        self.safety_confirmation = safety_confirmation

        is_control_cmd = False
        
        # 1. Classification
        try:
            is_control_cmd = self.classifier.classify(message, ai_mode=ai_mode)
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            raise e

        # 2. Routing
        if is_control_cmd:
            self.start(goal=message, ai_mode=ai_mode, safety_confirmation=safety_confirmation)
            return {"type": "control", "status": self.status, "message": "Starting to plan and execute the control task..."}
        else:
            reply = ""
            if ai_mode == "mock":
                reply = "Hello! I am CONTROLPC, your local virtual assistant for controlling the computer. I can launch applications directly, send keyboard shortcut sequences, interact via Windows UI Automation (UIA), or learn new shortcut paths. Go ahead and give me a command!"
            else:
                try:
                    prompt = CHAT_REPLY_PROMPT.format(message=message)
                    reply = self.llm.generate(prompt=prompt, max_tokens=150, temperature=0.7,
                                              system=journal.read_memory_digest(800) or None)
                except Exception as e:
                    reply = f"Error connecting to the local model: {e}"
                    
            self.status = "idle"
            self.add_log("assistant_chat", reply, "completed")
            return {"type": "chat", "status": self.status, "message": reply}

    def stream_chat_reply(self, message: str, ai_mode: str = "mock"):
        """Generator yielding chat-reply text deltas, for SSE streaming.
        Only used for non-control (chat) messages."""
        if ai_mode == "mock":
            reply = (
                "Hello! I am CONTROLPC, your local virtual assistant for controlling the computer. "
                "I can launch applications directly, send keyboard shortcut sequences, interact via "
                "Windows UI Automation (UIA), or learn new shortcut paths. "
                "Go ahead and give me a command!"
            )
            self.add_log("assistant_chat", reply, "completed")
            yield reply
            return

        full = ""
        for delta in self.llm.generate_stream(
            prompt=CHAT_REPLY_PROMPT.format(message=message), max_tokens=300, temperature=0.7,
            system=journal.read_memory_digest(800) or None
        ):
            full += delta
            yield delta
        self.add_log("assistant_chat", full, "completed")

    def next_step(self) -> Dict[str, Any]:
        with self.lock:
            if self.status != "running":
                return {"status": self.status, "message": "Agent is not active."}

            self.current_step += 1
            if self.current_step > self.max_steps:
                self.status = "error"
                self.add_log("system", "Exceeded the ReAct step limit.", "failed")
                return {"status": self.status, "message": "Exceeded the step limit."}

            self.add_log("system", f"Analyzing step {self.current_step}...", "info")
            
            # Plan decision (skip screenshot to save time; only capture when needed for click actions)
            decision = self.plan_action()
            if not decision:
                self.status = "error"
                self.add_log("system", "Did not receive a valid decision from the AI.", "failed")
                return {"status": self.status}

            reasoning = decision.get("reasoning", "Processing...")
            action = decision.get("action")
            params = decision.get("params", {})

            # Anti-loop guard (deterministic, independent of the LLM). A slow app
            # (Revit, AutoCAD…) isn't visible in the observation yet, so the planner
            # may keep proposing the same launch — which spawns duplicate windows in
            # an endless loop. Override such repeats with a clean finish.
            loop_override = self._loop_guard(action, params)
            if loop_override is not None:
                decision = loop_override
                reasoning = decision["reasoning"]
                action = decision["action"]
                params = decision["params"]

            self.add_log("reasoning", reasoning, "completed")
            
            # Evaluate safety policy
            policy_res = self.policy.evaluate_action(
                tool=action,
                params=params,
                intent=self.current_goal,
                reason=reasoning,
                safety_confirmation=self.safety_confirmation
            )
            
            risk_level = policy_res["risk_level"]
            decision_policy = policy_res["decision"]
            
            # Save Audit Log in pending/executing state
            memory.save_audit_log(
                policy_res, 
                source_channel=self.source_channel, 
                sender_id=self.sender_id, 
                executed_status="pending" if decision_policy == "requires_confirmation" else "executing"
            )
            
            action_desc = f"{action.upper()} (Risk level: {risk_level.upper()}) - Parameters: {params}"

            if decision_policy == "blocked":
                self.status = "error"
                self.add_log("error", f"Action BLOCKED by the security system: {policy_res['preview']['title']}. Reason: {policy_res['preview']['summary']}", "failed")
                memory.update_audit_log_status(policy_res["action_id"], "blocked")
                return {"status": self.status, "message": "Action blocked by the security policy."}
                
            self.pending_action = policy_res
            
            # Check Safety / User Approval
            if decision_policy == "requires_confirmation":
                self.status = "waiting_approval"
                self.add_log("action", f"Waiting for approval: {action_desc}", "pending", self.pending_action)
                if self.source_channel == "telegram":
                    try:
                        from integrations.telegram import send_telegram_notification
                        send_telegram_notification(
                            self.sender_id,
                            f"⚠️ Action approval requested:\n"
                            f"Target: {self.pending_action['preview']['title']}\n"
                            f"Description: {self.pending_action['preview']['summary']}\n"
                            f"Please send your PIN to approve execution."
                        )
                    except Exception as ex:
                        logger.error(f"Failed to send remote notification: {ex}")
                return {
                    "status": self.status,
                    "pending_action": self.pending_action
                }
            else:
                return self.execute_pending_action()

    def _loop_guard(self, action: Optional[str], params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return a 'finish' decision when the proposed action would loop, else None.

        Two cases:
        1. Re-opening an app already launched successfully this session (the #1 cause
           of the "Revit opens forever" bug — a heavy app is slow to show its window,
           so the planner keeps re-issuing `open`).
        2. Any identical (action, params) proposed 3+ times — generic runaway brake.
        """
        norm = lambda s: (s or "").strip().lower()

        if action == "open":
            app = norm(params.get("app_name"))
            already_opened = any(
                s.get("action") == "open"
                and norm(s.get("params", {}).get("app_name")) == app
                for s in self.executed_steps
            )
            if app and already_opened:
                return {
                    "reasoning": f"The application '{params.get('app_name')}' was already opened successfully in a previous step — not reopening, ending the task.",
                    "action": "finish",
                    "params": {"message": f"Successfully opened '{params.get('app_name')}'."},
                }

        sig = f"{action}:{json.dumps(params, sort_keys=True, ensure_ascii=False)}"
        self._action_sig_counts[sig] = self._action_sig_counts.get(sig, 0) + 1
        if action not in ("finish", "learn") and self._action_sig_counts[sig] >= 3:
            self._loop_aborted = True
            return {
                "reasoning": "Detected the same action repeated multiple times — stopping to avoid an infinite loop.",
                "action": "finish",
                "params": {"message": "Stopped the task because a loop was detected."},
            }
        return None

    def plan_action(self) -> Optional[Dict[str, Any]]:
        # Replay a learned plan step-by-step (skips the LLM entirely). Policy and
        # approval still apply to every replayed step.
        if self.replaying and self.cached_plan and self.cached_index < len(self.cached_plan):
            step = dict(self.cached_plan[self.cached_index])
            self.cached_index += 1
            return step
        self.replaying = False

        history_logs = memory.get_chat_logs()
        return self.planner.plan(
            goal=self.current_goal,
            step=self.current_step,
            max_steps=self.max_steps,
            history_logs=history_logs,
            ai_mode=self.ai_mode
        )

    def execute_pending_action(self) -> Dict[str, Any]:
        with self.lock:
            if not self.pending_action:
                return {"status": self.status, "message": "No pending action."}

            self.status = "running"
            action = self.pending_action.get("tool") or self.pending_action.get("action")
            params = self.pending_action["params"]
            action_id = self.pending_action.get("action_id")

            self.add_log("action", f"Executing: {action.upper()} - {params}", "info")
            if action_id:
                memory.update_audit_log_status(action_id, "executing")
            
            success = False
            err_msg = ""
            
            try:
                if action in TOOL_REGISTRY:
                    res = execute_tool_call(action, params)
                    success = res.get("success", False)
                    err_msg = res.get("error", "")
                    if success:
                        if "message" in res:
                            self.add_log("system", f"Result: {res['message']}", "info")
                        elif "content" in res:
                            self.add_log("system", f"Result: Successfully read the file ({res.get('length')} characters)", "info")
                        elif "summary" in res:
                            self.add_log("system", f"Summary result: {res['summary']}", "info")
                        elif "results" in res:
                            self.add_log("system", f"Search complete, found {len(res['results'])} files.", "info")
                elif action == "click":
                    # Validate coordinates safety
                    x, y = params.get("x"), params.get("y")
                    if safety.validate_click_safety(x, y):
                        res = os_control.click_mouse(x, y, params.get("click_type", "click"))
                        success = res["success"]
                        err_msg = res.get("error", "")
                    else:
                        success = False
                        err_msg = "Coordinates blocked by safety settings."
                elif action == "click_uia":
                    res = uia_control.click_uia_element(
                        window_title_re=params.get("window_title_re", ""),
                        auto_id=params.get("auto_id"),
                        name=params.get("name"),
                        control_type=params.get("control_type")
                    )
                    success = res["success"]
                    err_msg = res.get("error", "")
                elif action == "type":
                    window_title = params.get("window_title_re")
                    focused = True
                    if window_title:
                        from core.uia_control import focus_window_by_title
                        focused = focus_window_by_title(window_title)
                    if window_title and not focused:
                        success = False
                        err_msg = f"Could not focus a window matching '{window_title}'; refusing to send keystrokes to the wrong window."
                    else:
                        res = os_control.type_text(params.get("text", ""), params.get("press_enter", False))
                        success = res["success"]
                        err_msg = res.get("error", "")
                elif action == "press":
                    window_title = params.get("window_title_re")
                    focused = True
                    if window_title:
                        from core.uia_control import focus_window_by_title
                        focused = focus_window_by_title(window_title)
                    if window_title and not focused:
                        success = False
                        err_msg = f"Could not focus a window matching '{window_title}'; refusing to send keystrokes to the wrong window."
                    else:
                        res = os_control.press_key(params.get("key", ""))
                        success = res["success"]
                        err_msg = res.get("error", "")
                elif action == "hotkey":
                    window_title = params.get("window_title_re")
                    focused = True
                    if window_title:
                        from core.uia_control import focus_window_by_title
                        focused = focus_window_by_title(window_title)
                    if window_title and not focused:
                        success = False
                        err_msg = f"Could not focus a window matching '{window_title}'; refusing to send keystrokes to the wrong window."
                    else:
                        res = os_control.press_hotkey(*params.get("keys", []))
                        success = res["success"]
                        err_msg = res.get("error", "")
                elif action == "open":
                    app_name = params.get("app_name", "")
                    # 1. Search knowledge base
                    exe_path = memory.get_app_path(app_name)
                    
                    # 2. If not found, use cached scan or run new Start Menu scan
                    if not exe_path:
                        # Check cache first to avoid repeated slow scans
                        cache_key = app_name.lower().strip()
                        if cache_key in self._discovery_cache:
                            exe_path = self._discovery_cache[cache_key]
                            self.add_log("system", f"Found in cache: '{app_name}' -> '{exe_path}'", "info")
                        else:
                            self.add_log("system", f"Path for '{app_name}' not available yet. Scanning the Start Menu...", "info")
                            scanned = discovery.scan_start_menu()
                            candidates = discovery.find_app_candidates(app_name, scanned, top_n=5)
                            # Confident: a single match, or the best clearly beats the rest.
                            if candidates and (len(candidates) == 1 or candidates[0][2] - candidates[1][2] >= 200):
                                matched_key, exe_path, _score = candidates[0]
                                self._discovery_cache[cache_key] = exe_path
                                self.add_log(
                                    "system",
                                    f"Detected app: '{matched_key}' -> '{exe_path}'. Saving under the name '{app_name}'.",
                                    "info",
                                )
                                memory.save_app_path(app_name, exe_path)
                            elif candidates:
                                # Ambiguous: ask the user instead of opening the wrong app.
                                lines = "\n".join(f"  {i + 1}. {k}" for i, (k, p, s) in enumerate(candidates))
                                msg = (f"Multiple applications match '{app_name}'. Which one would you like to open? "
                                       f"Please reply with the exact full name:\n{lines}")
                                self.add_log("assistant_chat", msg, "completed")
                                self.status = "finished"
                                self.pending_action = None
                                if action_id:
                                    memory.update_audit_log_status(action_id, "completed")
                                return {"status": self.status, "message": msg}
    
                    # 3. Launch file/app directly
                    if exe_path:
                        res = os_control.open_app_or_file(exe_path)
                        success = res["success"]
                        err_msg = res.get("error", "")
                    else:
                        # Fallback to Win+R. Report success based on the actual OS
                        # calls instead of blindly assuming it worked.
                        self.add_log("system", f"Could not find an absolute path for '{app_name}'. Using Win+R as a fallback.", "info")
                        r1 = os_control.press_hotkey("win", "r")
                        time.sleep(0.5)
                        r2 = os_control.type_text(app_name, press_enter=True)
                        success = r1.get("success", False) and r2.get("success", False)
                        if not success:
                            err_msg = r1.get("error") or r2.get("error") or "Win+R fallback failed"
                        
                elif action == "learn":
                    key = params.get("key", "")
                    val = params.get("value", "")
                    success = memory.save_app_path(key, val)
                    if success:
                        self.add_log("success", f"Finished learning: '{key}' -> '{val}'", "completed")
                    else:
                        err_msg = "Error updating the database."
                elif action == "finish":
                    # Learn: cache the full successful action sequence so the same
                    # goal replays instantly next time (skill library). Skip caching
                    # and journaling when the loop-guard aborted the task — a runaway
                    # is not a successful plan and must not poison procedural memory.
                    self.executed_steps.append({"reasoning": self.pending_action.get("reason", ""), "action": "finish", "params": params})
                    if not self._loop_aborted:
                        try:
                            memory.save_task_plan(self.current_goal, self.executed_steps)
                        except Exception as ex:
                            logger.error(f"Failed to cache task plan: {ex}")
                        try:
                            from database import journal
                            journal.append_task(self.current_goal, self.executed_steps, params.get("message", ""), self.ai_mode)
                        except Exception as ex:
                            logger.error(f"Failed to write markdown journal: {ex}")
                    self.status = "finished"
                    if self._loop_aborted:
                        self.add_log("error", f"Task stopped (loop detected): {params.get('message')}", "failed")
                    else:
                        self.add_log("success", f"Task completed: {params.get('message')}", "completed")
                    self.pending_action = None
                    if self.source_channel == "telegram":
                        try:
                            from integrations.telegram import send_telegram_notification
                            send_telegram_notification(
                                self.sender_id,
                                f"✅ Task completed successfully!\nResult: {params.get('message')}"
                            )
                        except Exception as ex:
                            logger.error(f"Failed to send finish notification: {ex}")
                    return {"status": self.status, "message": "Task completed"}
                else:
                    err_msg = f"Unknown action: {action}"
            except Exception as e:
                err_msg = str(e)
                
            # Update logs status
            if success:
                # Record the step for the skill-library cache (saved on finish).
                self.executed_steps.append({"reasoning": self.pending_action.get("reason", ""), "action": action, "params": params})
                self.add_log("system", "Action executed successfully.", "info")
                if action_id:
                    memory.update_audit_log_status(action_id, "completed")
                self.pending_action = None
                time.sleep(0.3)  # Reduced from 1.0s → 0.3s: enough for the OS to respond without a perceptible delay
                return self.next_step()
            else:
                # A replayed (cached) step failed → the learned plan is stale.
                # Drop it and re-plan the remainder with the LLM instead of failing.
                if self.replaying:
                    self.replaying = False
                    self.cached_plan = None
                    memory.delete_task_plan(self.current_goal)
                    self.add_log("system", "The learned plan is no longer valid — re-planning automatically.", "info")
                    if action_id:
                        memory.update_audit_log_status(action_id, "failed")
                    self.pending_action = None
                    time.sleep(0.2)
                    return self.next_step()
                self.status = "error"
                self.add_log("error", f"Error executing the action: {err_msg}", "failed")
                if action_id:
                    memory.update_audit_log_status(action_id, "failed")
                self.pending_action = None
                if self.source_channel == "telegram":
                    try:
                        from integrations.telegram import send_telegram_notification
                        send_telegram_notification(
                            self.sender_id,
                            f"❌ Task failed at step {self.current_step}.\nError: {err_msg}"
                        )
                    except Exception as ex:
                        logger.error(f"Failed to send failure notification: {ex}")
                return {"status": self.status, "error": err_msg}

    # Fields the user may edit before approving, per tool.
    EDITABLE_FIELDS = {
        "email.send": ["to_email", "subject", "body"],
        "email.create_draft": ["to_email", "subject", "body"],
        "message.send": ["contact_query", "text"],
        "message.create_draft": ["contact_query", "text"],
    }

    def edit_pending_action(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Edit the content of the pending action (email/message) before approval."""
        with self.lock:
            if self.status != "waiting_approval" or not self.pending_action:
                return {"success": False, "error": "No action is awaiting approval."}

            tool = (self.pending_action.get("tool") or self.pending_action.get("action") or "").lower()
            allowed = self.EDITABLE_FIELDS.get(tool, [])
            if not allowed:
                return {"success": False, "error": f"The action '{tool}' does not support editing its content."}

            params = self.pending_action.setdefault("params", {})
            changed = []
            for key in allowed:
                if key in updates and isinstance(updates[key], str):
                    params[key] = updates[key]
                    changed.append(key)

            if not changed:
                return {"success": False, "error": "No valid fields to update."}

            # Refresh the preview summary so the approval card reflects edits.
            self.pending_action.setdefault("preview", {})["summary"] = (
                f"(Edited) {tool} → {params.get('to_email') or params.get('contact_query', '')}"
            )
            self.add_log("system", f"User edited the content before approval: {changed}", "info")
            return {"success": True, "pending_action": self.pending_action, "changed": changed}

    def reject_pending_action(self, reason: str = "User rejected") -> Dict[str, Any]:
        self.status = "paused"
        self.add_log("system", f"Action rejected: {reason}", "info")
        if self.pending_action and "action_id" in self.pending_action:
            memory.update_audit_log_status(self.pending_action["action_id"], "rejected")
        self.pending_action = None
        return {"status": self.status, "message": "Task paused."}
