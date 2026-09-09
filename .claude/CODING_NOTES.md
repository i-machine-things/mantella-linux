# Coding Best Practices & Reminders

> **Style rule:** Notes must be clear and concise — 300 characters or less each. Group by topic, not by date. Whenever a PR review (CodeRabbit or human) catches a mistake, add or amend a note here right away so it isn't repeated.

## Resource Cleanup & Temporary Files

**IMPORTANT**: Always add proper cleanup code in programs to prevent lingering temp files after closing.

### Best Practices:

1. **GUI Applications (PyQt, Tkinter, etc.)**
   - Implement `closeEvent()` handler to cleanup resources on window close
   - Call `deleteLater()` on widgets to ensure proper Qt object cleanup
   - Process pending events with `app.processEvents()` before exit

2. **File Handling**
   - Use context managers (`with` statements) for file operations
   - Explicitly close file handles when not using context managers
   - Release file locks before program exit
   - Clean up temporary files in temp directories

3. **Background Threads & Workers**
   - Stop and join all background threads before exit
   - Cancel any pending operations
   - Clean up thread-specific resources

4. **Testing Cleanup**
   - After closing the program, verify the executable can be:
     - Deleted immediately
     - Moved to another location
     - Replaced with a new version
   - If the file is locked, cleanup code is missing or incomplete

### Example Implementation (PyQt6):

```python
def closeEvent(self, event):
    """Handle window close event - ensure proper cleanup"""
    # Cleanup modules/components
    for module in self.modules:
        try:
            module.cleanup()
        except Exception as e:
            print(f"Error cleaning up module: {e}")

    # Save state
    self.save_settings()

    # Accept close event
    event.accept()
    QApplication.quit()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    exit_code = app.exec()

    # Final cleanup
    window.deleteLater()
    app.processEvents()

    sys.exit(exit_code)
```

### PyInstaller Specific:

In `.spec` file, add:
```python
exe = EXE(
    ...
    bootloader_ignore_signals=True,  # Better cleanup handling
    ...
)
```

## Date: 2025-12-16
This note was created based on issues encountered with PyInstaller executables remaining locked after closing.

## Network/Socket Security

- **Never bind a socket to the IPv6/IPv4 wildcard (`::` / `0.0.0.0`) just to get dual-stack behavior.** `("::", port)` with `IPV6_V6ONLY=0` listens on every network interface, not just loopback — exposing local-only APIs (and any credentials they proxy) to the whole LAN. For loopback-only dual-stack, bind two explicit sockets (`127.0.0.1` and `::1`) and pass both to the server (e.g. `uvicorn.Server(config).run(sockets=[sock_v4, sock_v6])`), rather than one wildcard socket.

## Async/Concurrency Patterns

- **Don't share one mutable cancellation flag/Event across sequential async operations.** If a "stop the current work" mechanism (e.g. a `threading.Lock` + `asyncio.Event` combo) reuses the same Event object across calls, a bounded/timed-out wait that gives up early and clears it can let a stale-but-still-running operation see cancellation as lifted and resume mutating shared state. Give each operation its own fresh cancellation token (create a new `asyncio.Event()` per call, pass it through explicitly) instead of clearing/reusing a shared one.
- **A bounded wait-then-give-up loop should never also silently reset the state it's waiting on** (e.g. forcing a shared `is_generating` flag back to `False` after a timeout) — that can mask a genuinely stuck task and let its later side effects land unexpectedly. Give up waiting, but leave the underlying state alone.

## General Style Notes

- **Keep lines under 120 characters.** Long lines are hard to review side-by-side in a diff or split editor pane, and tend to signal a line doing too many things at once. Wrap or break up expressions rather than letting them run long.
- **Add docstrings to explain code.** Focus on *why* a function/class exists or *why* it does something non-obvious — the code itself already shows *what* it does. A docstring worth writing usually covers intent, assumptions, edge cases, or a gotcha a future reader would otherwise have to rediscover the hard way.
- **Strip docstrings when building a release.** Release builds don't need internal rationale shipped alongside the binary — it bloats the artifact and can leak implementation notes you didn't mean to publish. Run Python with `-OO` (or an equivalent build step) to drop docstrings and assertions from the compiled output before packaging.
