# Phase 08: End-to-end Validation + First Public Release

Status: TODO

## Goal

Validate the full system and publish the first public stable release.

## Required E2E Scenarios

1) Fresh install

- Install bootstrap
- Install latest stable bundle
- Install bridge service
- Deploy Bitwig extension
- Flash firmware
- Cancel a flash mid-way and confirm the bridge is not left paused (`oc-bridge ctl status`).

2) Update

- From stable tag A to stable tag B
- Ensure atomic `current` switch
- Ensure bridge service restarts cleanly
- Ensure the bridge service definition references a stable `current/` exec path (not a versioned path).
- Ensure Bitwig extension is updated

3) Repair

- Simulate missing files in `current`
- Run repair action
- Verify system returns to a consistent state

4) Nightly

- Verify nightly pipeline skips when any repo is not fully green
- Verify nightly publishes when all repos are green and integration build passes

## Exit Criteria

- E2E scenarios pass on Windows/macOS/Linux.
- Distribution repo has:
  - stable release tag
  - signed manifest
  - correct assets
  - working Pages demos
- Documentation is sufficient for contributors.

## Tests

- CI: all workflows green.
- Manual: at least one fresh install test per OS.
