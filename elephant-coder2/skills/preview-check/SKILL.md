---
name: preview-check
description: When building or changing something with visual or runtime output — a web app, game, UI, or rendered scene — actually launch it in a preview and inspect the result (screenshot + console logs + DOM/ready state) before claiming it works or refining. Use whenever the deliverable is something a user would look at, not just code that compiles.
---

Code that compiles is not a working UI. For anything visual, the only real check
is looking at the rendered result — so launch it and inspect, don't infer.

## When to trigger

- Built or changed a web page, game, canvas/WebGL scene, or any visible UI.
- About to say a frontend "looks right" or "renders" without having viewed it.
- The user asks to build something and "look at the result and refine it".

## Method

1. **Run it for real.** Start the preview/dev server; load the actual page or app.
2. **Capture the visual.** Take a screenshot of the rendered result — that is the
   ground truth, not the source.
3. **Read the console + state.** Pull console logs (errors/warnings), and check
   `readyState`, that expected elements/canvas exist, and that the render/update
   loop is actually advancing.
4. **Compare to intent.** Does what's on screen match what was asked? Note the
   specific gaps (layout, color, missing element, blank frame).
5. **If it hangs or is blank** (screenshot times out, no logs): it's not a styling
   tweak — hand off to `runtime-debug` to find why the loop is stuck.
6. **Refine from observation.** Change based on what you saw, then re-capture. Loop
   until the rendered result matches.

## Output

Report what you observed in the preview (with the screenshot/console evidence), the
gaps, and the change you're making — then re-verify. Never call a UI done without
having actually viewed it rendering.
