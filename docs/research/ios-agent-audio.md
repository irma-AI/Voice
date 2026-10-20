# iOS: no agent audio through the WebRTC loopback

Question: is "Web Audio into a MediaStreamDestination, through a same-page RTCPeerConnection loopback, played by `<audio srcObject>`, plays silence on iPhone while the mic is open" a known WebKit issue, and since when? All sources read 2026-10-20.

## Short answer

I found no WebKit bug that matches this exact setup, and no iOS 18.x release that is named as introducing it. **Not confirmed.**

## Findings

**Confirmed**

- On iOS, Firefox also runs on WebKit (App Store guideline 2.5.6, [link](https://developer.apple.com/app-store/review/guidelines/)). Safari and Firefox failing together therefore points to one WebKit bug.
- While the page captures with echo cancellation, WebKit plays MediaStreamTrack audio (which is what an `<audio srcObject>` plays) through the capture's voice-processing unit (VPIO). This is a separate path from Web Audio's own output. A 2025 fix in that path covered "MediaStreamTrack audio rendering may be broken" when a page captures both with and without echo cancellation (bug 286572, commit fafc279: [bug](https://bugs.webkit.org/show_bug.cgi?id=286572), [commit](https://github.com/WebKit/WebKit/commit/fafc27995052)).
- An open regression covers the same voice-processing path: audio output crackles while getUserMedia with echoCancellation is active on iOS 26.2 to 27, and the reporter says iOS 18.7 is clean. The symptom is crackle, not silence (bug 326286, filed 2026-10-04: [link](https://bugs.webkit.org/show_bug.cgi?id=326286)).
- Older silence-while-capturing reports: bug 239996 (iOS 15.4, 2022, about 80% of calls silent with AudioContext plus WebRTC; [link](https://bugs.webkit.org/show_bug.cgi?id=239996)) and bug 212669 (a remote track in SDP but a silent element; pausing and playing the element fixed it; [link](https://bugs.webkit.org/show_bug.cgi?id=212669)).

**Speculation:** the loopback remote track goes down that VPIO track-rendering path, so a bug or state problem there (audio session, route, or a new iOS point release) would silence our audio. Playing to `ctx.destination` would avoid that path. This guess fits "worked yesterday" (an iOS update), but I have not verified it.

## Workarounds

- Play Web Audio directly to `ctx.destination` on iOS. This is what Pipecat's WebSocket client does: its `WavStreamPlayer` uses `streamNode.connect(this.context.destination)`, with no loopback and no audio element ([link](https://github.com/pipecat-ai/pipecat-client-web-transports/blob/main/lib/src/wavtools/lib/wav_stream_player.js)). OpenAI's realtime-console player does the same ([link](https://github.com/openai/openai-realtime-console/blob/websockets/src/lib/wavtools/lib/wav_stream_player.js)).
- `navigator.audioSession.type = 'play-and-record'` is meant for mic use and calls ([spec](https://www.w3.org/TR/audio-session/)). WebKit's behaviour with it has been inconsistent: bug 271305 is about the volume level switching on capture ([link](https://bugs.webkit.org/show_bug.cgi?id=271305)), and the "transient" types play no sound on iOS 18 (bug 264473, [link](https://bugs.webkit.org/show_bug.cgi?id=264473)). Not shown to fix silence.
- Creating the AudioContext before or after getUserMedia did not change the crackle in bug 326286. I found no source tying context order to silence.

## Does iOS echo-cancel Web Audio output?

Not confirmed by a primary source. A vendor page claims Safari and Firefox apply AEC to Web Audio, unlike Chromium (docs.atmoky.com/known-issues; it would not load, a TLS certificate error, so I saw it only in a search snippet). Bug 326286 notes that turning echo cancellation off moves output to the earpiece, so page output does sit inside a voice-processing session. Whether VPIO uses the `ctx.destination` output as its echo reference needs a test on a device.

## Other clients

- Pipecat WebSocket and OpenAI realtime-console: `AudioContext.destination` (see above).
- LiveKit: its WebRTC remote tracks play through media elements by default. An opt-in `webAudioMix` sends them through a gain node instead, and LiveKit had a doubled-audio bug on iOS because element `volume` is ignored there (#2003, July 2026, [link](https://github.com/livekit/client-sdk-js/issues/2003)). A separate report: the AudioContext closes on iPhone Safari after the mic is enabled (#1515, May 2025, cause unconfirmed, [link](https://github.com/livekit/client-sdk-js/issues/1515)).
