---
target: voice/page.html call page in the panel
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 2
target_identity: "file:/Users/petterannerwall/Developer/Voice/.claude/worktrees/agent-a269d4246a012b3c5/voice/page.html"
target_fingerprint: "sha256:3d36afd0a9592bd6cf8f2a08dc6a0ab7fb708043294c7cce89200a95418e90b7"
target_path: /Users/petterannerwall/Developer/Voice/.claude/worktrees/agent-a269d4246a012b3c5/voice/page.html
timestamp: 2026-10-18T06-18-48Z
slug: voice-page-html
---
Method: dual-agent (A: design review · B: detector and headless browser evidence)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | The themed live dot and arc are below 3:1, and the button state is off-screen in the panel |
| 2 | Match System / Real World | 2 | English page on a Swedish site, with a Swedish launcher and refusal; the labels say "Agent", the disclosure says "AI assistant" |
| 3 | User Control and Freedom | 2 | Hang up is below the fold; Escape does not work inside the frame |
| 4 | Consistency and Standards | 3 | The Live Light Rule breaks after the call: the arc and the last agent line stay lit |
| 5 | Error Prevention | 3 | The microphone prompt is warned about before it appears |
| 6 | Recognition Rather Than Recall | 3 | The state sentence always says what to do next |
| 7 | Flexibility and Efficiency | 2 | No Escape inside the frame; no focus on Start call |
| 8 | Aesthetic and Minimalist Design | 3 | Restrained, but the empty ring and transcript slot take 256px before the call |
| 9 | Error Recovery | 3 | Blocked does not say where to allow the microphone again |
| 10 | Help and Documentation | 2 | No hint of what the agent can answer |
| **Total** | | **26/40** | **Acceptable** |

## Design Specificity Verdict

Mostly specific. The serif disclosure, the compact Turn ring, the agent in Cable light and the dot-and-label chip all belong to Voice. Two things weaken it: the pre-call ring reads as a generic timer, and under a Theme the accent replaces the one warm light. At panel size it was a full page squeezed into a widget.

The deterministic scan found 2 overused-font warnings (Instrument Serif, Geist), which are false positives because the type is settled. In the browser, it found 1 low-contrast finding: the previous transcript line's label at 4.2:1.

## Priority Issues

- [P0] The primary action is never in view: the content is 633 to 683px in a 512px panel, so Start call and Hang up sit below the fold. Fix: make the panel a column as tall as the frame and let the transcript take the slack.
- [P1] The Theme accent drives the live marks at 2.95:1 on Deep sea (fails 1.4.11).
- [P1] The Live Light Rule breaks after the call: the arc, the 0:00 linecap dot and the last agent line stay lit.
- [P2] Accessibility: the previous line's label is at 3.9 to 4.2:1; the transcript has no role; Escape does not work inside the frame.
- [P2] Ended and blocked copy and weight: "Thank you for calling." does not name the Business, and "Call again" is a full-strength primary button.

## Persona Red Flags

- Persona A: "Press Start call" shows with no button in sight; the ring shows 0:00 before the call starts.
- Persona B: the transcript has no role; the label is at 3.9:1; the green live dot is at 2.95:1; Escape does nothing inside the panel.
- Persona C: Hang up is off-screen during a call, and in landscape less than half the panel shows.

## Minor Observations

- The iframe's white background flashes before the page paints.
- A long Business name wraps to two lines.
- No lang attribute is set on the transcript lines.
- The refused page has no visual anchor.

## Questions to Consider

- Should the ring exist before there is a call?
- Does the Theme mean "the button is yours, the light is Voice's"?
