# Feature: Persistent Storage for SDL Builds

**Status:** planned  
**Project:** midi-studio  
**Created:** 2026-01-17  

## Context

SDL builds (Native + WASM) currently use `MemoryStorage` which is in-memory only. Data is lost on restart.

## Goal

Add persistent storage for SDL builds:
- **Native (Windows/Linux/macOS):** File-based storage (JSON or binary)
- **WASM (Browser):** IndexedDB or localStorage

## Current State

### Implemented
- `MemoryStorage` class in `core/sdl/MemoryStorage.hpp`
- Used by both `main-native.cpp` and `main-wasm.cpp`
- Storage interface: `IStorage` from open-control framework

### Architecture

```
IStorage (interface)
├── TeensyStorage    → EEPROM/LittleFS (Teensy)
├── MemoryStorage    → In-memory (SDL, current)
├── FileStorage      → JSON/Binary file (Native, TODO)
└── BrowserStorage   → IndexedDB (WASM, TODO)
```

## Tasks

- [ ] Create `FileStorage` class for Native builds
  - Location: `core/sdl/FileStorage.hpp`
  - Use JSON for human-readable storage
  - Store in user config dir (`~/.config/midi-studio/` or `%APPDATA%`)
- [ ] Create `BrowserStorage` class for WASM builds
  - Location: `core/sdl/BrowserStorage.hpp`
  - Use IndexedDB via Emscripten APIs
  - Fallback to localStorage if needed
- [ ] Update `main-native.cpp` to use `FileStorage`
- [ ] Update `main-wasm.cpp` to use `BrowserStorage`
- [ ] CMake: conditionally compile correct storage impl

## Notes

- Phase 5 (TransportFactory) from original plan was skipped - direct includes work fine
- WebSocket transport for WASM is fully implemented
- Storage is the last major SDL feature gap
