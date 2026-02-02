# Phase 05: Polish + Legacy Cleanup

Objective

- Make the port story consistent across code + comments.
- Add small unit tests for mapping logic.

Checklist

- Fix misleading port comments in WASM/native mains.
- Fix misleading oc-bridge docs/comments if they mention wrong ports.
- Add Python tests for:
  - app/mode -> controller port mapping
  - wasm URL printing (bridgeWsPort query param)
