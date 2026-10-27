# The voice sets the timeline

Approved in chat, 2026-10-27, after the first cloud demo. The user chose ElevenLabs.

## Why

Watching the first hosted demo against its narration turned up three problems:

1. **The voice sounded like a computer.** Each line was a separate Deepgram clip, generated on its own and joined
   with gaps. No intonation carried from one sentence to the next.
2. **Screens and words didn't match.**
   - The sentences ran a step ahead of the picture.
   - The video opened on a marketing pop-up.
   - It ended on the filter panel, with the results never shown.
3. **The script didn't sound like a person presenting.** One short sentence per click reads like captions. A
   presenter talks in one continuous thought over several actions, pauses while something loads, and reacts.

All three come from one design: record the clicks, then attach one separate clip to each click.

## The design

1. **One continuous voice-over with screen markers.** After recording, the founder's script (written before
   recording) becomes one continuous voice-over in the founder's words. `[NN]` markers are placed where each recorded
   moment should appear, for example: "…so watch this. [01] Everything for men lives right up here… [02] and Active is
   where our runners are." Every segment id appears exactly once, in order. Two markers may sit side by side, so the
   talk can flow across quick steps. The truth pass is unchanged: greyed-out values, the value really chosen, the
   items really shown.
2. **One take.** ElevenLabs speaks the whole voice-over in a single request, which keeps human intonation across
   sentences. It returns the start time of every character, so each marker gets a time.
3. **The video follows the voice.** Segment NN starts on screen exactly when its marker is spoken and lasts until the
   next marker. Footage shorter than its stretch of speech holds its last frame, which is the step's outcome. Footage
   longer than its speech is shortened down to half; if it's still longer, a pause goes into the voice at that point,
   the way a presenter waits for a page.
4. **Fallback.** Without an ElevenLabs key, each segment's words are spoken by Deepgram, as before.

## Settings

- `ELEVENLABS_API_KEY` (optional). With it, ElevenLabs narrates.
- `JDF_ELEVEN_MODEL`, default `eleven_multilingual_v2`. It's measured fast and stable for long-form; `eleven_v3` is
  more expressive but slower.
- `--voice` takes a name: `chris` (default), `eric`, `will`, `sarah`, `jessica`, which map to ElevenLabs voices.
  Deepgram names (`apollo`, `thalia`) still work without the key.

## Also fixed, from the same video

- The opening frame never shows a pop-up: the demo waits 3 s and clears it first.
- The showcase closes a filter panel that ignores Escape, so the results are on screen.
- A value is called greyed out only after the listing has had time to reload.
- The narrator names only the items outlined on screen.
