# Founder script first, then record

Approved in chat, 2026-10-27.

## Why

The narration was written after recording, from what ended up on screen, so it described the clicks: "Select $126 to
$150 range." "Choose Running Shoes only." Nemotron wrote captions with every prompt we tried; GLM wrote first-person
lines that were still flat. A founder doesn't work that way. They know their product, they decide what story to tell
and to whom, they record to match it, and they speak in their own words about why it matters.

## The flow

One prompt, for example "Show my investors how easy it is to find men's running shoes under $150 on our site."

1. **Always a map.** Without a map there is no product knowledge, so `demo` explores the site first when no
   `--index` is given. Maps are cached per host in `~/.cache/jev-demofast/maps/<host>.json`.
2. **The founder's script (Nemotron on Nebius).** Before recording, Nemotron reads the prompt (audience and purpose
   included) and what the map knows: the menus and their items, the listings and their filters with their values.
   It writes the voice-over the founder would give: the promise, the walk through the product, and the payoff. This is
   one flowing script, saved as `story.txt` in the run folder and printed.
3. **Record.** Jev drives as before: menus on camera, filters, the Clef check, the showcase, all with the same guards.
4. **Fit and truth pass.** The founder's sentences are placed over the recorded segments, one line per segment, in
   the founder's words. A sentence is changed only where the recording differs: a filter the site disabled, a count, a
   price, or an unconfirmed ending. Counts and names come from what was on screen, never from the script.
5. **Stitch.** Voice per line; each segment's footage is held as long as its line (as before).

## Rules for the voice

- Spoken sentences with a subject and a verb, never captions. "We" and "our", and "you" to the viewer.
- Why it matters to the audience the prompt names, not what the mouse does.
- A comparison with other sites may frame the story, but never as a made-up fact about a competitor.
- No example lines about the product in the prompt: Nemotron copied them word for word.

## Rulings

- The word budget goes from 11 to 17 words per segment, and the 2-6 word fragment rule is removed. A founder's sentence
  doesn't fit in 11 words. Cost: measured on Allbirds, the video went from 38.7 s to 58.5 s (+20 s).
- The script shapes the narration, not Jev's clicks. Making the beats steer the drive is a later step.
- `demo` always has a map. Only the lower-level `run` and `narrate` commands can still record without one, and those
  keep the old narration.
- Nemotron thinks when it writes the script (both calls) and nowhere else. With thinking off it wrote captions. With
  thinking on, each call takes about 3-10 s, once per video.
- The fitting step gets the facts of each segment but not its page text: given the page text, it described the screen
  again.
- The founder's script is written only with `--voice`, because a video without a voice-over has nothing to use it for.
- The script's moments line up with the recording's segments (the promise over the home page, then one per menu,
  listing, filter, and the results). Without that, every line landed one segment late.
- The founder's voice says "our" even on a site the user doesn't own, such as Allbirds. That's fine for showing the
  pipeline.
