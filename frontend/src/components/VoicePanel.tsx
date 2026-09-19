/**
 * Deliberately a disabled/empty state, not a fake call UI (CLAUDE.md: "never
 * fake it"). Live wiring against the ElevenLabs browser SDK lands once
 * app/api/voice.py's session-creation route is merged (Phase 5) and real
 * ELEVENLABS_API_KEY/ELEVENLABS_AGENT_ID credentials exist to test against —
 * neither is true in this environment yet, so the honest state is "not
 * configured," not a simulated call.
 */
export function VoicePanel({ elevenlabsLive }: { elevenlabsLive: boolean }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Voice</h3>
      {elevenlabsLive ? (
        <p className="mt-2 text-xs text-amber-300">
          ElevenLabs credentials are configured, but the browser call UI is not yet wired in this build — the
          live acceptance gate is reachable via the API only.
        </p>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          ElevenLabs not configured — live voice gate UNMET. Set <code className="text-slate-400">ELEVENLABS_API_KEY</code>{" "}
          and <code className="text-slate-400">ELEVENLABS_AGENT_ID</code> to enable a real browser call with a
          persisted recording and transcript.
        </p>
      )}
    </div>
  );
}
