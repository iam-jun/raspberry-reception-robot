# UI App

This folder will contain the touch-screen UI for the Smart Reception Robot.

The UI should call the orchestrator service endpoints instead of talking directly to STT, RAG, or TTS. The initial flow is:

```text
button press -> call /ask -> display question and answer
```

For now this module is a placeholder only.

