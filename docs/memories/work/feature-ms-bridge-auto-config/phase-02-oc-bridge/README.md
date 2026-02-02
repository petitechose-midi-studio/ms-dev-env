# Phase 02: oc-bridge (Headless UX + No IPC Collisions)

Objective

- Allow multiple oc-bridge instances (service + dev headless) without fighting over control-plane ports.
- Make headless mode emit actionable logs on stdout.

Changes

- Only start the control server (pause/resume/status TCP) for `ControllerTransport::Serial`.
- In headless mode, attach a log receiver and print `LogKind::System` entries.

Test

- With a serial-service bridge running:
  - `oc-bridge --headless --controller ws --controller-port 8101 --udp-port 9002`
  - Expected:
    - no "ControlBind" errors
    - prints "Bridge started: WS:8101 ..." and connection lifecycle logs
